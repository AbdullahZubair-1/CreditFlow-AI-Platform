import logging
import uuid
from datetime import UTC, datetime

from app.services import events, groq_client, pubsub, scraper_client
from app.core.database import async_session_factory
from app.services.groq_client import GroqError
from app.models import GenerationJob, PromptHistory
from app.services.text_cleanup import strip_markdown

logger = logging.getLogger("ai_generation.generation")

# Placeholder pricing (Groq's actual per-model rates vary widely) —
# illustrative only, same "placeholder" treatment as Billing's plan prices
# and Credits' grant amounts. 1 cent per 100 tokens.
CENTS_PER_100_TOKENS = 1

# Keeps the augmented prompt from ballooning past what's reasonable to send
# to Groq — a full scraped page can be tens of thousands of characters.
RESEARCH_CONTEXT_MAX_CHARS = 3000


async def _build_prompt_with_research(prompt: str) -> str:
    """Best-effort: Scraper searches for and scrapes one page about the
    prompt (no URL from the user) and the result is folded in as context
    ahead of the actual instruction. A failed/empty search just falls back
    to the original prompt unchanged rather than blocking generation."""
    result = await scraper_client.research(prompt)
    if not result or not result.get("text_content"):
        return prompt

    excerpt = result["text_content"][:RESEARCH_CONTEXT_MAX_CHARS]
    return (
        f"Use the following web research as factual context where it's relevant "
        f"(source: {result['url']}):\n\n{excerpt}\n\n---\n\n{prompt}"
    )


async def run_generation(
    job_id: uuid.UUID, account_id: str, model_slug: str, prompt: str, use_web_research: bool = False
) -> None:
    async with async_session_factory() as session:
        job = await session.get(GenerationJob, job_id)
        job.status = "streaming"
        await session.commit()

    effective_prompt = await _build_prompt_with_research(prompt) if use_web_research else prompt

    response_parts: list[str] = []
    prompt_tokens = completion_tokens = total_tokens = 0
    cancelled = False

    try:
        async for chunk in groq_client.stream_completion(model_slug, effective_prompt):
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

        response_text = strip_markdown("".join(response_parts))

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
            purpose = job.purpose
            user_id = str(job.user_id)
            session.add(PromptHistory(generation_job_id=job_id, prompt=prompt, response=response_text))
            await session.commit()

        await pubsub.publish_chunk(str(job_id), {"type": "done", "total_tokens": total_tokens})

        title = None
        if purpose == "post":
            # Only "post" generations become a Content draft (see
            # Content's _handle_generation_completed), so this is skipped
            # for other purposes to avoid spending an extra Groq call on
            # something nothing will ever read.
            try:
                title = await groq_client.generate_short_title(response_text)
            except GroqError:
                logger.exception(
                    "failed to generate title for job %s, Content will fall back to its own heuristic", job_id
                )

        await events.publish_generation_completed(
            account_id,
            user_id,
            str(job_id),
            model_slug,
            purpose,
            response_text,
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cost_cents,
            title,
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
