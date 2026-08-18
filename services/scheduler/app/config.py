from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # Celery broker + result backend — a separate logical Redis DB index
    # from the Gateway/Auth/AI-Generation's db 0 and Usage's db 1, per the
    # spec's explicit call-out for the Scheduler Service.
    celery_redis_url: str = "redis://redis:6379/2"

    beat_scan_interval_seconds: float = 60.0
    # Locks are shorter than the scan interval so a slow/stuck run can't
    # hold a lock past the point where the next scan would need it anyway.
    fire_lock_ttl_seconds: int = 55

    class Config:
        env_file = ".env"


settings = Settings()

RECURRENCE_CADENCES = {"none", "daily", "weekly", "monthly"}
