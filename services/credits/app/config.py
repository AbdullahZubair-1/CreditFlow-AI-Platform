from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    billing_service_url: str = "http://billing:8000"

    low_balance_threshold: int = 100

    class Config:
        env_file = ".env"


settings = Settings()

# Placeholder credit grants per plan tier, applied when Billing's
# invoice.paid domain event is consumed. Free has no paid invoice, so it
# never grants credits through this path.
PLAN_CREDIT_GRANTS: dict[str, int] = {
    "free": 0,
    "pro": 1000,
    "team": 5000,
}
