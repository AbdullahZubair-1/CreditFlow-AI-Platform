from urllib.parse import quote

from app.config import settings


def build_image_url(prompt: str) -> str:
    """Pollinations.ai serves an image directly from a GET request encoding
    the prompt in the URL path — no API key, no async job to poll."""
    return f"{settings.pollinations_base_url}/{quote(prompt)}"
