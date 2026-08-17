import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import aio_pika
from sqlalchemy import select

from app import stripe_client
from app.config import PRICE_ID_TO_PLAN, settings
from app.db import async_session_factory
from app.models import BillingAccount, Invoice, ProcessedEvent, Subscription, SubscriptionEvent
from app.outbox import add_outbox_event
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection

logger = logging.getLogger("billing.events")

DOMAIN_EVENTS_EXCHANGE = "domain_events"
WEBHOOK_EVENTS_EXCHANGE = "webhook_events"
ACCOUNT_QUEUE = "billing.account_created"
WEBHOOK_QUEUE = "billing.stripe_webhooks"

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


async def _handle_account_created(payload: dict[str, Any]) -> None:
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    # accounts don't carry an email of their own; individual accounts are
    # named after the owner's email at creation time in the user-tenant
    # service, which is good enough for a Stripe Customer's display email.
    email_or_name = data.get("name", f"account-{account_id}")

    async with async_session_factory() as session:
        existing = await session.get(BillingAccount, account_id)
        if existing:
            return

        stripe_customer_id = stripe_client.create_customer(email_or_name)
        session.add(BillingAccount(account_id=account_id, stripe_customer_id=stripe_customer_id))
        session.add(Subscription(account_id=account_id, plan_tier="free", status="active"))
        await session.commit()


async def _handle_stripe_webhook(payload: dict[str, Any]) -> None:
    event = payload["data"]
    stripe_event_id = event["id"]
    event_type = event["type"]
    obj = event["data"]["object"]

    async with async_session_factory() as session:
        # Persist the raw webhook before any further processing, per the
        # reliability requirements — this is the durable write side of the
        # flow. It also doubles as this handler's real idempotency guard:
        # since the insert below and every _apply_* side effect commit in
        # this same transaction, "a SubscriptionEvent row for this
        # stripe_event_id already exists" reliably means "everything that
        # was ever going to happen for this event already happened,
        # atomically" — so redelivery after a crash between this
        # transaction committing and the outer processed_events row
        # committing (the exact gap a forced-restart test probes) safely
        # no-ops here instead of re-extending a dunning grace period or
        # double-emitting payment.failed/subscription.updated.
        existing = await session.scalar(
            select(SubscriptionEvent).where(SubscriptionEvent.stripe_event_id == stripe_event_id)
        )
        if existing:
            return

        session.add(SubscriptionEvent(stripe_event_id=stripe_event_id, event_type=event_type, raw_payload=event))

        if event_type == "invoice.paid":
            await _apply_invoice_paid(session, obj)
        elif event_type == "invoice.payment_failed":
            await _apply_payment_failed(session, obj)
        elif event_type in ("customer.subscription.created", "customer.subscription.updated"):
            await _apply_subscription_updated(session, obj)
        elif event_type == "checkout.session.completed":
            await _apply_checkout_session_completed(session, obj)

        await session.commit()


def _plan_tier_from_invoice_lines(invoice_obj: dict[str, Any]) -> str | None:
    """Reads the plan directly off the invoice's own line items (each
    carries the Stripe Price actually billed) instead of trusting the
    Subscription row's cached plan_tier — Stripe doesn't guarantee that
    customer.subscription.created/updated (which is what sets that cache,
    see _apply_subscription_updated) arrives before invoice.paid for the
    same checkout. Reading it wrong here silently granted zero credits
    for a real, paid Pro/Team invoice whenever the subscription event
    happened to process second."""
    lines = invoice_obj.get("lines", {}).get("data", [])
    if not lines:
        return None
    price = lines[0].get("price") or lines[0].get("plan") or {}
    return PRICE_ID_TO_PLAN.get(price.get("id"))


async def _apply_invoice_paid(session, invoice_obj: dict[str, Any]) -> None:
    account_id = await _account_id_for_customer(session, invoice_obj["customer"])
    if account_id is None:
        return

    existing = await session.scalar(
        select(Invoice).where(Invoice.stripe_invoice_id == invoice_obj["id"])
    )
    if existing:
        return

    session.add(
        Invoice(
            account_id=account_id,
            stripe_invoice_id=invoice_obj["id"],
            amount_cents=invoice_obj["amount_paid"],
            currency=invoice_obj["currency"],
            status="paid",
        )
    )

    subscription = await session.scalar(select(Subscription).where(Subscription.account_id == account_id))
    if subscription:
        subscription.status = "active"
        subscription.grace_period_ends_at = None

    # Prefer the plan read directly off this invoice's own line items;
    # only fall back to the (possibly not-yet-updated) Subscription row's
    # cached plan_tier if the invoice itself doesn't carry a recognized
    # Stripe Price (e.g. some non-subscription invoice types).
    plan_tier = _plan_tier_from_invoice_lines(invoice_obj) or (subscription.plan_tier if subscription else "free")

    add_outbox_event(
        session,
        "invoice.paid",
        {
            "account_id": str(account_id),
            "invoice_id": invoice_obj["id"],
            "amount_cents": invoice_obj["amount_paid"],
            # the Credits Service maps plan_tier -> credits granted
            "plan_tier": plan_tier,
        },
    )


