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


class SubscriptionResponse(BaseModel):
    account_id: str
    plan_tier: str
    status: str
    grace_period_ends_at: datetime | None


class InvoiceResponse(BaseModel):
    id: str
    amount_cents: int
    currency: str
    status: str
    created_at: datetime


class RefundRequest(BaseModel):
    invoice_id: str
    reason: str | None = None


class RefundResponse(BaseModel):
    id: str
    amount_cents: int
    status: str = "issued"
