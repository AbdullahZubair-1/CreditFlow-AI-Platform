import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditsLedger


async def get_balance(session: AsyncSession, account_id: uuid.UUID) -> int:
    """Sum every delta rather than reading the newest row's cached
    balance_after — the latter needed a reliable "which row is newest"
    ordering, which broke whenever an account got two ledger entries in
    the same transaction (e.g. two manual/automated grants applied
    together): Postgres freezes now()/created_at's default at transaction
    start, so both rows get an *identical* timestamp, and the previous
    tie-break (CreditsLedger.id.desc(), a random UUID) could pick either
    one — observed in practice returning a stale balance after exactly
    this scenario. Summing deltas is order-independent and always
    correct for an append-only ledger."""
    total = await session.scalar(
        select(func.coalesce(func.sum(CreditsLedger.delta), 0)).where(CreditsLedger.account_id == account_id)
    )
    return total or 0


async def get_sellable_balance(session: AsyncSession, account_id: uuid.UUID) -> int:
    """The free signup bonus (see events._handle_account_created) is
    usable for generation but can never be listed on the marketplace.
    Modeled as: whatever total amount was ever granted as
    free_signup_bonus is treated as a protected floor — only the balance
    above that floor is sellable. As the account spends credits, its
    sellable balance shrinks in lockstep with its total balance until
    total balance would drop to the bonus amount, at which point sellable
    balance floors at 0 (the account is still spending down its own
    protected bonus for actual usage, just not exposing any of it to the
    marketplace)."""
    total = await get_balance(session, account_id)
    bonus_granted = await session.scalar(
        select(func.coalesce(func.sum(CreditsLedger.delta), 0)).where(
            CreditsLedger.account_id == account_id, CreditsLedger.reason == "free_signup_bonus"
        )
    )
    return max(0, total - (bonus_granted or 0))


async def append_entry(
    session: AsyncSession,
    account_id: uuid.UUID,
    delta: int,
    reason: str,
    reference_id: str | None = None,
) -> CreditsLedger:
    """Appends a new ledger row reflecting the running balance. Caller is
    responsible for committing within its own transaction — this lets a
    caller append several related entries (e.g. a marketplace transfer's
    debit and credit) atomically in one commit."""
    current_balance = await get_balance(session, account_id)
    entry = CreditsLedger(
        account_id=account_id,
        delta=delta,
        reason=reason,
        reference_id=reference_id,
        balance_after=current_balance + delta,
    )
    session.add(entry)
    await session.flush()
    return entry
