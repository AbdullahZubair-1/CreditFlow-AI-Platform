import logging
import uuid
from datetime import UTC, datetime

from app import events, openrouter_client, pubsub
from app.db import async_session_factory
from app.models import GenerationJob, PromptHistory

logger = logging.getLogger("ai_generation.generation")

# Placeholder pricing (OpenRouter's actual per-model rates vary widely) —
# illustrative only, same "placeholder" treatment as Billing's plan prices
# and Credits' grant amounts. 1 cent per 100 tokens.
CENTS_PER_100_TOKENS = 1


async def run_generation(job_id: uuid.UUID, account_id: str, model_slug: str, prompt: str) -> None:
    async with async_session_factory() as session:
        job = await session.get(GenerationJob, job_id)
        job.status = "streaming"
        await session.commit()

    response_parts: list[str] = []
    prompt_tokens = completion_tokens = total_tokens = 0
    cancelled = False

    try:
        async for chunk in openrouter_client.stream_completion(model_slug, prompt):
            if await pubsub.is_cancel_requested(str(job_id)):
                cancelled = True
                break

            if chunk["type"] == "token":
                response_parts.append(chunk["content"])
                await pubsub.publish_chunk(str(job_id), {"type": "token", "content": chunk["content"]})
            elif chunk["type"] == "usage":
                usage = chunk["usage"]
                prompt_tokens = usage.get("prompt_tokens", 0)
                completion_tokens = usage.get("completion_tokens", 0)
                total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)

        response_text = "".join(response_parts)

        async with async_session_factory() as session:
            job = await session.get(GenerationJob, job_id)

            if cancelled:
                job.status = "cancelled"
                session.add(PromptHistory(generation_job_id=job_id, prompt=prompt, response=response_text))
                await session.commit()
                await pubsub.publish_chunk(str(job_id), {"type": "cancelled"})
                return

            cost_cents = max(1, total_tokens // 100) * CENTS_PER_100_TOKENS if total_tokens else 0
            job.status = "completed"
            job.prompt_tokens = prompt_tokens
            job.completion_tokens = completion_tokens
            job.total_tokens = total_tokens
            job.cost_cents = cost_cents
            job.completed_at = datetime.now(UTC)
            session.add(PromptHistory(generation_job_id=job_id, prompt=prompt, response=response_text))
            await session.commit()

        await pubsub.publish_chunk(str(job_id), {"type": "done", "total_tokens": total_tokens})
        await events.publish_generation_completed(
            account_id, str(job_id), model_slug, prompt_tokens, completion_tokens, total_tokens, cost_cents
        )

    except Exception as exc:  # noqa: BLE001
        logger.exception("generation job %s failed", job_id)
        reason = str(exc)

        async with async_session_factory() as session:
            job = await session.get(GenerationJob, job_id)
            job.status = "failed"
            job.error_reason = reason[:255]
            await session.commit()

        await pubsub.publish_chunk(str(job_id), {"type": "error", "message": reason})
        await events.publish_generation_failed(account_id, str(job_id), model_slug, reason)
