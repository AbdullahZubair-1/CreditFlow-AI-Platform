import uuid

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import billing_client
from app.config import CENTS_PER_CREDIT, MARKETPLACE_MIN_DISCOUNT_PERCENT, PLAN_CREDIT_GRANTS
from app.db import get_session
from app.identity import Identity, require_identity
from app.ledger import get_balance, get_sellable_balance
from app.models import CreditsLedger, MarketplaceListing
from app.schemas import (
    BalanceResponse,
    CreateListingRequest,
    LedgerEntryResponse,
    ListingResponse,
    PurchaseListingRequest,
    PurchaseListingResponse,
)
from py_shared.errors import ApiError

router = APIRouter()

# Matches the Gateway's own OWNER_TIER_ROLES (owner + admin) — this service
# previously had zero server-side role checks of its own, relying entirely
# on the Gateway's now-relaxed blanket gate over the whole /credits/* prefix
# (see services/gateway/app/api/routes.py). Members can browse listings and
# see their own balance/transactions; only owner/admin can actually buy or
# sell (list, cancel a listing, or purchase — from the marketplace or
# directly), matching what was explicitly asked for.
OWNER_TIER_ROLES = {"owner", "admin"}


def _require_owner_tier(identity: Identity) -> None:
    if identity.role not in OWNER_TIER_ROLES:
        raise ApiError("forbidden", "This action requires an owner or admin role.", 403)


@router.get("/plan-grants")
async def get_plan_grants() -> dict[str, int]:
    """How many credits each subscription plan grants per billing cycle —
    lets the frontend show real numbers (e.g. "Pro: 1,000 credits/mo")
    instead of hardcoding a copy of this table that could drift."""
    return PLAN_CREDIT_GRANTS


