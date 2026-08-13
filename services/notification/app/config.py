from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    auth_service_url: str = "http://auth:8000"
    user_tenant_service_url: str = "http://user-tenant:8000"
    frontend_base_url: str = "http://localhost:5173"

    # Placeholder — Resend's free tier / sandbox domain. Replace with a
    # real key before exercising real email delivery end-to-end.
    resend_api_key: str = "re_placeholder"
    resend_from_email: str = "CreditFlow <onboarding@resend.dev>"

    # Optional — Slack Incoming Webhooks need no OAuth app review, per the
    # spec. Left empty by default; ops alerts just log instead of posting
    # when unset.
    slack_webhook_url: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
