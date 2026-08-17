import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import select

from app.db import async_session_factory
from app.models import AuditLog, ProcessedEvent
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection

logger = logging.getLogger("admin.events")

# Every topic exchange in the platform — the spec's "Consumes: all
# events, topic-bound (#) for audit purposes." New exchanges added by
# future slices need a line here too; there's no way to discover them
# dynamically from RabbitMQ's client API without broker management
# permissions this service doesn't have.
AUDITED_EXCHANGES = [
    "user_events",
    "domain_events",
    "billing_events",
    "social_events",
    "scraper_events",
    "ai_events",
    "webhook_events",
    "usage_events",
]

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await get_connection()
        _channel = await get_confirm_channel(_connection)
    return _channel


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


def _extract_account_id(data: dict[str, Any]) -> uuid.UUID | None:
    raw = data.get("account_id")
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except (ValueError, TypeError):
        return None


def make_handler(source_exchange: str):
    async def _handle(payload: dict[str, Any]) -> None:
        event_id = payload.get("event_id")
        if not event_id:
            return  # nothing to key the audit row or idempotency check on

        data = payload.get("data") or {}
        occurred_at_raw = payload.get("occurred_at")
        try:
            occurred_at = datetime.fromisoformat(occurred_at_raw) if occurred_at_raw else datetime.now(UTC)
        except ValueError:
            occurred_at = datetime.now(UTC)

        async with async_session_factory() as session:
            # event_id has its own unique constraint, but the generic
            # processed_events check only guards against redelivery
            # *after* both this commit and the outer processed_events row
            # have landed. Without this check, a crash in between (what a
            # forced-restart test probes) wouldn't silently duplicate the
            # audit row on redelivery — the unique constraint would reject
            # the second insert with an IntegrityError, which the outer
            # consume() loop would treat as a real handler failure and
            # retry pointlessly until it lands in the DLQ, even though the
            # event was already correctly recorded the first time.
            existing = await session.scalar(select(AuditLog).where(AuditLog.event_id == event_id))
            if existing:
                return

            session.add(
                AuditLog(
                    event_id=event_id,
                    event_type=payload.get("event_type", "unknown"),
                    source_exchange=source_exchange,
                    account_id=_extract_account_id(data),
                    payload=payload,
                    occurred_at=occurred_at,
                )
            )
            await session.commit()

    return _handle


async def start_consumers() -> None:
    channel = await get_channel()

    for exchange_name in AUDITED_EXCHANGES:
        queue = await declare_durable_queue_with_dlx(
            channel, exchange_name, f"admin.audit.{exchange_name}", routing_keys=["#"]
        )
        await consume(channel, queue, exchange_name, make_handler(exchange_name), _is_processed, _mark_processed)

    logger.info("admin audit consumer listening on: %s", ", ".join(AUDITED_EXCHANGES))
