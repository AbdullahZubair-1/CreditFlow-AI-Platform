import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import WalletLedger


async def get_wallet_balance(session: AsyncSession, account_id: uuid.UUID) -> int:
    """Sum every delta rather than trusting the newest row's cached
    balance_after_cents — same reasoning as ledger.get_balance: two entries
    landing in the same transaction get an identical created_at, so
    ordering by it can't reliably pick the "latest" row."""
    total = await session.scalar(
        select(func.coalesce(func.sum(WalletLedger.delta_cents), 0)).where(WalletLedger.account_id == account_id)
    )
    return total or 0


async def append_wallet_entry(
    session: AsyncSession,
    account_id: uuid.UUID,
    delta_cents: int,
    reason: str,
    reference_id: str | None = None,
) -> WalletLedger:
    """Appends a new wallet ledger row reflecting the running balance.
    Caller is responsible for committing — this lets a caller append a
    wallet entry atomically alongside other work in the same transaction
    (e.g. a marketplace sale's credits transfer and its wallet credit)."""
    current_balance = await get_wallet_balance(session, account_id)
    entry = WalletLedger(
        account_id=account_id,
        delta_cents=delta_cents,
        reason=reason,
        reference_id=reference_id,
        balance_after_cents=current_balance + delta_cents,
    )
    session.add(entry)
    await session.flush()
    return entry
