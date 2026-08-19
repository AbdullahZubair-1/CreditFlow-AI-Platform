import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika

from py_shared.rabbitmq import get_confirm_channel, get_connection, publish_event

EXCHANGE = "user_events"

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


async def publish_user_registered(user_id: str, email: str, verification_token: str) -> None:
    channel = await get_channel()
    await publish_event(channel, EXCHANGE, "user.registered", _envelope("user.registered", {
        "user_id": user_id,
        "email": email,
        # added for the Notification Service to build a working
        # verification link — the spec calls for exactly this ("generate
        # verification token, emit event for Notification Service to send
        # the email"), which the event payload didn't carry until now.
        "verification_token": verification_token,
    }))


async def publish_user_logged_in(user_id: str) -> None:
    channel = await get_channel()
    await publish_event(channel, EXCHANGE, "user.logged_in", _envelope("user.logged_in", {
        "user_id": user_id,
    }))


async def publish_user_deleted(user_id: str) -> None:
    """User-Tenant consumes this to remove the user's AccountMember rows
    across every account they belonged to — Auth owns identity, but
    membership lives in a different service/schema entirely, so deleting
    the User row here doesn't (and can't, via any FK) clean that up on
    its own."""
    channel = await get_channel()
    await publish_event(channel, EXCHANGE, "user.deleted", _envelope("user.deleted", {"user_id": user_id}))


async def publish_password_reset_requested(user_id: str, email: str, otp: str) -> None:
    channel = await get_channel()
    await publish_event(
        channel,
        EXCHANGE,
        "user.password_reset_requested",
        _envelope(
            "user.password_reset_requested",
            # otp added so Notification can actually email it — without it,
            # the OTP only ever reached the user via the dev-only response
            # field, which is not "works end-to-end by email" per the spec.
            {"user_id": user_id, "email": email, "otp": otp},
        ),
    )
