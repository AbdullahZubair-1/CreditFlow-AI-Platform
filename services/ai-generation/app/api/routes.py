import logging
import uuid

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events, pollinations_client, pubsub, usage_client
from app.config import AVAILABLE_MODELS
from app.db import get_session
from app.generation import run_generation
from app.identity import Identity, require_identity
from app.models import GenerationJob, ImageGenerationJob, PromptHistory
from app.schemas import (
    CreateGenerationRequest,
    CreateGenerationResponse,
    GenerateImageRequest,
    GenerateImageResponse,
    GenerationJobResponse,
)
from py_shared.errors import ApiError

router = APIRouter()
logger = logging.getLogger("ai_generation.api")


@router.get("/models")
async def list_models() -> dict[str, str]:
    return AVAILABLE_MODELS


@router.post("/generations", response_model=CreateGenerationResponse, status_code=202)
async def create_generation(
    body: CreateGenerationRequest,
    background_tasks: BackgroundTasks,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> CreateGenerationResponse:
    model_slug = AVAILABLE_MODELS.get(body.model)
    if not model_slug:
        raise ApiError(
            "invalid_model", f"Unknown model '{body.model}'. Choose one of: {list(AVAILABLE_MODELS)}.", 400
        )

    try:
        allowed = await usage_client.precheck(identity.account_id, identity.user_id, identity.role, body.model)
    except httpx.HTTPError as exc:
        raise ApiError("usage_check_failed", "Could not verify usage quota. Try again shortly.", 502) from exc

    if not allowed:
        raise ApiError("quota_exceeded", "This account has exceeded its usage quota for this period.", 429)

    job = GenerationJob(
        account_id=uuid.UUID(identity.account_id),
        user_id=uuid.UUID(identity.user_id),
        model=model_slug,
        purpose=body.purpose,
    )
    session.add(job)
    await session.commit()

    background_tasks.add_task(
        _run_generation_safely, job.id, identity.account_id, model_slug, body.prompt
    )

    return CreateGenerationResponse(job_id=str(job.id), status="pending")


async def _run_generation_safely(job_id: uuid.UUID, account_id: str, model_slug: str, prompt: str) -> None:
    try:
        await run_generation(job_id, account_id, model_slug, prompt)
    except Exception:  # noqa: BLE001
        # run_generation already handles its own failure path (marks the
        # job failed, publishes ai.generation_failed) — this is a last
        # resort so a bug in that handling can't leak an unhandled
        # exception out of a fire-and-forget background task.
        logger.exception("unhandled error running generation job %s", job_id)


@router.post("/generations/{job_id}/cancel", status_code=204)
async def cancel_generation(
    job_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    job = await session.get(GenerationJob, job_id)
    if not job or job.account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Generation job not found.", 404)
    if job.status not in ("pending", "streaming"):
        raise ApiError("invalid_state", "Only in-flight jobs can be cancelled.", 409)

    await pubsub.request_cancel(str(job_id))


@router.get("/generations/{job_id}", response_model=GenerationJobResponse)
async def get_generation(
    job_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> GenerationJobResponse:
    job = await session.get(GenerationJob, job_id)
    if not job or job.account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Generation job not found.", 404)

    history = await session.scalar(select(PromptHistory).where(PromptHistory.generation_job_id == job_id))

    return GenerationJobResponse(
        id=str(job.id),
        model=job.model,
        status=job.status,
        prompt=history.prompt if history else "",
        response=history.response if history else "",
        total_tokens=job.total_tokens,
        cost_cents=job.cost_cents,
        error_reason=job.error_reason,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.post("/generations/{job_id}/image", response_model=GenerateImageResponse, status_code=201)
async def generate_image(
    job_id: uuid.UUID,
    body: GenerateImageRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> GenerateImageResponse:
    """Bonus: attach an AI-generated image to a generation job via
    Pollinations.ai (free tier, no API key)."""
    job = await session.get(GenerationJob, job_id)
    if not job or job.account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Generation job not found.", 404)

    image_url = pollinations_client.build_image_url(body.prompt)
    image_job = ImageGenerationJob(
        generation_job_id=job_id,
        account_id=uuid.UUID(identity.account_id),
        prompt=body.prompt,
        image_url=image_url,
        status="completed",
    )
    session.add(image_job)
    await session.commit()

    await events.publish_image_generated(identity.account_id, str(job_id), image_url)

    return GenerateImageResponse(id=str(image_job.id), image_url=image_url)