async def _apply_checkout_session_completed(session, checkout_obj: dict[str, Any]) -> None:
    """Subscription checkouts settle via invoice.paid instead; the
    checkout.session.completed events we act on here are one-time
    purchases (see stripe_client.create_one_time_checkout_session) that
    carry no invoice and must be translated into a domain event of their
    own for the Credits Service to consume."""
    metadata = checkout_obj.get("metadata") or {}
    purpose = metadata.get("purpose")

    if purpose == "marketplace_purchase":
        add_outbox_event(
            session,
            "marketplace.payment_completed",
            {
                "listing_id": metadata["listing_id"],
                "buyer_account_id": metadata["buyer_account_id"],
                "seller_account_id": metadata["seller_account_id"],
                "amount_cents": checkout_obj["amount_total"],
            },
        )
    elif purpose == "credit_purchase":
        add_outbox_event(
            session,
            "credits.purchase_completed",
            {
                "account_id": metadata["account_id"],
                "credits_amount": int(metadata["credits_amount"]),
                # Stripe's checkout session id doubles as Credits' own
                # idempotency key for this grant (see its
                # _handle_credit_purchase_completed) — redelivery of this
                # same webhook event can't double-grant credits.
                "checkout_session_id": checkout_obj["id"],
            },
        )


async def _apply_payment_failed(session, invoice_obj: dict[str, Any]) -> None:
    account_id = await _account_id_for_customer(session, invoice_obj["customer"])
    if account_id is None:
        return

    subscription = await session.scalar(select(Subscription).where(Subscription.account_id == account_id))
    if subscription:
        subscription.status = "past_due"
        subscription.grace_period_ends_at = datetime.now(UTC) + timedelta(
            days=settings.dunning_grace_period_days
        )

    add_outbox_event(session, "payment.failed", {"account_id": str(account_id), "invoice_id": invoice_obj["id"]})

    # NOTE: automatically emitting subscription.downgraded once the grace
    # period elapses needs a periodic scanner — that arrives with the
    # Scheduler Service slice (Celery Beat). For now the grace deadline is
    # recorded on the subscription row and surfaced via GET /subscription
    # so an operator (or a fast-follow cron) can act on it.


async def _apply_subscription_updated(session, subscription_obj: dict[str, Any]) -> None:
    """Handles both customer.subscription.created (a brand-new checkout)
    and customer.subscription.updated (a plan change via a Stripe-side
    action, e.g. the customer portal) — either way, the source of truth
    for which plan is actually active is the Stripe Price attached to the
    subscription's line item, not anything CreditFlow's own /subscription
    PATCH endpoint may or may not have set. Without this, a brand-new
    subscription's plan_tier stayed "free" forever: nothing else in this
    webhook flow ever wrote it, since customer.subscription.created wasn't
    even routed here until now, and this handler previously only touched
    status, never plan_tier."""
    account_id = await _account_id_for_customer(session, subscription_obj["customer"])
    if account_id is None:
        return

    subscription = await session.scalar(select(Subscription).where(Subscription.account_id == account_id))
    if not subscription:
        return

    subscription.stripe_subscription_id = subscription_obj["id"]
    subscription.status = subscription_obj["status"]

    price_id = subscription_obj["items"]["data"][0]["price"]["id"]
    plan_tier = PRICE_ID_TO_PLAN.get(price_id)
    if plan_tier:
        subscription.plan_tier = plan_tier

    add_outbox_event(
        session,
        "subscription.updated",
        {
            "account_id": str(account_id),
            "status": subscription_obj["status"],
            "plan_tier": subscription.plan_tier,
        },
    )


async def _account_id_for_customer(session, stripe_customer_id: str) -> uuid.UUID | None:
    row = await session.scalar(
        select(BillingAccount).where(BillingAccount.stripe_customer_id == stripe_customer_id)
    )
    return row.account_id if row else None


async def start_consumers() -> None:
    channel = await get_channel()

    account_queue = await declare_durable_queue_with_dlx(
        channel, DOMAIN_EVENTS_EXCHANGE, ACCOUNT_QUEUE, routing_keys=["account.created"]
    )
    # "#" (not "*") because Stripe event types are themselves dot-separated
    # (e.g. "invoice.paid", "checkout.session.completed"), so the relayed
    # routing key "billing.<type>" can have more than two segments — "*"
    # only matches exactly one word and would silently miss those.
    webhook_queue = await declare_durable_queue_with_dlx(
        channel, WEBHOOK_EVENTS_EXCHANGE, WEBHOOK_QUEUE, routing_keys=["billing.#"]
    )

    await consume(channel, account_queue, DOMAIN_EVENTS_EXCHANGE, _handle_account_created, _is_processed, _mark_processed)
    await consume(channel, webhook_queue, WEBHOOK_EVENTS_EXCHANGE, _handle_stripe_webhook, _is_processed, _mark_processed)
    logger.info("billing consumers listening on %s and %s", ACCOUNT_QUEUE, WEBHOOK_QUEUE)
