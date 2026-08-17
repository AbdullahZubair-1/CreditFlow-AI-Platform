"""Thin wrapper around Groq's OpenAI-compatible streaming chat
completions endpoint. Yields one dict per token chunk and a final dict
carrying usage totals (requested via stream_options.include_usage so a
second, non-streaming call isn't needed just to learn the token count).
"""
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.config import settings


class GroqError(Exception):
    pass


# Llama's instruct tuning defaults to Markdown (headers, **bold**, numbered
# lists) unless told otherwise — fine for a chat UI, wrong here: this
# content is meant to become a LinkedIn post (via Content -> Social
# Publishing), and LinkedIn renders literal asterisks/hashes rather than
# formatting them. Without this system message, generated posts showed
# raw "**Key Features:**" markup instead of the plain, readable text a
# real post needs.
SYSTEM_PROMPT = (
    "You are a professional social media content writer. Write in plain text only — "
    "no Markdown formatting of any kind (no **bold**, no # headers, no numbered or "
    "bulleted list syntax, no backticks). If you want to convey a list, write it as "
    "plain sentences or lines separated by newlines, without leading symbols. Write "
    "naturally, the way a person would write a LinkedIn post."
)


async def stream_completion(model: str, prompt: str) -> AsyncIterator[dict[str, Any]]:
    url = f"{settings.groq_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    async with httpx.AsyncClient(timeout=settings.generation_timeout_seconds) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise GroqError(f"Groq returned {response.status_code}: {body.decode(errors='replace')}")

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
