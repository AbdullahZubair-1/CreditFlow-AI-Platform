from datetime import datetime

from pydantic import BaseModel


class CreateGenerationRequest(BaseModel):
    prompt: str
    model: str = "fast"  # key into AVAILABLE_MODELS, not a raw Groq model slug
    # "post" generations get turned into a draft Content record by the
    # Content Service; other purposes (e.g. ad-hoc chat) are ignored by it.
    purpose: str = "post"
    # Optional web research: no URL from the user, just the prompt itself —
    # Scraper searches for and scrapes one relevant page, folded into the
    # prompt as extra context before it ever reaches Groq. Best-effort: a
    # failed search/scrape just means the generation proceeds without it,
    # never blocks or fails the request itself.
    use_web_research: bool = False


class CreateGenerationResponse(BaseModel):
    job_id: str
    status: str


class GenerationJobResponse(BaseModel):
    id: str
    model: str
    status: str
    prompt: str
    response: str
    total_tokens: int
    cost_cents: int
    error_reason: str | None
    created_at: datetime
    completed_at: datetime | None


class GenerateImageRequest(BaseModel):
    prompt: str
    generation_job_id: str | None = None


class GenerateImageResponse(BaseModel):
    id: str
    image_url: str
