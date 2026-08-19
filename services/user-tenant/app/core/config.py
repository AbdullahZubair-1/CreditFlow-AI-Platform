from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    auth_service_url: str = "http://auth:8000"
    invite_ttl_days: int = 7

    class Config:
        env_file = ".env"


settings = Settings()
