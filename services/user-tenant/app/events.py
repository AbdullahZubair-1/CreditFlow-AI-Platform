import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import select

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
BILLING_EVENTS_EXCHANGE = "billing_events"
DOMAIN_EVENTS_EXCHANGE = "domain_events"
QUEUE_NAME = "user_tenant.user_registered"
BILLING_QUEUE_NAME = "user_tenant.billing_events"

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


async def publish_account_updated(account_id: str, plan_tier: str) -> None:
    channel = await get_channel()
    await publish_event(
        channel,
        DOMAIN_EVENTS_EXCHANGE,
        "account.updated",
        _envelope("account.updated", {"account_id": account_id, "plan_tier": plan_tier}),
    )


async def publish_member_joined(account_id: str, user_id: str, role: str) -> None:
    channel = await get_channel()
    await publish_event(
        channel,
        DOMAIN_EVENTS_EXCHANGE,
        "member.joined",
        _envelope("member.joined", {"account_id": account_id, "user_id": user_id, "role": role}),
    )


async def publish_invite_created(invite_id: str, account_id: str, email: str, token: str, role: str) -> None:
    """Added retroactively for the Notification Service — the spec's
    "Team invite flow: generate invite token, emit event for Notification
    Service to email the invitee" was never actually wired to publish
    anything until Notification existed to consume it."""
    channel = await get_channel()
    await publish_event(
        channel,
        DOMAIN_EVENTS_EXCHANGE,
        "invite.created",
        _envelope(
            "invite.created",
            {"invite_id": invite_id, "account_id": account_id, "email": email, "token": token, "role": role},
        ),
    )


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


async def _handle_user_registered(payload: dict[str, Any]) -> None:
    """The generic processed_events check in py_shared.rabbitmq.consume()
    only guards against redelivery *after* this handler's own commit and
    the outer processed_events row have both landed — a crash in between
    those two commits (exactly what a forced-restart test probes) would
    otherwise redeliver this event and create a second individual Account
    + owner membership for the same user, since nothing here checked for
    one already existing. A brand-new user has zero memberships, so
    "this user already has any membership at all" is a reliable,
    same-schema signal that this handler already ran for them."""
    data = payload["data"]
    user_id = data["user_id"]

    async with async_session_factory() as session:
        existing_membership = await session.scalar(
            select(AccountMember).where(AccountMember.user_id == uuid.UUID(user_id))
        )
        if existing_membership:
            return

        account = Account(type="individual", name=data.get("email", "Individual Account"))
        session.add(account)
        await session.flush()

        session.add(AccountMember(account_id=account.id, user_id=uuid.UUID(user_id), role="owner"))
        await session.commit()
        account_id = str(account.id)

    await publish_account_created(account_id, "individual", account.name)
    await publish_member_joined(account_id, user_id, "owner")


async def _handle_user_deleted(payload: dict[str, Any]) -> None:
    """Auth deletes the User row itself and has no way to reach into this
    service's schema to clean up membership — this is that cleanup.
    Deliberately only removes AccountMember rows, not the Account itself:
    an account's content/billing/credits history shouldn't vanish just
    because the (possibly former sole) owner deleted their login, and an
    account with zero remaining members is a harmless, inert row rather
    than something requiring a cross-service cascade this slice doesn't
    attempt."""
    data = payload["data"]
    user_id = uuid.UUID(data["user_id"])

    async with async_session_factory() as session:
        rows = await session.scalars(select(AccountMember).where(AccountMember.user_id == user_id))
        for row in rows:
            await session.delete(row)
        await session.commit()


async def _handle_invoice_paid(payload: dict[str, Any]) -> None:
    """Billing settles a payment and grants the plan_tier it billed for,
    but plan_tier itself lives on User/Tenant's accounts table (the
    dashboard header, seat limits, etc. all read it from here) — without
    this consumer, an account's displayed plan never actually changed after
    a real upgrade, only Billing's own subscription row did."""
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    plan_tier = data.get("plan_tier", "free")

    async with async_session_factory() as session:
        account = await session.get(Account, account_id)
        if not account or account.plan_tier == plan_tier:
            return  # nothing to do, or already applied (redelivery)

        account.plan_tier = plan_tier
        await session.commit()

    await publish_account_updated(str(account_id), plan_tier)


async def _route_billing_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "invoice.paid":
        await _handle_invoice_paid(payload)
    elif event_type in ("subscription.downgraded", "subscription.updated"):
        # subscription.updated fires from PATCH /billing/subscription (an
        # existing paid account switching plans, e.g. Pro -> Team) — a
        # completely separate path from the checkout-driven invoice.paid
        # flow above, and until now nothing here ever listened for it at
        # all: Billing's own Subscription.plan_tier flipped immediately,
        # but this service's Account.plan_tier (what every paid-feature
        # gate in the Gateway and frontend actually reads) never did,
        # so a mid-cycle plan change silently never unlocked anything.
        # Same shape (account_id, plan_tier) as invoice.paid, same apply
        # logic.
        await _handle_invoice_paid(payload)


async def _route_user_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "user.registered":
        await _handle_user_registered(payload)
    elif event_type == "user.deleted":
        await _handle_user_deleted(payload)


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel, USER_EVENTS_EXCHANGE, QUEUE_NAME, routing_keys=["user.registered", "user.deleted"]
    )
    await consume(
        channel,
        queue,
        USER_EVENTS_EXCHANGE,
        _route_user_event,
        _is_processed,
        _mark_processed,
    )
    logger.info("user-tenant consumer listening on %s", QUEUE_NAME)

    billing_queue = await declare_durable_queue_with_dlx(
        channel,
        BILLING_EVENTS_EXCHANGE,
        BILLING_QUEUE_NAME,
        routing_keys=["invoice.paid", "subscription.downgraded", "subscription.updated"],
    )
    await consume(channel, billing_queue, BILLING_EVENTS_EXCHANGE, _route_billing_event, _is_processed, _mark_processed)
    logger.info("user-tenant consumer listening on %s", BILLING_QUEUE_NAME)
