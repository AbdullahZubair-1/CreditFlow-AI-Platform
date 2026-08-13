from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    redis_url: str = "redis://redis:6379/1"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    reconcile_interval_seconds: float = 60.0

    class Config:
        env_file = ".env"


settings = Settings()

# Placeholder monthly token quotas per plan tier — the AI Generation
# Service (a later slice) will call POST /usage/precheck before every
# generation call to enforce these in real time.
PLAN_TOKEN_QUOTAS: dict[str, int] = {
    "free": 50_000,
    "pro": 500_000,
    "team": 2_000_000,
}

THRESHOLDS = (80, 100)