@router.get("/balance", response_model=BalanceResponse)
async def get_my_balance(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> BalanceResponse:
    account_id = uuid.UUID(identity.account_id)
    balance = await get_balance(session, account_id)
    sellable = await get_sellable_balance(session, account_id)
    return BalanceResponse(account_id=identity.account_id, balance=balance, sellable_balance=sellable)


@router.get("/internal/accounts/{account_id}/balance")
async def internal_get_balance(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    """Service-to-service only — the Gateway explicitly rejects any
    /internal/* path on its proxy routes. Backs the Admin/Ops Service's
    per-account overview, which needs any account's balance, not just
    the caller's own (GET /balance above is identity-scoped)."""
    balance = await get_balance(session, account_id)
    return {"account_id": str(account_id), "balance": balance}


@router.get("/transactions", response_model=list[LedgerEntryResponse])
async def list_my_transactions(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> list[LedgerEntryResponse]:
    rows = await session.scalars(
        select(CreditsLedger)
        .where(CreditsLedger.account_id == uuid.UUID(identity.account_id))
        .order_by(CreditsLedger.created_at.desc())
    )
    return [
        LedgerEntryResponse(
            id=str(r.id),
            delta=r.delta,
            reason=r.reason,
            reference_id=r.reference_id,
            balance_after=r.balance_after,
            created_at=r.created_at,
        )
        for r in rows.all()
    ]


@router.get("/marketplace/listings", response_model=list[ListingResponse])
async def list_marketplace_listings(session: AsyncSession = Depends(get_session)) -> list[ListingResponse]:
    rows = await session.scalars(
        select(MarketplaceListing)
        .where(MarketplaceListing.status == "active")
        .order_by(MarketplaceListing.created_at.desc())
    )
    return [
        ListingResponse(
            id=str(listing.id),
            seller_account_id=str(listing.seller_account_id),
            credits_amount=listing.credits_amount,
            price_cents=listing.price_cents,
            status=listing.status,
            created_at=listing.created_at,
        )
        for listing in rows.all()
    ]


@router.post("/marketplace/listings", response_model=ListingResponse, status_code=201)
async def create_listing(
    body: CreateListingRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ListingResponse:
    _require_owner_tier(identity)
    if body.credits_amount <= 0 or body.price_cents <= 0:
        raise ApiError("invalid_listing", "credits_amount and price_cents must be positive.", 400)

    # Marketplace credits must always be at least MARKETPLACE_MIN_DISCOUNT_PERCENT
    # cheaper per credit than buying directly from us — cross-multiplied to
    # stay in exact integer cents rather than compare floats:
    # price_cents/credits_amount <= CENTS_PER_CREDIT * (1 - discount/100)
    #   <=> price_cents * 100 <= credits_amount * CENTS_PER_CREDIT * (100 - discount)
    if body.price_cents * 100 > body.credits_amount * CENTS_PER_CREDIT * (100 - MARKETPLACE_MIN_DISCOUNT_PERCENT):
        max_price_cents = (body.credits_amount * CENTS_PER_CREDIT * (100 - MARKETPLACE_MIN_DISCOUNT_PERCENT)) // 100
        raise ApiError(
            "price_too_high",
            f"Marketplace price must be at least {MARKETPLACE_MIN_DISCOUNT_PERCENT}% below the direct-purchase "
            f"rate (${CENTS_PER_CREDIT / 100:.2f}/credit) — max ${max_price_cents / 100:.2f} for "
            f"{body.credits_amount} credits.",
            400,
        )

    seller_account_id = uuid.UUID(identity.account_id)
    # Sellable, not raw, balance — the free signup bonus is usable for
    # generation but can never be listed for sale (see
    # ledger.get_sellable_balance).
    # NOTE: this checks available balance at listing time but doesn't lock
    # it — an account could list more credits across several concurrent
    # listings than it actually has. Acceptable simplification for this
    # slice; the debit only actually happens on a confirmed sale, at which
    # point a real shortfall would need reconciliation (documented, not
    # yet handled automatically).
    sellable_balance = await get_sellable_balance(session, seller_account_id)
    if sellable_balance < body.credits_amount:
        raise ApiError(
            "insufficient_balance",
            f"Not enough sellable credits to list — your free signup bonus can't be listed for sale "
            f"(you can sell up to {sellable_balance} credits).",
            400,
        )

    listing = MarketplaceListing(
        seller_account_id=seller_account_id,
        credits_amount=body.credits_amount,
        price_cents=body.price_cents,
        status="active",
    )
    session.add(listing)
    await session.commit()

    return ListingResponse(
        id=str(listing.id),
        seller_account_id=str(listing.seller_account_id),
        credits_amount=listing.credits_amount,
        price_cents=listing.price_cents,
        status=listing.status,
        created_at=listing.created_at,
    )


@router.delete("/marketplace/listings/{listing_id}", status_code=204)
async def cancel_listing(
    listing_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    _require_owner_tier(identity)
    listing = await session.get(MarketplaceListing, listing_id)
    if not listing or listing.seller_account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Listing not found.", 404)
    if listing.status != "active":
        raise ApiError("invalid_state", "Only active listings can be cancelled.", 409)

    listing.status = "cancelled"
    await session.commit()


@router.post("/marketplace/listings/{listing_id}/purchase", response_model=PurchaseListingResponse)
async def purchase_listing(
    listing_id: uuid.UUID,
    body: PurchaseListingRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> PurchaseListingResponse:
    _require_owner_tier(identity)
    listing = await session.get(MarketplaceListing, listing_id)
    if not listing or listing.status != "active":
        raise ApiError("not_found", "Listing not available for purchase.", 404)
    if listing.seller_account_id == uuid.UUID(identity.account_id):
        raise ApiError("invalid_purchase", "You cannot purchase your own listing.", 400)

    try:
        checkout_url = await billing_client.create_marketplace_checkout_session(
            buyer_account_id=identity.account_id,
            buyer_user_id=identity.user_id,
            buyer_role=identity.role,
            amount_cents=listing.price_cents,
            description=f"Purchase {listing.credits_amount} CreditFlow credits",
            metadata={
                "purpose": "marketplace_purchase",
                "listing_id": str(listing.id),
                "buyer_account_id": identity.account_id,
                "seller_account_id": str(listing.seller_account_id),
            },
            success_url=body.success_url,
            cancel_url=body.cancel_url,
        )
    except httpx.HTTPStatusError as exc:
        raise ApiError("billing_error", "Could not create checkout session for this purchase.", 502) from exc

    # Marked pending only after Billing confirms the checkout session was
    # created, so a failed call above leaves the listing untouched and
    # purchasable again rather than stuck.
    listing.status = "pending_payment"
    listing.buyer_account_id = uuid.UUID(identity.account_id)
    await session.commit()

    return PurchaseListingResponse(checkout_url=checkout_url)
