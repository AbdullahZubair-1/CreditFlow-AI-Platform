from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    auth_service_url: str = "http://auth:8000"
    user_tenant_service_url: str = "http://user-tenant:8000"
    billing_service_url: str = "http://billing:8000"
    credits_service_url: str = "http://credits:8000"
    usage_service_url: str = "http://usage:8000"

    rate_limit_per_ip_per_minute: int = 120
    rate_limit_per_account_per_minute: int = 300

    # Placeholder — replace with the signing secret from your Stripe
    # webhook endpoint (dashboard or `stripe listen`) before testing
    # webhook delivery end-to-end.
    stripe_webhook_secret: str = "whsec_placeholder"
    webhook_dedup_ttl_seconds: int = 24 * 60 * 60

    class Config:
        env_file = ".env"


settings = Settings()
