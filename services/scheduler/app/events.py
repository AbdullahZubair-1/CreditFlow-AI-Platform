import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika

from app.db import async_session_factory
from app.models import AvailableContent, ProcessedEvent
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("scheduler.events")

DOMAIN_EVENTS_EXCHANGE = "domain_events"
CONTENT_QUEUE = "scheduler.content_created"

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


async def publish_content_scheduled(scheduled_post_id: str, account_id: str, content_id: str) -> None:
    """Deliberately lets publish failures propagate (unlike most other
    best-effort publishers in this codebase): this event is what tells
    Social Publishing a post is due, so the caller (app/tasks.py) needs to
    know it failed and hold off marking the occurrence fired, rather than
    silently losing it. Publisher confirms on the underlying channel mean
    a broker-side failure surfaces here as an exception too."""
    channel = await get_channel()
    await publish_event(
        channel,
        DOMAIN_EVENTS_EXCHANGE,
        "content.scheduled",
        _envelope(
            "content.scheduled",
            {"scheduled_post_id": scheduled_post_id, "account_id": account_id, "content_id": content_id},
        ),
    )


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


async def _handle_content_created(payload: dict[str, Any]) -> None:
    data = payload["data"]
    content_id = uuid.UUID(data["content_id"])
    account_id = uuid.UUID(data["account_id"])

    async with async_session_factory() as session:
        existing = await session.get(AvailableContent, content_id)
        if existing:
            return
        # content.created always fires for a brand-new draft, so "draft"
        # is the correct starting status regardless of what a later
        # content.updated redelivery might otherwise suggest.
        session.add(AvailableContent(content_id=content_id, account_id=account_id, status="draft"))
        await session.commit()


async def _handle_content_updated(payload: dict[str, Any]) -> None:
    """Keeps the cached status in sync with Content's actual status
    machine (draft -> approved -> published) — without this, Scheduler
    would only ever know a content item as "draft" (whatever it was at
    creation) and could never actually enforce "only approved content can
    be scheduled"."""
    data = payload["data"]
    content_id = uuid.UUID(data["content_id"])
    status = data.get("status")
    if not status:
        return

    async with async_session_factory() as session:
        row = await session.get(AvailableContent, content_id)
        if not row:
            # content.updated arrived before content.created's own
            # redelivery settled, or the cache row was never created for
            # some other reason — nothing to update yet.
            return
        row.status = status
        await session.commit()


async def _route_domain_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "content.created":
        await _handle_content_created(payload)
    elif event_type == "content.updated":
        await _handle_content_updated(payload)


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel, DOMAIN_EVENTS_EXCHANGE, CONTENT_QUEUE, routing_keys=["content.created", "content.updated"]
    )
    await consume(channel, queue, DOMAIN_EVENTS_EXCHANGE, _route_domain_event, _is_processed, _mark_processed)
    logger.info("scheduler consumer listening on %s", CONTENT_QUEUE)
