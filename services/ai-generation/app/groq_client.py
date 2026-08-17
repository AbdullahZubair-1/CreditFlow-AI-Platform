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


# Fast/cheap model for these — they're short utility transformations, not
# the user-facing generation itself, so there's no reason to spend the
# "quality" model's tokens on them. Kept in sync with AVAILABLE_MODELS["fast"]
# in app/config.py (llama-3.1-8b-instant was removed from Groq's catalog).
UTILITY_MODEL = "openai/gpt-oss-20b"


async def _utility_completion(system_prompt: str, user_content: str, max_tokens: int) -> str:
    """Shared non-streaming call for the small, single-shot utility
    transformations below (title, image prompt) — neither needs live
    token-by-token output, just one short completion."""
    url = f"{settings.groq_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.groq_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": UTILITY_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        # gpt-oss (UTILITY_MODEL) is a reasoning model: by default it spends
        # its token budget "thinking" in a separate `reasoning` field before
        # ever writing to `content`. max_tokens here was tuned for a
        # non-reasoning model (llama) and is far too small to survive that —
        # without this, a real request exhausted the entire 60-token budget
        # on reasoning and returned finish_reason="length" with an empty
        # content string, which the image-prompt caller's fallback then
        # silently replaced with the *entire original post body*, crashing
        # the DB insert once that got baked into a 1024-char URL column.
        "reasoning_effort": "low",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        if response.status_code != 200:
            raise GroqError(f"Groq returned {response.status_code}: {response.text}")
        data = response.json()
        return data["choices"][0]["message"]["content"].strip().strip('"')


IMAGE_PROMPT_SYSTEM_PROMPT = (
    "You'll receive the full text of a social media post. Pick the single most "
    "visually concrete example, moment, or detail actually mentioned in the text "
    "(not the post's abstract overall theme) and describe it as a specific scene "
    "for an AI image generator. Avoid generic tech cliches — no robots, no glowing "
    "circuit boards, no people typing on laptops in dark rooms unless the text "
    "literally describes that. Respond with ONLY the image description itself "
    "(10-25 words), no preamble, no quotes, no explanation."
)

TITLE_SYSTEM_PROMPT = (
    "You'll receive the full text of a social media post. Write a short, specific "
    "title for it (4-8 words) that names its actual topic — not a generic label, "
    "not a truncated first sentence. Respond with ONLY the title itself, no "
    "quotes, no punctuation at the end, no Markdown."
)


async def generate_image_prompt(post_text: str) -> str:
    """Pollinations.ai (and text-to-image models generally) need a visual
    scene description to produce something accurate — handing it a loose
    topic or the post's abstract theme produces something generically
    "on-theme" but not actually tied to the post (e.g. a stock-photo-style
    robot for anything AI-related). Grounding it in one concrete detail
    from the actual generated text instead produces something that
    genuinely reflects this specific post."""
    # 250, not 60: even at reasoning_effort="low" the model still spends a
    # non-zero, input-dependent number of tokens reasoning before writing
    # the actual answer — 60 was tuned for the old non-reasoning model and
    # was still tight enough to occasionally exhaust itself on reasoning
    # alone for a longer/more complex post, hitting finish_reason="length"
    # with empty content again. This leaves reliable headroom regardless.
    result = await _utility_completion(IMAGE_PROMPT_SYSTEM_PROMPT, post_text, max_tokens=250)
    # Falling back to the *entire* post body (rather than a short prompt)
    # is exactly what turned one empty-content response into a crash: the
    # full text got URL-encoded into image_url, well past its 1024-char
    # column limit. Capped here so this fallback can never do that again,
    # regardless of why the completion came back empty.
    return result or post_text[:200]


async def generate_short_title(post_text: str) -> str:
    """The post's first line isn't reliably a short topic — plenty of
    generations open straight into a full sentence with no distinct title
    line, which content._derive_title's old first-line heuristic would
    just truncate mid-word. Asking for a real title directly is more
    reliable than trying to reverse-engineer one from the body text."""
    # Same reasoning-headroom issue as generate_image_prompt above — 20
    # tokens reliably left this with finish_reason="length" and empty
    # content before it ever got past "thinking" about the title.
    return await _utility_completion(TITLE_SYSTEM_PROMPT, post_text, max_tokens=150)


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
        # Both AVAILABLE_MODELS entries are gpt-oss reasoning models — a
        # live stream against real Groq showed roughly two-thirds of
        # streamed tokens going to an invisible `reasoning` delta the UI
        # never shows (see the note on _utility_completion above for why
        # that matters more than just cost/latency). Writing a short social
        # post doesn't need deep reasoning, so this trims that overhead
        # without changing the actual output.
        "reasoning_effort": "low",
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
