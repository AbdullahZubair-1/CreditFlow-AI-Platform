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

# One-time bonus granted when an account is first created (still on the
# free plan at that point — PLAN_CREDIT_GRANTS above only fires on a paid
# invoice, which a free account never has). Deliberately not sellable on
# the marketplace — see ledger.get_sellable_balance.
FREE_SIGNUP_BONUS_CREDITS = 50

# Must match Billing's settings.cents_per_credit (services/billing/app/
# config.py) — that's the official direct-purchase rate. MIN_DISCOUNT is
# the platform-wide rule that a marketplace listing must always price its
# credits at least this many percent below buying them directly from us,
# enforced server-side in create_listing.
CENTS_PER_CREDIT = 9
MARKETPLACE_MIN_DISCOUNT_PERCENT = 5
