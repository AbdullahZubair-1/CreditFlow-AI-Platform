import logging

import httpx

from app.core.config import settings

logger = logging.getLogger("ai_generation.scraper_client")

RESEARCH_TIMEOUT_SECONDS = 45.0


async def research(query: str) -> dict | None:
    """Best-effort: a failed search/scrape (timeout, no results found,
    every candidate blocked by robots.txt) just means the caller proceeds
    without research context — this never raises, since "the web research
    toggle happened to fail" shouldn't fail the whole generation request."""
    try:
        async with httpx.AsyncClient(timeout=RESEARCH_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{settings.scraper_service_url}/internal/research", json={"query": query})
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()
    except httpx.HTTPError:
        logger.warning("web research request failed for query %r", query, exc_info=True)
        return None
