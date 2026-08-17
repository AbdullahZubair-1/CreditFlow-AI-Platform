"""Transactional Outbox: writers append a row to outbox_events in the same
DB transaction as their domain state change; a background poller (started
in main.py's lifespan) publishes each unpublished row to RabbitMQ with
publisher confirms and marks it published — so a crash between the DB
write and the publish can never lose or skip the event.
"""
import asyncio
import logging

import aio_pika
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db import async_session_factory
from app.models import OutboxEvent
from py_shared.rabbitmq import get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("billing.outbox")

EXCHANGE = "billing_events"


def _envelope(row: OutboxEvent) -> dict:
    """Wraps the raw domain payload in the same {event_id, event_type,
    occurred_at, data} shape every consumer of billing_events (User/Tenant's
    plan_tier sync, Credits' plan/refund/purchase grants) actually expects —
    every _handle_* on the receiving end reads payload["data"] and routes on
    payload["event_type"]. Publishing the bare payload dict instead (as this
    previously did) meant every one of those reads silently returned None: a
    real Stripe-confirmed upgrade never unlocked paid-plan features, a real
    plan's monthly credit grant never landed, and a real "buy extra credits"
    purchase never credited the ledger, because every consumer's routing
    check failed before it ever looked at the actual data. The outbox row's
    own primary key doubles as a stable event_id (unchanged across a
    publish-then-crash-before-mark-published retry, since it's assigned once
    at row creation), which is exactly what receivers' is_processed()
    idempotency check needs to dedupe that retry correctly.
    """
    return {
        "event_id": str(row.id),
        "event_type": row.routing_key,
        "occurred_at": row.created_at.isoformat(),
        "data": row.payload,
    }


def add_outbox_event(session: AsyncSession, routing_key: str, payload: dict) -> None:
    session.add(OutboxEvent(routing_key=routing_key, payload=payload))


async def run_outbox_poller() -> None:
    connection = await get_connection()
    channel = await get_confirm_channel(connection)

    while True:
        try:
            async with async_session_factory() as session:
                rows = (
                    await session.scalars(
                        select(OutboxEvent).where(OutboxEvent.published == False)  # noqa: E712
                    )
                ).all()

                for row in rows:
                    await publish_event(channel, EXCHANGE, row.routing_key, _envelope(row))
                    row.published = True
                    await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("outbox poller iteration failed, will retry")

        await asyncio.sleep(settings.outbox_poll_interval_seconds)
