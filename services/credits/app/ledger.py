import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditsLedger


async def get_balance(session: AsyncSession, account_id: uuid.UUID) -> int:
    latest = await session.scalar(
        select(CreditsLedger.balance_after)
        .where(CreditsLedger.account_id == account_id)
        .order_by(CreditsLedger.created_at.desc(), CreditsLedger.id.desc())
        .limit(1)
    )
    return latest or 0


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
