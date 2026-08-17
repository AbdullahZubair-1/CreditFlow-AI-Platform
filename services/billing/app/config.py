from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"

    # Placeholder Stripe sandbox/test-mode credentials — replace with real
    # test keys from your Stripe dashboard before exercising the checkout
    # flow end-to-end. Price IDs are placeholders too; create matching
    # test-mode Prices in Stripe and swap these in via env vars.
    stripe_secret_key: str = "sk_test_placeholder"
    stripe_price_pro: str = "price_pro_placeholder"
    stripe_price_team: str = "price_team_placeholder"

    outbox_poll_interval_seconds: float = 2.0
    dunning_grace_period_days: int = 3
    dunning_scan_interval_seconds: float = 60.0

    # Official direct-purchase rate for buying credits outside a plan
    # subscription — Credits' marketplace listing cap (95% of this) must
    # stay in sync with this value; see services/credits/app/config.py.
    cents_per_credit: int = 9

    class Config:
        env_file = ".env"


settings = Settings()

# Free tier has no Stripe Price — it's the default, no-subscription state.
PLAN_PRICE_IDS: dict[str, str | None] = {
    "free": None,
    "pro": settings.stripe_price_pro,
    "team": settings.stripe_price_team,
}

# Illustrative placeholder amounts (USD cents) shown to the frontend; the
# actual charge is whatever the Stripe Price above is configured for.
PLAN_DISPLAY_PRICES_CENTS: dict[str, int] = {
    "free": 0,
    "pro": 1900,
    "team": 4900,
}

# Reverse of PLAN_PRICE_IDS — lets a webhook payload's
# subscription.items.data[0].price.id be translated back into "pro"/"team"
# so the Subscription row's plan_tier can actually be set to what was
# purchased (see events._apply_subscription_updated).
PRICE_ID_TO_PLAN: dict[str, str] = {price_id: plan for plan, price_id in PLAN_PRICE_IDS.items() if price_id}
