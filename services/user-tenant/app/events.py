import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika

from app.db import async_session_factory
from app.models import Account, AccountMember, ProcessedEvent
from py_shared.rabbitmq import (
    consume,
    declare_durable_queue_with_dlx,
    get_confirm_channel,
    get_connection,
    publish_event,
)

logger = logging.getLogger("user_tenant.events")

USER_EVENTS_EXCHANGE = "user_events"
DOMAIN_EVENTS_EXCHANGE = "domain_events"
QUEUE_NAME = "user_tenant.user_registered"

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


async def publish_account_created(account_id: str, account_type: str, name: str) -> None:
    channel = await get_channel()
    await publish_event(
        channel,
        DOMAIN_EVENTS_EXCHANGE,
        "account.created",
        _envelope("account.created", {"account_id": account_id, "type": account_type, "name": name}),
    )


async def publish_member_joined(account_id: str, user_id: str, role: str) -> None:
    channel = await get_channel()
    await publish_event(
        channel,
        DOMAIN_EVENTS_EXCHANGE,
        "member.joined",
        _envelope("member.joined", {"account_id": account_id, "user_id": user_id, "role": role}),
    )


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


async def _handle_user_registered(payload: dict[str, Any]) -> None:
    data = payload["data"]
    user_id = data["user_id"]

    async with async_session_factory() as session:
        account = Account(type="individual", name=data.get("email", "Individual Account"))
        session.add(account)
        await session.flush()

        session.add(AccountMember(account_id=account.id, user_id=uuid.UUID(user_id), role="owner"))
        await session.commit()
        account_id = str(account.id)

    await publish_account_created(account_id, "individual", account.name)
    await publish_member_joined(account_id, user_id, "owner")


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel, USER_EVENTS_EXCHANGE, QUEUE_NAME, routing_keys=["user.registered"]
    )
    await consume(
        channel,
        queue,
        USER_EVENTS_EXCHANGE,
        _handle_user_registered,
        _is_processed,
        _mark_processed,
    )
    logger.info("user-tenant consumer listening on %s", QUEUE_NAME)
