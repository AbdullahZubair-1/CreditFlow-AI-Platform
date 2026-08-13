from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    usage_service_url: str = "http://usage:8000"

    # Placeholder — replace with a real key from https://openrouter.ai
    # before exercising generation end-to-end.
    openrouter_api_key: str = "sk-or-placeholder"
    openrouter_base_url: str = "https://openrouter.ai/api/v1"

    # Pollinations.ai needs no API key (bonus image generation).
    pollinations_base_url: str = "https://image.pollinations.ai/prompt"

    generation_timeout_seconds: float = 120.0

    class Config:
        env_file = ".env"


settings = Settings()

# At least 2 OpenRouter model choices, per the spec — one fast/cheap, one
# higher quality. Both are real OpenRouter model slugs; swap freely.
AVAILABLE_MODELS: dict[str, str] = {
    "fast": "meta-llama/llama-3.1-8b-instruct",
    "quality": "openai/gpt-4o-mini",
}
