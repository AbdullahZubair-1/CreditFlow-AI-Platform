"""Re-streams AI Generation Service tokens to the frontend as
Server-Sent Events, by subscribing to the same Redis pub/sub channel the
AI Generation Service publishes to (channel naming convention
`generation:{job_id}` — see that service's app/pubsub.py). The Gateway
never talks to Groq directly; it's purely a relay so the frontend
only ever has to hold one connection open, to the Gateway.
"""
import json
from collections.abc import AsyncIterator

from app.services.redis_client import get_client

TERMINAL_TYPES = {"done", "error", "cancelled"}


def channel_name(job_id: str) -> str:
    return f"generation:{job_id}"


async def stream_generation(job_id: str) -> AsyncIterator[str]:
    pubsub = get_client().pubsub()
    await pubsub.subscribe(channel_name(job_id))

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            payload = message["data"]
            yield f"data: {payload}\n\n"

            try:
                event = json.loads(payload)
            except (TypeError, ValueError):
                continue
            if event.get("type") in TERMINAL_TYPES:
                break
    finally:
        await pubsub.unsubscribe(channel_name(job_id))
        await pubsub.close()
