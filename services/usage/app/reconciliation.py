"""Periodic reconciliation: recompute each active account's current-month
token usage from the durable Postgres ledger and overwrite the Redis
counter with it, correcting for any drift (e.g. a crash between the
ledger write and the Redis increment in events.py)."""
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from app import redis_client
from app.config import settings
from app.db import async_session_factory
from app.models import UsageLedger

logger = logging.getLogger("usage.reconciliation")


async def _month_start() -> datetime:
    now = datetime.now(UTC)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


async def reconcile_once() -> None:
    period = redis_client.current_period()
    month_start = await _month_start()

    async with async_session_factory() as session:
        rows = await session.execute(
            select(UsageLedger.account_id, func.sum(UsageLedger.total_tokens))
            .where(UsageLedger.created_at >= month_start)
            .group_by(UsageLedger.account_id)
        )
        for account_id, total in rows.all():
            await redis_client.set_used_tokens(str(account_id), period, int(total))


async def run_reconciliation_loop() -> None:
    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("usage reconciliation pass failed, will retry")

        await asyncio.sleep(settings.reconcile_interval_seconds)
