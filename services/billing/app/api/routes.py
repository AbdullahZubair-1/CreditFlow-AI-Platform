import uuid
from datetime import UTC, datetime, timedelta

import stripe
from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import stripe_client
from app.core.config import PLAN_DISPLAY_PRICES_CENTS, PLAN_PRICE_IDS, REFUND_RATE, REFUND_WINDOW_DAYS, settings
from app.core.database import get_session
from app.core.identity import Identity, require_identity
from app.models import BillingAccount, Invoice, Refund, Subscription
from app.services.outbox import add_outbox_event
from app.schemas import (
    CheckoutSessionRequest,
    CheckoutSessionResponse,
    CreditsPricingResponse,
    DirectCreditPurchaseRequest,
    InvoiceResponse,
    OneTimeCheckoutRequest,
    PlanChangeResponse,
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


@router.get("/internal/revenue")
async def internal_get_revenue(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Service-to-service only — backs the Admin/Ops Service's SuperAdmin
    revenue view (both the per-account breakdown and the platform-wide
    total, which the Admin Service computes by summing this list rather
    than needing a second endpoint). One grouped query rather than N
    per-account calls, unlike the other /internal/* lookups here, since
    the SuperAdmin directory needs every account's figure at once."""
    rows = await session.execute(
        select(Invoice.account_id, func.sum(Invoice.amount_cents))
        .where(Invoice.status == "paid")
        .group_by(Invoice.account_id)
    )
    return [{"account_id": str(account_id), "total_revenue_cents": total} for account_id, total in rows.all()]


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


@router.post("/internal/checkout-sessions/one-time", response_model=CheckoutSessionResponse)
async def create_one_time_checkout_session(
    body: OneTimeCheckoutRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> CheckoutSessionResponse:
    """Service-to-service only — the Gateway explicitly rejects any
    /internal/* path on its proxy routes (see _reject_internal_paths in
    services/gateway/app/api/routes.py), so this is reachable only via a
    direct container-to-container call, not through the public internet.
    That matters here specifically: amount_cents and metadata are both
    caller-controlled, with no server-side price computation of their own
    — fine for a trusted internal caller (Credits computes the real price
    itself before calling this), but it would let an arbitrary frontend
    caller request, say, a $0.01 checkout tagged with metadata claiming a
    $500 marketplace purchase completed. Used by Credits/Marketplace to
    charge an account for a one-off purchase; the caller passes the
    buyer's own account identity headers through, same as any
    Gateway-proxied call would, and arbitrary metadata that a Billing
    webhook consumer downstream (see events.py) uses to route the
    resulting `checkout.session.completed` event back to the right
    domain event."""
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


@router.get("/credits/pricing", response_model=CreditsPricingResponse)
async def get_credits_pricing() -> CreditsPricingResponse:
    return CreditsPricingResponse(cents_per_credit=settings.cents_per_credit)


@router.post("/credits/checkout-session", response_model=CheckoutSessionResponse)
async def create_credit_purchase_checkout_session(
    body: DirectCreditPurchaseRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> CheckoutSessionResponse:
    """Direct credit purchase, separate from subscribing to a plan — the
    price and metadata are computed here, server-side, from
    body.credits_amount alone; unlike /internal/checkout-sessions/one-time
    above, this endpoint is public (Gateway-reachable) specifically
    because it never trusts a caller-supplied amount_cents or metadata."""
    if body.credits_amount <= 0:
        raise ApiError("invalid_amount", "credits_amount must be positive.", 400)

    billing_account = await session.get(BillingAccount, uuid.UUID(identity.account_id))
    if not billing_account:
        raise ApiError(
            "billing_not_ready",
            "This account's Stripe customer hasn't been provisioned yet. Try again shortly.",
            409,
        )

    amount_cents = body.credits_amount * settings.cents_per_credit
    try:
        checkout_url = stripe_client.create_one_time_checkout_session(
            billing_account.stripe_customer_id,
            amount_cents,
            "usd",
            f"{body.credits_amount} CreditFlow credits",
            {
                "purpose": "credit_purchase",
                "account_id": identity.account_id,
                "credits_amount": str(body.credits_amount),
            },
            body.success_url,
            body.cancel_url,
        )
    except stripe.error.StripeError as exc:  # noqa: BLE001
        raise ApiError("stripe_error", str(exc), 502) from exc

    return CheckoutSessionResponse(checkout_url=checkout_url)


@router.patch("/subscription", response_model=PlanChangeResponse)
async def update_subscription(
    body: UpdateSubscriptionRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> PlanChangeResponse:
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

    # Idempotent no-op: a double-submit of the same target plan (e.g. a
    # double click before the button disabled) must not re-run a downgrade's
    # wallet credit a second time, or send the browser to a second upgrade
    # checkout for a plan it's already on.
    if subscription.plan_tier == body.plan:
        return PlanChangeResponse(subscription=_to_subscription_response(subscription))

    try:
        price_delta_cents = stripe_client.preview_plan_change(subscription.stripe_subscription_id, body.plan)
    except stripe.error.StripeError as exc:  # noqa: BLE001
        raise ApiError("stripe_error", str(exc), 502) from exc

    if price_delta_cents > 0:
        # Upgrade — collect the exact prorated difference via a real
        # Checkout page first; the plan itself only switches once that
        # payment's webhook actually confirms success (see
        # _apply_checkout_session_completed's "plan_upgrade" branch).
        # Applying the plan change here and hoping the background charge
        # succeeds (the old behavior) meant a declined card still got the
        # new tier's features and credits immediately.
        billing_account = await session.get(BillingAccount, uuid.UUID(identity.account_id))
        checkout_url = stripe_client.create_one_time_checkout_session(
            billing_account.stripe_customer_id,
            price_delta_cents,
            "usd",
            f"Upgrade to CreditFlow {body.plan.title()}",
            {"purpose": "plan_upgrade", "account_id": identity.account_id, "new_plan": body.plan},
            body.success_url,
            body.cancel_url,
        )
        return PlanChangeResponse(checkout_url=checkout_url)

    # Downgrade — applies immediately (nothing to wait on: we're giving
    # money back, not collecting it). price_delta_cents is Stripe's own
    # exact proration credit for the unused time on the pricier plan;
    # 95% of it goes to the account's wallet (see Credits' WalletLedger),
    # matching this platform's existing 95%-refunded/5%-retained policy
    # (REFUND_RATE, used identically for the 7-day invoice refund above).
    stripe_client.modify_subscription(subscription.stripe_subscription_id, body.plan, proration_behavior="none")
    subscription.plan_tier = body.plan

    credit_cents = -price_delta_cents
    wallet_credit_cents = int(credit_cents * REFUND_RATE) if credit_cents > 0 else 0
    if wallet_credit_cents > 0:
        add_outbox_event(
            session,
            "plan.downgrade_credited",
            {
                "account_id": identity.account_id,
                "wallet_credit_cents": wallet_credit_cents,
                "reference_id": str(uuid.uuid4()),
            },
        )

    add_outbox_event(
        session, "subscription.updated", {"account_id": identity.account_id, "plan_tier": body.plan}
    )
    await session.commit()

    return PlanChangeResponse(
        subscription=_to_subscription_response(subscription),
        wallet_credit_cents=wallet_credit_cents or None,
    )


def _to_subscription_response(subscription: Subscription) -> SubscriptionResponse:
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
    # Read-only, so no _require_owner here — any member can see invoice
    # history, they just can't act on it (checkout/change plan/refund are
    # still owner-only, both here and via the Gateway's owner-tier gate on
    # every non-GET billing request).
    rows = await session.scalars(
        select(Invoice)
        .where(Invoice.account_id == uuid.UUID(identity.account_id))
        .order_by(Invoice.created_at.desc())
    )
    invoices = rows.all()

    # Whether an invoice has already been refunded was previously tracked
    # only in the frontend's own in-memory state right after a successful
    # refund click — reloading the page (or any other user/session ever
    # viewing this list) had no way to know, since nothing here ever told
    # the client. One grouped query rather than one refund lookup per
    # invoice.
    refunded_by_invoice = dict(
        (
            await session.execute(
                select(Refund.invoice_id, Refund.amount_cents).where(
                    Refund.invoice_id.in_([i.id for i in invoices])
                )
            )
        ).all()
    )

    return [
        InvoiceResponse(
            id=str(i.id),
            amount_cents=i.amount_cents,
            currency=i.currency,
            status=i.status,
            created_at=i.created_at,
            refunded_amount_cents=refunded_by_invoice.get(i.id),
        )
        for i in invoices
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

    if datetime.now(UTC) - invoice.created_at > timedelta(days=REFUND_WINDOW_DAYS):
        raise ApiError(
            "refund_window_expired",
            f"Refunds are only available within {REFUND_WINDOW_DAYS} days of the charge.",
            400,
        )

    existing_refund = await session.scalar(select(Refund).where(Refund.invoice_id == invoice.id))
    if existing_refund:
        raise ApiError("already_refunded", "This invoice has already been refunded.", 409)

    # 95% of the original charge — the remaining 5% is a retained
    # processing/cancellation fee, not refunded.
    refund_amount_cents = int(invoice.amount_cents * REFUND_RATE)

    try:
        # Stripe's 2025-03-31 "Basil" API version removed the Invoice
        # object's top-level payment_intent field (an invoice can now have
        # multiple partial payments) — the payment intent for a payment now
        # only resolves through the expanded payments list.
        stripe_invoice = stripe.Invoice.retrieve(
            invoice.stripe_invoice_id, expand=["payments.data.payment.payment_intent"]
        )
        payments = stripe_invoice["payments"]["data"]
        if not payments:
            raise ApiError("stripe_error", "This invoice has no recorded payment to refund.", 502)
        payment_intent_id = payments[0]["payment"]["payment_intent"]["id"]
        refund = stripe_client.create_refund(payment_intent_id, refund_amount_cents, body.reason)
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
    #
    # invoice_id here MUST be the Stripe invoice id, not this row's own
    # internal UUID: the original purchase_grant ledger entry (see
    # _apply_invoice_paid below) was recorded with reference_id set to the
    # Stripe invoice id, since that's what the invoice.paid webhook carries.
    # Publishing the internal UUID instead meant Credits' clawback lookup
    # (keyed on that same reference_id) could never find the grant it was
    # supposed to claw back — every refund silently no-op'd the clawback.
    add_outbox_event(
        session,
        "refund.issued",
        {
            "account_id": identity.account_id,
            "invoice_id": invoice.stripe_invoice_id,
            "amount_cents": refund.amount,
        },
    )

    # A refunded invoice was a real subscription billing cycle (Stripe only
    # generates Invoice objects for subscriptions here — one-time credit
    # purchases go through checkout.session.completed instead), so refunding
    # it means giving up that plan. Cancel the Stripe subscription itself
    # (not just flip our own plan_tier) so the account doesn't get billed
    # again next cycle and silently flipped back to paid on the next
    # invoice.paid webhook, contradicting the refund. Same downgrade shape
    # as the dunning scanner (app/dunning.py) uses, reusing the same
    # already-verified sync path to User/Tenant's Account.plan_tier.
    subscription = await session.scalar(
        select(Subscription).where(Subscription.account_id == uuid.UUID(identity.account_id))
    )
    if subscription and subscription.plan_tier != "free":
        if subscription.stripe_subscription_id:
            try:
                stripe_client.cancel_subscription(subscription.stripe_subscription_id)
            except stripe.error.StripeError as exc:  # noqa: BLE001
                raise ApiError("stripe_error", str(exc), 502) from exc

        subscription.plan_tier = "free"
        subscription.status = "downgraded"
        subscription.grace_period_ends_at = None
        add_outbox_event(
            session, "subscription.downgraded", {"account_id": identity.account_id, "plan_tier": "free"}
        )

    await session.commit()

    return RefundResponse(id=str(refund_row.id), amount_cents=refund_row.amount_cents)
