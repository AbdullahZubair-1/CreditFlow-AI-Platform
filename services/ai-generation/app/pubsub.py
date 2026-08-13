"""Redis pub/sub fan-out for streaming tokens to the Gateway's SSE
re-streaming endpoint, plus a simple cancellation flag. Channel naming
(`generation:{job_id}`) is a convention shared with the Gateway's
app/sse.py — there's no code-level dependency between the two services,
just this documented agreement."""
import json

import redis.asyncio as redis

from app.config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def channel_name(job_id: str) -> str:
    return f"generation:{job_id}"


async def publish_chunk(job_id: str, event: dict) -> None:
    await get_client().publish(channel_name(job_id), json.dumps(event))


async def request_cancel(job_id: str) -> None:
    await get_client().set(f"generation:{job_id}:cancel", "1", ex=settings.generation_timeout_seconds)


async def is_cancel_requested(job_id: str) -> bool:
    return await get_client().exists(f"generation:{job_id}:cancel") == 1
