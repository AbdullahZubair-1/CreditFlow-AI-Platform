"""The spec's "internal scheduler" for recurring scrape jobs — a plain
asyncio loop inside this service (not the dedicated Scheduler Service),
scanning for jobs whose next_run_at has passed and re-triggering them."""
import asyncio
import logging
import uuid
from datetime import datetime, timedelta, timezone

from app import events, mongo
from app.config import RECURRENCE_INTERVALS_SECONDS, settings

logger = logging.getLogger("scraper.recurring")


async def scan_due_recurring_jobs() -> None:
    now = datetime.now(timezone.utc)
    cursor = mongo.scrape_jobs().find(
        {"recurrence": {"$in": ["daily", "weekly"]}, "next_run_at": {"$lte": now}}
    )

    async for job in cursor:
        interval = RECURRENCE_INTERVALS_SECONDS[job["recurrence"]]
        new_job_id = str(uuid.uuid4())

        await mongo.scrape_jobs().insert_one(
            {
                "_id": new_job_id,
                "account_id": job["account_id"],
                "target_url": job["target_url"],
                "job_type": job["job_type"],
                "status": "pending",
                "recurrence": "none",  # this occurrence is one-off; the parent job keeps recurring
                "next_run_at": None,
                "error_reason": None,
                "created_at": now,
                "completed_at": None,
            }
        )
        await events.publish_scrape_requested(new_job_id, job["account_id"], job["target_url"], job["job_type"])

        await mongo.scrape_jobs().update_one(
            {"_id": job["_id"]}, {"$set": {"next_run_at": now + timedelta(seconds=interval)}}
        )


async def run_recurring_loop() -> None:
    while True:
        try:
            await scan_due_recurring_jobs()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("recurring scrape scan failed, will retry")

        await asyncio.sleep(settings.recurring_scan_interval_seconds)
