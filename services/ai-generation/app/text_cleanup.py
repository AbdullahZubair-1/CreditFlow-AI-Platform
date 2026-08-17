"""Strips common Markdown syntax from a completed generation as a safety
net on top of groq_client.SYSTEM_PROMPT — a system prompt steers the model
away from Markdown but isn't a hard guarantee, and this content is meant
to become a plain-text LinkedIn post (via Content -> Social Publishing),
where literal asterisks/hashes render as-is rather than as formatting.
Applied once, to the final assembled text, not per-token — Markdown
tokens like "**" can straddle arbitrary chunk boundaries mid-stream, so
cleaning per-chunk would be unreliable; cleaning the whole string at once
is not.
"""
import re

_BOLD_ITALIC = re.compile(r"(\*\*\*|\*\*|\*|___|__|_)(\S.*?\S|\S)\1")
_HEADER_PREFIX = re.compile(r"^[ \t]*#{1,6}[ \t]+", re.MULTILINE)
_LIST_PREFIX = re.compile(r"^[ \t]*(?:[-*+]|\d+\.)[ \t]+", re.MULTILINE)
_INLINE_CODE = re.compile(r"`([^`]*)`")


def strip_markdown(text: str) -> str:
    text = _BOLD_ITALIC.sub(r"\2", text)
    text = _HEADER_PREFIX.sub("", text)
    text = _LIST_PREFIX.sub("", text)
    text = _INLINE_CODE.sub(r"\1", text)
    return text
