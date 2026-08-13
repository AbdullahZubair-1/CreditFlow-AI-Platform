from datetime import datetime

from pydantic import BaseModel


class CreateGenerationRequest(BaseModel):
    prompt: str
    model: str = "fast"  # key into AVAILABLE_MODELS, not a raw OpenRouter slug


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
