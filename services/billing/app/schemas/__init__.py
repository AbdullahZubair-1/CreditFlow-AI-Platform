from datetime import datetime

from pydantic import BaseModel


class PlanResponse(BaseModel):
    tier: str
    display_price_cents: int
    stripe_price_id: str | None


class CheckoutSessionRequest(BaseModel):
    plan: str
    success_url: str
    cancel_url: str


class CheckoutSessionResponse(BaseModel):
    checkout_url: str


class OneTimeCheckoutRequest(BaseModel):
    amount_cents: int
    currency: str = "usd"
    description: str
    metadata: dict[str, str] = {}
    success_url: str
    cancel_url: str


class DirectCreditPurchaseRequest(BaseModel):
    credits_amount: int
    success_url: str
    cancel_url: str


class CreditsPricingResponse(BaseModel):
    cents_per_credit: int


class UpdateSubscriptionRequest(BaseModel):
    plan: str
    # Only actually used for an upgrade (the new plan costs more) — that
    # path redirects to a real Stripe Checkout page for the price
    # difference rather than applying immediately, so it needs somewhere
    # to send the browser back to. A downgrade applies synchronously and
    # never touches these.
    success_url: str
    cancel_url: str


class SubscriptionResponse(BaseModel):
    account_id: str
    plan_tier: str
    status: str
    grace_period_ends_at: datetime | None


class PlanChangeResponse(BaseModel):
    # Upgrading sets checkout_url and leaves subscription unset — the plan
    # hasn't changed yet, and won't until that checkout's payment succeeds.
    # Downgrading (or a same-price/no-op change) applies immediately and
    # sets subscription instead, with wallet_credit_cents populated
    # whenever the downgrade actually generated a wallet credit.
    checkout_url: str | None = None
    subscription: SubscriptionResponse | None = None
    wallet_credit_cents: int | None = None


class InvoiceResponse(BaseModel):
    id: str
    amount_cents: int
    currency: str
    status: str
    created_at: datetime
    refunded_amount_cents: int | None = None


class RefundRequest(BaseModel):
    invoice_id: str
    reason: str | None = None


class RefundResponse(BaseModel):
    id: str
    amount_cents: int
    status: str = "issued"
