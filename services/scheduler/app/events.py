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
        session.add(AvailableContent(content_id=content_id, account_id=account_id))
        await session.commit()


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel, DOMAIN_EVENTS_EXCHANGE, CONTENT_QUEUE, routing_keys=["content.created"]
    )
    await consume(channel, queue, DOMAIN_EVENTS_EXCHANGE, _handle_content_created, _is_processed, _mark_processed)
    logger.info("scheduler consumer listening on %s", CONTENT_QUEUE)
