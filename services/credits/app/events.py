import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import select

from app.config import PLAN_CREDIT_GRANTS, settings
from app.db import async_session_factory
from app.ledger import append_entry, get_balance
from app.models import CreditsLedger, MarketplaceListing, ProcessedEvent
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("credits.events")

BILLING_EVENTS_EXCHANGE = "billing_events"
AI_EVENTS_EXCHANGE = "ai_events"
DOMAIN_EVENTS_EXCHANGE = "domain_events"
QUEUE_NAME = "credits.billing_events"
AI_QUEUE_NAME = "credits.ai_events"

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
        # Best-effort: the ledger write already committed and is the
        # source of truth. Unlike Billing (where the Outbox pattern is a
        # hard reliability requirement), losing a credits.* notification
        # here just delays Usage/Notification, so we log and move on
        # rather than blocking the caller on a broker hiccup.
        logger.exception("failed to publish %s", routing_key)


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


async def _maybe_emit_low_balance(account_id: uuid.UUID, balance: int) -> None:
    if balance < settings.low_balance_threshold:
        await _publish("credits.low_balance", {"account_id": str(account_id), "balance": balance})


async def _handle_invoice_paid(payload: dict[str, Any]) -> None:
    """The generic processed_events check only guards against redelivery
    *after* both this handler's commit and the outer processed_events row
    have landed — a crash in between (what a forced-restart test probes)
    would otherwise redeliver this event and append a second
    purchase_grant ledger row for the same invoice, double-crediting the
    account. reference_id + reason together are this handler's own,
    same-schema idempotency key."""
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    plan_tier = data.get("plan_tier", "free")
    grant = PLAN_CREDIT_GRANTS.get(plan_tier, 0)
    if grant <= 0:
        return

    async with async_session_factory() as session:
        already_granted = await session.scalar(
            select(CreditsLedger).where(
                CreditsLedger.reference_id == data["invoice_id"], CreditsLedger.reason == "purchase_grant"
            )
        )
        if already_granted:
            return

        entry = await append_entry(session, account_id, grant, "purchase_grant", data["invoice_id"])
        await session.commit()

    await _publish("credits.credited", {"account_id": str(account_id), "amount": grant, "reason": "purchase_grant"})
    await _maybe_emit_low_balance(account_id, entry.balance_after)


async def _handle_refund_issued(payload: dict[str, Any]) -> None:
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    invoice_id = data["invoice_id"]

    async with async_session_factory() as session:
        # Claw back exactly what was granted for this invoice, capped at
        # the current balance so a refund can never push an account
        # negative if the credits have already been spent — that leftover
        # shortfall is an accepted, documented simplification for this
        # slice rather than a hard error.
        granted = await session.scalar(
            select(CreditsLedger.delta).where(
                CreditsLedger.account_id == account_id,
                CreditsLedger.reference_id == invoice_id,
                CreditsLedger.reason == "purchase_grant",
            )
        )
        if not granted:
            return

        already_clawed_back = await session.scalar(
            select(CreditsLedger).where(
                CreditsLedger.reference_id == invoice_id, CreditsLedger.reason == "refund_clawback"
            )
        )
        if already_clawed_back:
            return

        current_balance = await get_balance(session, account_id)
        clawback = min(granted, current_balance)
        if clawback <= 0:
            return

        entry = await append_entry(session, account_id, -clawback, "refund_clawback", invoice_id)
        await session.commit()

    await _publish(
        "credits.debited", {"account_id": str(account_id), "amount": clawback, "reason": "refund_clawback"}
    )
    await _maybe_emit_low_balance(account_id, entry.balance_after)


async def _handle_marketplace_payment_completed(payload: dict[str, Any]) -> None:
    data = payload["data"]
    listing_id = uuid.UUID(data["listing_id"])
    buyer_account_id = uuid.UUID(data["buyer_account_id"])
    seller_account_id = uuid.UUID(data["seller_account_id"])

    async with async_session_factory() as session:
        listing = await session.get(MarketplaceListing, listing_id)
        if not listing or listing.status != "pending_payment":
            # Already settled (duplicate webhook redelivery) or in an
            # unexpected state — idempotent no-op either way.
            logger.info("skipping marketplace settlement for listing %s (status=%s)", listing_id, listing.status if listing else "missing")
            return

        seller_entry = await append_entry(
            session, seller_account_id, -listing.credits_amount, "marketplace_sale", str(listing_id)
        )
        buyer_entry = await append_entry(
            session, buyer_account_id, listing.credits_amount, "marketplace_purchase", str(listing_id)
        )

        listing.status = "sold"
        listing.buyer_account_id = buyer_account_id
        listing.sold_at = datetime.now(UTC)

        await session.commit()

    await _publish(
        "credits.debited",
        {"account_id": str(seller_account_id), "amount": listing.credits_amount, "reason": "marketplace_sale"},
    )
    await _publish(
        "credits.credited",
        {"account_id": str(buyer_account_id), "amount": listing.credits_amount, "reason": "marketplace_purchase"},
    )
    await _maybe_emit_low_balance(seller_account_id, seller_entry.balance_after)
    await _maybe_emit_low_balance(buyer_account_id, buyer_entry.balance_after)


