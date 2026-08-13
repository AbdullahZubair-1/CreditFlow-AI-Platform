import uuid

import stripe
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import stripe_client
from app.config import PLAN_DISPLAY_PRICES_CENTS, PLAN_PRICE_IDS
from app.db import get_session
from app.identity import Identity, require_identity
from app.models import BillingAccount, Invoice, Refund, Subscription
from app.outbox import add_outbox_event
from app.schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    InvoiceResponse,
    OneTimeCheckoutRequest,
    PlanResponse,
    RefundRequest,
    RefundResponse,
    SubscriptionResponse,
    UpdateSubscriptionRequest,
)
from py_shared.errors import ApiError

router = APIRouter()


def _require_owner(identity: Identity) -> None:
    if identity.role != "owner":
        raise ApiError("forbidden", "Only the account owner can manage billing.", 403)


@router.get("/plans", response_model=list[PlanResponse])
async def list_plans() -> list[PlanResponse]:
    return [
        PlanResponse(tier=tier, display_price_cents=PLAN_DISPLAY_PRICES_CENTS[tier], stripe_price_id=price_id)
        for tier, price_id in PLAN_PRICE_IDS.items()
    ]


@router.get("/internal/accounts/{account_id}/subscription")
async def internal_get_subscription(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    """Service-to-service only — the Gateway explicitly rejects any
    /internal/* path on its proxy routes. Backs the Admin/Ops Service's
    per-account overview, which needs any account's plan tier, not just
    the caller's own (GET /subscription above is identity-scoped)."""
    subscription = await session.scalar(select(Subscription).where(Subscription.account_id == account_id))
    if not subscription:
        raise ApiError("not_found", "No subscription found for this account.", 404)
    return {"account_id": str(account_id), "plan_tier": subscription.plan_tier, "status": subscription.status}


@router.get("/subscription", response_model=SubscriptionResponse)
async def get_subscription(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> SubscriptionResponse:
    subscription = await session.scalar(
        select(Subscription).where(Subscription.account_id == uuid.UUID(identity.account_id))
    )
    if not subscription:
        raise ApiError("not_found", "No subscription found for this account.", 404)

    return SubscriptionResponse(
        account_id=str(subscription.account_id),
        plan_tier=subscription.plan_tier,
        status=subscription.status,
        grace_period_ends_at=subscription.grace_period_ends_at,
    )


@router.post("/checkout-session", response_model=CheckoutSessionResponse)
async def create_checkout_session(
    body: CheckoutSessionRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> CheckoutSessionResponse:
    _require_owner(identity)

    if body.plan not in PLAN_PRICE_IDS or PLAN_PRICE_IDS[body.plan] is None:
        raise ApiError("invalid_plan", f"Unknown or non-purchasable plan '{body.plan}'.", 400)

    billing_account = await session.get(BillingAccount, uuid.UUID(identity.account_id))
    if not billing_account:
        raise ApiError(
            "billing_not_ready",
            "This account's Stripe customer hasn't been provisioned yet. Try again shortly.",
            409,
        )

    try:
        checkout_url = stripe_client.create_checkout_session(
            billing_account.stripe_customer_id, body.plan, body.success_url, body.cancel_url
        )
    except stripe.error.StripeError as exc:  # noqa: BLE001
        raise ApiError("stripe_error", str(exc), 502) from exc

    return CheckoutSessionResponse(checkout_url=checkout_url)


@router.post("/checkout-sessions/one-time", response_model=CheckoutSessionResponse)
async def create_one_time_checkout_session(
    body: OneTimeCheckoutRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> CheckoutSessionResponse:
    """Used by other services (e.g. Credits/Marketplace) to charge an
    account for a one-off purchase — the caller passes the buyer's own
    account identity headers through, same as any Gateway-proxied call, and
    arbitrary metadata that a Billing webhook consumer downstream (see
    events.py) uses to route the resulting `checkout.session.completed`
    event back to the right domain event."""
    billing_account = await session.get(BillingAccount, uuid.UUID(identity.account_id))
    if not billing_account:
        raise ApiError(
            "billing_not_ready",
            "This account's Stripe customer hasn't been provisioned yet. Try again shortly.",
            409,
        )

    try:
        checkout_url = stripe_client.create_one_time_checkout_session(
            billing_account.stripe_customer_id,
            body.amount_cents,
            body.currency,
            body.description,
            body.metadata,
            body.success_url,
            body.cancel_url,
        )
    except stripe.error.StripeError as exc:  # noqa: BLE001
        raise ApiError("stripe_error", str(exc), 502) from exc

    return CheckoutSessionResponse(checkout_url=checkout_url)


@router.patch("/subscription", response_model=SubscriptionResponse)
async def update_subscription(
    body: UpdateSubscriptionRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> SubscriptionResponse:
    _require_owner(identity)

    subscription = await session.scalar(
        select(Subscription).where(Subscription.account_id == uuid.UUID(identity.account_id))
    )
    if not subscription:
        raise ApiError("not_found", "No subscription found for this account.", 404)
    if not subscription.stripe_subscription_id:
        raise ApiError(
            "no_active_subscription",
            "Account has no active paid subscription to modify; use /checkout-session first.",
            409,
        )
    if body.plan not in PLAN_PRICE_IDS or PLAN_PRICE_IDS[body.plan] is None:
        raise ApiError("invalid_plan", f"Unknown or non-purchasable plan '{body.plan}'.", 400)

    try:
        stripe_client.modify_subscription(subscription.stripe_subscription_id, body.plan)
    except stripe.error.StripeError as exc:  # noqa: BLE001
        raise ApiError("stripe_error", str(exc), 502) from exc

    subscription.plan_tier = body.plan
    add_outbox_event(
        session, "subscription.updated", {"account_id": identity.account_id, "plan_tier": body.plan}
    )
    await session.commit()

    return SubscriptionResponse(
        account_id=str(subscription.account_id),
        plan_tier=subscription.plan_tier,
        status=subscription.status,
        grace_period_ends_at=subscription.grace_period_ends_at,
    )


@router.get("/invoices", response_model=list[InvoiceResponse])
async def list_invoices(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> list[InvoiceResponse]:
    _require_owner(identity)

    rows = await session.scalars(
        select(Invoice)
        .where(Invoice.account_id == uuid.UUID(identity.account_id))
        .order_by(Invoice.created_at.desc())
    )
    return [
        InvoiceResponse(
            id=str(i.id), amount_cents=i.amount_cents, currency=i.currency, status=i.status, created_at=i.created_at
        )
        for i in rows.all()
    ]


@router.post("/refunds", response_model=RefundResponse, status_code=201)
async def create_refund(
    body: RefundRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> RefundResponse:
    _require_owner(identity)

    invoice = await session.get(Invoice, uuid.UUID(body.invoice_id))
    if not invoice or invoice.account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Invoice not found for this account.", 404)

    try:
        stripe_invoice = stripe.Invoice.retrieve(invoice.stripe_invoice_id)
        refund = stripe_client.create_refund(stripe_invoice["payment_intent"], body.reason)
    except stripe.error.StripeError as exc:  # noqa: BLE001
        raise ApiError("stripe_error", str(exc), 502) from exc

    refund_row = Refund(
        account_id=uuid.UUID(identity.account_id),
        invoice_id=invoice.id,
        stripe_refund_id=refund.id,
        amount_cents=refund.amount,
        reason=body.reason,
    )
    session.add(refund_row)

    # Refunds are triggered by us (not learned from a webhook), so the
    # refund.issued domain event is written to the outbox right here, in
    # the same transaction as the refund row — the Credits Service (a
    # later slice) will consume it to claw back any associated grant.
    add_outbox_event(
        session,
        "refund.issued",
        {"account_id": identity.account_id, "invoice_id": str(invoice.id), "amount_cents": refund.amount},
    )
    await session.commit()

    return RefundResponse(id=str(refund_row.id), amount_cents=refund_row.amount_cents)
