"""Thin wrapper around OpenRouter's OpenAI-compatible streaming chat
completions endpoint. Yields one dict per token chunk and a final dict
carrying usage totals (requested via stream_options.include_usage so a
second, non-streaming call isn't needed just to learn the token count)."""
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings


class OpenRouterError(Exception):
    pass


async def stream_completion(model: str, prompt: str) -> AsyncIterator[dict[str, Any]]:
    url = f"{settings.openrouter_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    async with httpx.AsyncClient(timeout=settings.generation_timeout_seconds) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise OpenRouterError(f"OpenRouter returned {response.status_code}: {body.decode(errors='replace')}")

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:") :].strip()
                if data == "[DONE]":
                    break

                chunk = json.loads(data)
                usage = chunk.get("usage")
                choices = chunk.get("choices") or []
                content = None
                if choices:
                    content = choices[0].get("delta", {}).get("content")

                if content:
                    yield {"type": "token", "content": content}
                if usage:
                    yield {"type": "usage", "usage": usage}
