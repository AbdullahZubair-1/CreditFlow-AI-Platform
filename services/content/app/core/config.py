from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # Dev-only stand-in for object storage (S3 in a real deployment) —
    # manually uploaded images are written to this local volume and served
    # back via a static file mount. Swapping in S3 later only touches
    # app/services/storage.py.
    upload_dir: str = "/app/uploads"
    upload_base_url: str = "/uploads"

    class Config:
        env_file = ".env"


settings = Settings()

PUBLISH_ROLES = {"owner", "admin"}
