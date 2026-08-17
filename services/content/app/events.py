import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import select

from app.db import async_session_factory
from app.models import Content, ContentVersion, ProcessedEvent
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("content.events")

AI_EVENTS_EXCHANGE = "ai_events"
SCRAPER_EVENTS_EXCHANGE = "scraper_events"
DOMAIN_EVENTS_EXCHANGE = "domain_events"
GENERATION_QUEUE = "content.ai_generation_completed"
SCRAPE_QUEUE = "content.scrape_completed"

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
    try:
        channel = await get_channel()
        await publish_event(channel, DOMAIN_EVENTS_EXCHANGE, routing_key, _envelope(routing_key, data))
    except Exception:  # noqa: BLE001
        logger.exception("failed to publish %s", routing_key)


async def publish_content_created(content: Content) -> None:
    await _publish("content.created", {"content_id": str(content.id), "account_id": str(content.account_id)})


async def publish_content_updated(content: Content) -> None:
    await _publish(
        "content.updated",
        {"content_id": str(content.id), "account_id": str(content.account_id), "status": content.status},
    )


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


async def _handle_generation_completed(payload: dict[str, Any]) -> None:
    data = payload["data"]
    if data.get("purpose") != "post":
        return

    account_id = uuid.UUID(data["account_id"])
    user_id = uuid.UUID(data["user_id"])
    generation_job_id = data["generation_job_id"]
    response_text = data.get("response_text", "")

    async with async_session_factory() as session:
        existing = await session.scalar(
            select(Content).where(Content.source_generation_job_id == generation_job_id)
        )
        if existing:
            return

        title = (response_text[:57] + "...") if len(response_text) > 60 else (response_text or "Untitled draft")
        content = Content(
            account_id=account_id,
            created_by_user_id=user_id,
            title=title or "Untitled draft",
            body=response_text,
            status="draft",
            source_generation_job_id=generation_job_id,
        )
        session.add(content)
        await session.flush()

        session.add(
            ContentVersion(
                content_id=content.id,
                version_number=1,
                title=content.title,
                body=content.body,
                image_url=content.image_url,
                edited_by_user_id=user_id,
            )
        )
        await session.commit()

    await publish_content_created(content)


async def _handle_scrape_completed(payload: dict[str, Any]) -> None:
    """Turns a completed scrape into a usable draft, closing the gap where
    Scraper's output previously had no automated path into content creation
    — a user would otherwise have to manually copy scraped text into a
    generation prompt."""
    data = payload["data"]
    account_id_raw = data.get("account_id")
    user_id_raw = data.get("user_id")
    if not account_id_raw or not user_id_raw:
        logger.warning("scrape.completed missing account_id/user_id, skipping draft creation: %s", data)
        return

    document_id = data["document_id"]
    account_id = uuid.UUID(account_id_raw)
    user_id = uuid.UUID(user_id_raw)
    title = data.get("title") or data.get("url", "Untitled scrape")
    excerpt = data.get("text_excerpt", "")

    async with async_session_factory() as session:
        existing = await session.scalar(
            select(Content).where(Content.source_scrape_document_id == document_id)
        )
        if existing:
            return

        content = Content(
            account_id=account_id,
            created_by_user_id=user_id,
            title=title[:255],
            body=excerpt,
            status="draft",
            source_scrape_document_id=document_id,
        )
        session.add(content)
        await session.flush()

        session.add(
            ContentVersion(
                content_id=content.id,
                version_number=1,
                title=content.title,
                body=content.body,
                image_url=content.image_url,
                edited_by_user_id=user_id,
            )
        )
        await session.commit()

    await publish_content_created(content)


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel, AI_EVENTS_EXCHANGE, GENERATION_QUEUE, routing_keys=["ai.generation_completed"]
    )
    await consume(channel, queue, AI_EVENTS_EXCHANGE, _handle_generation_completed, _is_processed, _mark_processed)
    logger.info("content consumer listening on %s", GENERATION_QUEUE)

    scrape_queue = await declare_durable_queue_with_dlx(
        channel, SCRAPER_EVENTS_EXCHANGE, SCRAPE_QUEUE, routing_keys=["scrape.completed"]
    )
    await consume(channel, scrape_queue, SCRAPER_EVENTS_EXCHANGE, _handle_scrape_completed, _is_processed, _mark_processed)
    logger.info("content consumer listening on %s", SCRAPE_QUEUE)
