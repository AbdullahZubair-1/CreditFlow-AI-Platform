import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
import httpx
from sqlalchemy import update

from app import content_client, linkedin_client
from app.crypto import decrypt_token
from app.db import async_session_factory
from app.linkedin_client import LinkedInError
from app.models import PostMedia, ProcessedEvent, PublishJob, SocialConnection
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("social_publishing.events")

DOMAIN_EVENTS_EXCHANGE = "domain_events"
# The spec names a dedicated "social_events" topic exchange for this
# domain's own events (post.published/post.failed) — same treatment as
# Billing's "billing_events" — even though most other services in this
# codebase publish to the shared domain_events exchange instead.
SOCIAL_EVENTS_EXCHANGE = "social_events"
QUEUE_NAME = "social_publishing.content_scheduled"

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await get_connection()
        _channel = await get_confirm_channel(_connection)
    return _channel


def _envelope(routing_key: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": routing_key,
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": data,
    }


async def _publish(routing_key: str, data: dict[str, Any]) -> None:
    channel = await get_channel()
    await publish_event(channel, SOCIAL_EVENTS_EXCHANGE, routing_key, _envelope(routing_key, data))


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


async def _fail_permanently(job: PublishJob, reason: str) -> None:
    """For failures that retrying can never fix (no LinkedIn connection,
    content deleted, etc.) — records the failure and emits post.failed,
    but deliberately does NOT raise, so the bounded-retry-then-DLX
    mechanism in py_shared.rabbitmq isn't wasted retrying something that
    will fail identically every time."""
    async with async_session_factory() as session:
        row = await session.get(PublishJob, job.id)
        row.status = "failed"
        row.error_reason = reason[:255]
        row.completed_at = datetime.now(UTC)
        await session.commit()

    await _publish(
        "post.failed",
        {"scheduled_post_id": str(job.scheduled_post_id), "account_id": str(job.account_id), "reason": reason},
    )


async def _release_claim(job_id: uuid.UUID) -> None:
    """Reverts a job's atomic claim (see _handle_content_scheduled) back to
    'pending' after a transient failure, so the bounded-retry-then-DLX
    mechanism can actually re-attempt it — without this, a job claimed via
    the pending->publishing UPDATE would stay stuck in 'publishing' forever
    after any retryable error, since retries would find status != 'pending'
    and silently no-op instead of retrying."""
    async with async_session_factory() as session:
        await session.execute(
            update(PublishJob)
            .where(PublishJob.id == job_id, PublishJob.status == "publishing")
            .values(status="pending")
        )
        await session.commit()


async def _handle_content_scheduled(payload: dict[str, Any]) -> None:
    data = payload["data"]
    scheduled_post_id = uuid.UUID(data["scheduled_post_id"])
    account_id = uuid.UUID(data["account_id"])
    content_id = uuid.UUID(data["content_id"])

    async with async_session_factory() as session:
        job = await session.get(PublishJob, scheduled_post_id)
        if job and job.status not in ("pending",):
            return  # already claimed, published, or permanently failed (redelivery)
        if not job:
            job = PublishJob(scheduled_post_id=scheduled_post_id, account_id=account_id, content_id=content_id)
            session.add(job)
            await session.commit()

    # Atomically claim the job before making the real LinkedIn API call —
    # this, not the read above, is what actually prevents a duplicate real
    # LinkedIn post: two concurrent redeliveries of the same event can both
    # pass the "status == pending" read, but only one of them can win this
    # UPDATE ... WHERE status = 'pending'. The other sees rowcount == 0 and
    # backs off instead of also calling LinkedIn.
    async with async_session_factory() as session:
        result = await session.execute(
            update(PublishJob).where(PublishJob.id == job.id, PublishJob.status == "pending").values(status="publishing")
        )
        await session.commit()
        if result.rowcount == 0:
            logger.info("job %s already claimed by another delivery, skipping", job.id)
            return

    async with async_session_factory() as session:
        connection = await session.get(SocialConnection, account_id)
    if not connection:
        await _fail_permanently(job, "Account has no connected LinkedIn account.")
        return

    try:
        content = await content_client.get_content(str(account_id), "service", str(content_id))
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            await _fail_permanently(job, "Content item no longer exists.")
            return
        await _release_claim(job.id)
        raise  # transient — let it retry via the standard bounded-retry-then-DLX path

    access_token = decrypt_token(connection.access_token_encrypted)

    try:
        asset_urn = None
        if content.get("image_url"):
            asset_urn = await _upload_image(job.id, access_token, connection.linkedin_member_urn, content["image_url"])

        linkedin_post_id = await linkedin_client.create_ugc_post(
            access_token, connection.linkedin_member_urn, content["body"], asset_urn
        )
    except LinkedInError:
        logger.exception("LinkedIn publish failed for job %s, will retry", job.id)
        await _release_claim(job.id)
        raise  # transient (rate limit, 5xx, etc.) — bounded retry then DLX

    async with async_session_factory() as session:
        row = await session.get(PublishJob, job.id)
        row.status = "published"
        row.linkedin_post_id = linkedin_post_id
        row.completed_at = datetime.now(UTC)
        await session.commit()

    await _publish(
        "post.published",
        {
            "scheduled_post_id": str(scheduled_post_id),
            "account_id": str(account_id),
            "content_id": str(content_id),
            "linkedin_post_id": linkedin_post_id,
        },
    )


async def _upload_image(publish_job_id: uuid.UUID, access_token: str, member_urn: str, image_url: str) -> str:
    async with httpx.AsyncClient(timeout=30.0) as client:
        image_response = await client.get(image_url)
        image_response.raise_for_status()
        image_bytes = image_response.content

    upload_url, asset_urn = await linkedin_client.register_image_upload(access_token, member_urn)
    await linkedin_client.upload_image_binary(upload_url, access_token, image_bytes)

    async with async_session_factory() as session:
        session.add(PostMedia(publish_job_id=publish_job_id, asset_urn=asset_urn, image_url=image_url))
        await session.commit()

    return asset_urn


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel, DOMAIN_EVENTS_EXCHANGE, QUEUE_NAME, routing_keys=["content.scheduled"]
    )
    await consume(channel, queue, DOMAIN_EVENTS_EXCHANGE, _handle_content_scheduled, _is_processed, _mark_processed)
    logger.info("social-publishing consumer listening on %s", QUEUE_NAME)
