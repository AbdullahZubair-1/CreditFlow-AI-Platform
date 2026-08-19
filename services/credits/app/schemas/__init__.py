from datetime import datetime

from pydantic import BaseModel


class BalanceResponse(BaseModel):
    account_id: str
    balance: int
    # Excludes the free signup bonus, which can never be listed on the
    # marketplace (see ledger.get_sellable_balance) — surfaced here so the
    # frontend can show "up to X sellable" without a second round trip.
    sellable_balance: int


class LedgerEntryResponse(BaseModel):
    id: str
    delta: int
    reason: str
    reference_id: str | None
    balance_after: int
    created_at: datetime


class CreateListingRequest(BaseModel):
    credits_amount: int
    price_cents: int


class ListingResponse(BaseModel):
    id: str
    seller_account_id: str
    credits_amount: int
    price_cents: int
    status: str
    created_at: datetime


class PurchaseListingRequest(BaseModel):
    success_url: str
    cancel_url: str


class PurchaseListingResponse(BaseModel):
    checkout_url: str


class WalletBalanceResponse(BaseModel):
    balance_cents: int


class WalletLedgerEntryResponse(BaseModel):
    id: str
    delta_cents: int
    reason: str
    reference_id: str | None
    balance_after_cents: int
    created_at: datetime


class CreatePayoutRequestRequest(BaseModel):
    amount_cents: int
    # Free text rather than a structured bank/PayPal form — there's no real
    # transfer integration behind this (see PayoutRequest's docstring), so
    # a SuperAdmin just needs enough to know where to actually send the
    # money by hand.
    destination: str


class PayoutRequestResponse(BaseModel):
    id: str
    account_id: str
    amount_cents: int
    destination: str
    status: str
    requested_at: datetime
    completed_at: datetime | None