async def _handle_credit_purchase_completed(payload: dict[str, Any]) -> None:
    """Direct credit purchase, separate from a plan's automatic grant —
    checkout_session_id (Stripe's own id for that checkout) is this
    handler's idempotency key, the same role invoice_id plays for
    _handle_invoice_paid, so a redelivered webhook can't double-grant."""
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    credits_amount = data["credits_amount"]
    checkout_session_id = data["checkout_session_id"]
    if credits_amount <= 0:
        return

    async with async_session_factory() as session:
        already_granted = await session.scalar(
            select(CreditsLedger).where(
                CreditsLedger.reference_id == checkout_session_id, CreditsLedger.reason == "direct_purchase"
            )
        )
        if already_granted:
            return

        entry = await append_entry(session, account_id, credits_amount, "direct_purchase", checkout_session_id)
        await session.commit()

    await _publish("credits.credited", {"account_id": str(account_id), "amount": credits_amount, "reason": "direct_purchase"})
    await _maybe_emit_low_balance(account_id, entry.balance_after)


async def _handle_generation_completed(payload: dict[str, Any]) -> None:
    """AI Generation only checks *quota* (Usage Service) before streaming —
    it has no notion of a credits balance. This is the other half of the
    spend loop: once a generation finishes and its real cost is known, debit
    that amount from the account's credits ledger. reference_id is the
    generation_job_id, which is unique per generation, so redelivery after a
    crash between this commit and processed_events landing can't double-bill
    the same job."""
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    generation_job_id = data["generation_job_id"]
    cost = data.get("cost_cents", 0)
    if cost <= 0:
        return

    async with async_session_factory() as session:
        already_debited = await session.scalar(
            select(CreditsLedger).where(
                CreditsLedger.reference_id == generation_job_id, CreditsLedger.reason == "ai_generation_debit"
            )
        )
        if already_debited:
            return

        # Cost is charged in full even if it pushes the balance negative —
        # the generation already happened and Usage already allowed it via
        # its own separate quota check, so there is nothing left to gate
        # here. A negative balance simply surfaces as "top up" pressure via
        # the low-balance event below, same as any other overspend.
        entry = await append_entry(session, account_id, -cost, "ai_generation_debit", generation_job_id)
        await session.commit()

    await _publish(
        "credits.debited", {"account_id": str(account_id), "amount": cost, "reason": "ai_generation_debit"}
    )
    await _maybe_emit_low_balance(account_id, entry.balance_after)


async def _route_billing_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "invoice.paid":
        await _handle_invoice_paid(payload)
    elif event_type == "refund.issued":
        await _handle_refund_issued(payload)
    elif event_type == "marketplace.payment_completed":
        await _handle_marketplace_payment_completed(payload)
    elif event_type == "credits.purchase_completed":
        await _handle_credit_purchase_completed(payload)


async def _route_ai_event(payload: dict[str, Any]) -> None:
    if payload.get("event_type") == "ai.generation_completed":
        await _handle_generation_completed(payload)


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel,
        BILLING_EVENTS_EXCHANGE,
        QUEUE_NAME,
        routing_keys=["invoice.paid", "refund.issued", "marketplace.payment_completed", "credits.purchase_completed"],
    )
    await consume(channel, queue, BILLING_EVENTS_EXCHANGE, _route_billing_event, _is_processed, _mark_processed)
    logger.info("credits consumer listening on %s", QUEUE_NAME)

    ai_queue = await declare_durable_queue_with_dlx(
        channel,
        AI_EVENTS_EXCHANGE,
        AI_QUEUE_NAME,
        routing_keys=["ai.generation_completed"],
    )
    await consume(channel, ai_queue, AI_EVENTS_EXCHANGE, _route_ai_event, _is_processed, _mark_processed)
    logger.info("credits consumer listening on %s", AI_QUEUE_NAME)
