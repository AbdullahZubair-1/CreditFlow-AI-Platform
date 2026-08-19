from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    auth_service_url: str = "http://auth:8000"
    user_tenant_service_url: str = "http://user-tenant:8000"
    frontend_base_url: str = "http://localhost:5173"

    # SMTP — e.g. Gmail (smtp.gmail.com:587, an App Password from
    # myaccount.google.com/apppasswords, not your real account password).
    # Unlike Resend's free/sandbox tier, a normal SMTP account has no
    # "verified recipient" restriction — it sends to any real address.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = "smtp-placeholder@gmail.com"
    smtp_password: str = "smtp-placeholder"
    smtp_from_email: str = "CreditFlow <smtp-placeholder@gmail.com>"

    # Optional — Slack Incoming Webhooks need no OAuth app review, per the
    # spec. Left empty by default; ops alerts just log instead of posting
    # when unset.
    slack_webhook_url: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
