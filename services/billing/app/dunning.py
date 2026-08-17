"""Completes the dunning flow the spec describes: "on payment_failed, start
grace-period timer; emit subscription.downgraded if unresolved." Payment
failure already starts the timer (see events._apply_payment_failed, which
sets grace_period_ends_at) — this is the other half, a periodic scan that
actually acts once that timer runs out with no successful payment in
between (a successful invoice.paid clears grace_period_ends_at, see
events._apply_invoice_paid).
"""
import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy import select

from app.config import settings
from app.db import async_session_factory
from app.models import Subscription
from app.outbox import add_outbox_event

logger = logging.getLogger("billing.dunning")


async def _downgrade_expired_grace_periods() -> None:
    async with async_session_factory() as session:
        now = datetime.now(UTC)
        rows = (
            await session.scalars(
                select(Subscription).where(
                    Subscription.status == "past_due", Subscription.grace_period_ends_at < now
                )
            )
        ).all()

        for subscription in rows:
            subscription.status = "downgraded"
            subscription.plan_tier = "free"
            subscription.grace_period_ends_at = None
            add_outbox_event(
                session,
                "subscription.downgraded",
                {"account_id": str(subscription.account_id), "plan_tier": "free"},
            )

        if rows:
            await session.commit()


async def run_dunning_scanner() -> None:
    while True:
        try:
            await _downgrade_expired_grace_periods()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("dunning scan iteration failed, will retry")

        await asyncio.sleep(settings.dunning_scan_interval_seconds)
