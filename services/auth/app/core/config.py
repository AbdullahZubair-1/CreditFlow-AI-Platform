from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    login_rate_limit_per_minute: int = 10
    otp_ttl_seconds: int = 10 * 60
    user_tenant_service_url: str = "http://user-tenant:8000"

    class Config:
        env_file = ".env"


settings = Settings()
