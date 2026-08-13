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
                    await publish_event(channel, EXCHANGE, row.routing_key, row.payload)
                    row.published = True
                    await session.commit()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("outbox poller iteration failed, will retry")

        await asyncio.sleep(settings.outbox_poll_interval_seconds)
