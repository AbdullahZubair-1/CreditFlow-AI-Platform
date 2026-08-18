from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://creditflow:creditflow@postgres:5432/creditflow"
    redis_url: str = "redis://redis:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    usage_service_url: str = "http://usage:8000"

    # Placeholder — replace with a real key from
    # https://console.groq.com/keys before exercising generation
    # end-to-end. The platform spec names OpenRouter as the text AI
    # provider; this project uses Groq instead (same OpenAI-compatible
    # chat completions shape, just a different host/key/model catalog).
    groq_api_key: str = "gsk_placeholder"
    groq_base_url: str = "https://api.groq.com/openai/v1"

    # Pollinations.ai needs no API key (bonus image generation).
    pollinations_base_url: str = "https://image.pollinations.ai/prompt"

    generation_timeout_seconds: float = 120.0

    class Config:
        env_file = ".env"


settings = Settings()

# At least 2 model choices, per the spec — one fast/cheap, one higher
# quality. Both are real Groq-hosted model slugs; swap freely (Groq's
# catalog changes over time — check https://console.groq.com/docs/models
# if either of these gets deprecated). The previous llama-3.1-8b-instant /
# llama-3.3-70b-versatile pair was fully removed from Groq's catalog
# (confirmed via console.groq.com/docs/models, Aug 2026) and every
# generation request was failing with a 404 model_not_found — replaced
# with the gpt-oss pair, Groq's current production text models.
AVAILABLE_MODELS: dict[str, str] = {
    "fast": "openai/gpt-oss-20b",
    "quality": "openai/gpt-oss-120b",
}
