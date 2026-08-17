import logging
import uuid
from datetime import datetime, timezone
from typing import Any

import aio_pika

from app import mongo
from app.crawler import CrawlerError, RobotsDisallowedError, crawl
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("scraper.events")

SCRAPER_EVENTS_EXCHANGE = "scraper_events"
QUEUE_NAME = "scraper.scrape_requested"

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await get_connection()
        _channel = await get_confirm_channel(_connection)
    return _channel


def _envelope(routing_key: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": routing_key,
        "occurred_at": datetime.now(timezone.utc).isoformat(),
        "data": data,
    }


async def publish_scrape_requested(scrape_job_id: str, account_id: str, target_url: str, job_type: str) -> None:
    channel = await get_channel()
    await publish_event(
        channel,
        SCRAPER_EVENTS_EXCHANGE,
        "scrape.requested",
        _envelope(
            "scrape.requested",
            {"scrape_job_id": scrape_job_id, "account_id": account_id, "target_url": target_url, "job_type": job_type},
        ),
    )


async def _publish_result(routing_key: str, data: dict[str, Any]) -> None:
    try:
        channel = await get_channel()
        await publish_event(channel, SCRAPER_EVENTS_EXCHANGE, routing_key, _envelope(routing_key, data))
    except Exception:  # noqa: BLE001
        logger.exception("failed to publish %s for %s", routing_key, data.get("scrape_job_id"))


async def _is_processed(event_id: str) -> bool:
    return await mongo.processed_events().find_one({"event_id": event_id}) is not None


async def _mark_processed(event_id: str) -> None:
    await mongo.processed_events().insert_one({"event_id": event_id, "processed_at": datetime.now(timezone.utc)})


async def _handle_scrape_requested(payload: dict[str, Any]) -> None:
    """The generic processed_events check only guards against redelivery
    *after* every write below and the outer processed_events row have all
    landed. scraped_documents and scrape_jobs are two separate Mongo
    writes (no multi-document transaction wraps them) — a crash between
    them (what a forced-restart test probes) would leave the job at
    status=pending and, without the check below, redelivery would re-crawl
    and insert a second scraped_documents row for the same job rather than
    just finishing the status update that didn't make it the first time."""
    data = payload["data"]
    scrape_job_id = data["scrape_job_id"]
    target_url = data["target_url"]

    job = await mongo.scrape_jobs().find_one({"_id": scrape_job_id})
    if job and job["status"] not in ("pending", "scheduled"):
        return  # already handled (redelivery)

    existing_document = await mongo.scraped_documents().find_one({"scrape_job_id": scrape_job_id})
    if existing_document:
        # The crawl already happened; only the status update didn't land.
        await mongo.scrape_jobs().update_one(
            {"_id": scrape_job_id}, {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}}
        )
        return

    try:
        result = await crawl(target_url)
    except RobotsDisallowedError as exc:
        await _mark_failed(scrape_job_id, str(exc))
        return  # permanent — retrying won't change what robots.txt says
    except CrawlerError:
        logger.exception("transient crawl failure for job %s, will retry", scrape_job_id)
        raise  # bounded retry then DLX, same as every other consumer

    document_id = str(uuid.uuid4())
    await mongo.scraped_documents().insert_one(
        {
            "_id": document_id,
            "scrape_job_id": scrape_job_id,
            "url": result["url"],
            "title": result["title"],
            "text_content": result["text_content"],
            "html": result["html"],
            "created_at": datetime.now(timezone.utc),
        }
    )

    await mongo.scrape_jobs().update_one(
        {"_id": scrape_job_id},
        {"$set": {"status": "completed", "completed_at": datetime.now(timezone.utc)}},
    )

    await _publish_result(
        "scrape.completed", {"scrape_job_id": scrape_job_id, "document_id": document_id, "url": target_url}
    )


async def _mark_failed(scrape_job_id: str, reason: str) -> None:
    await mongo.scrape_jobs().update_one(
        {"_id": scrape_job_id},
        {"$set": {"status": "failed", "error_reason": reason[:255], "completed_at": datetime.now(timezone.utc)}},
    )
    await _publish_result("scrape.failed", {"scrape_job_id": scrape_job_id, "reason": reason})


async def start_consumer() -> None:
    channel = await get_channel()
    queue = await declare_durable_queue_with_dlx(
        channel, SCRAPER_EVENTS_EXCHANGE, QUEUE_NAME, routing_keys=["scrape.requested"]
    )
    await consume(channel, queue, SCRAPER_EVENTS_EXCHANGE, _handle_scrape_requested, _is_processed, _mark_processed)
    logger.info("scraper consumer listening on %s", QUEUE_NAME)
