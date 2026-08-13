from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    mongo_url: str = "mongodb://mongo:27017"
    mongo_db_name: str = "creditflow_scraper"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # Per-domain politeness: minimum gap between two requests to the same
    # host, regardless of how many scrape jobs target it concurrently.
    min_seconds_between_requests_per_domain: float = 5.0
    page_load_timeout_seconds: float = 30.0

    # "an internal scheduler" (per the spec) for recurring jobs — a plain
    # asyncio loop inside this service, deliberately not the dedicated
    # Scheduler Service's Celery Beat setup, since recurring scrapes are
    # a lightweight, self-contained concern of this one service.
    recurring_scan_interval_seconds: float = 60.0

    class Config:
        env_file = ".env"


settings = Settings()

RECURRENCE_INTERVALS_SECONDS = {
    "none": None,
    "daily": 24 * 60 * 60,
    "weekly": 7 * 24 * 60 * 60,
}
