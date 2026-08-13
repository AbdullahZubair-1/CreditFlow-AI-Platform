from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection, AsyncIOMotorDatabase

from app.config import settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_url)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    return get_client()[settings.mongo_db_name]


def scrape_jobs() -> AsyncIOMotorCollection:
    return get_db()["scrape_jobs"]


def scraped_documents() -> AsyncIOMotorCollection:
    return get_db()["scraped_documents"]


def processed_events() -> AsyncIOMotorCollection:
    return get_db()["processed_events"]


async def init_indexes() -> None:
    await processed_events().create_index("event_id", unique=True)
    await scrape_jobs().create_index("account_id")
    await scrape_jobs().create_index([("recurrence", 1), ("next_run_at", 1)])
    await scraped_documents().create_index("scrape_job_id")
