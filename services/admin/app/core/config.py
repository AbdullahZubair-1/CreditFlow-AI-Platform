from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    redis_url: str = "redis://redis:6379/0"

    user_tenant_service_url: str = "http://user-tenant:8000"
    billing_service_url: str = "http://billing:8000"
    credits_service_url: str = "http://credits:8000"
    usage_service_url: str = "http://usage:8000"
    auth_service_url: str = "http://auth:8000"

    class Config:
        env_file = ".env"


settings = Settings()
