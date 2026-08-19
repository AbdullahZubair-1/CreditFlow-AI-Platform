import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.config import settings
from app.core.database import async_session_factory, engine
from app.models import ScheduledPost
from app.services.celery_app import celery_app
from app.services.events import publish_content_scheduled
from app.services.redis_client import try_acquire_lock

logger = logging.getLogger("scheduler.tasks")

RECURRENCE_DELTAS = {
    "daily": timedelta(days=1),
    "weekly": timedelta(weeks=1),
    "monthly": timedelta(days=30),  # placeholder cadence — not calendar-month-accurate
}


@celery_app.task(name="app.tasks.scan_due_scheduled_posts")
def scan_due_scheduled_posts() -> None:
    asyncio.run(_scan_due_scheduled_posts_async())


async def _scan_due_scheduled_posts_async() -> None:
    # `engine` (app/db.py) is created once at module import time, but this
    # whole coroutine runs inside a brand-new event loop on every single
    # Celery task invocation (asyncio.run() below always makes a fresh
    # one). asyncpg connections are bound to the loop that created them, so
    # a connection checked back into the pool at the end of one loop is
    # invalid on the next — this call failed with "attached to a different
    # loop" on its very second invocation and "another operation is in
    # progress" on every one after that, meaning no scheduled post has
    # ever actually been able to fire. Disposing the engine at the end of
    # this loop's run empties the pool before the loop dies, so the next
    # asyncio.run() lazily opens fresh, correctly-loop-bound connections.
    try:
        now = datetime.now(UTC)
        async with async_session_factory() as session:
            due = (
                await session.scalars(
                    select(ScheduledPost).where(ScheduledPost.status == "scheduled", ScheduledPost.publish_at <= now)
                )
            ).all()
            due_ids = [row.id for row in due]

        for scheduled_id in due_ids:
            try:
                await _fire_if_locked(scheduled_id)
            except Exception:  # noqa: BLE001
                logger.exception("failed to fire scheduled post %s", scheduled_id)
    finally:
        await engine.dispose()


async def _fire_if_locked(scheduled_id) -> None:
    async with async_session_factory() as session:
        row = await session.get(ScheduledPost, scheduled_id)
        if not row or row.status != "scheduled":
            return  # cancelled, or another worker already advanced it

        lock_key = f"scheduler:lock:{row.id}:{row.publish_at.isoformat()}"
        if not await try_acquire_lock(lock_key, settings.fire_lock_ttl_seconds):
            return  # another beat/worker already claimed this occurrence this cycle

        account_id, content_id, next_publish_at = str(row.account_id), str(row.content_id), row.publish_at

    # Publish before committing any state change: if this raises, nothing
    # in Postgres has moved, the lock naturally expires (55s < the 60s
    # scan interval), and the next scan retries this occurrence rather
    # than silently marking it fired without Social Publishing ever
    # having been told about it.
    await publish_content_scheduled(str(scheduled_id), account_id, content_id)

    async with async_session_factory() as session:
        row = await session.get(ScheduledPost, scheduled_id)
        if not row or row.status != "scheduled":
            return

        row.occurrences_fired += 1
        if row.recurrence == "none":
            row.status = "fired"
        else:
            row.publish_at = next_publish_at + RECURRENCE_DELTAS[row.recurrence]
            # stays status="scheduled" so it's picked up again next cycle
        await session.commit()
