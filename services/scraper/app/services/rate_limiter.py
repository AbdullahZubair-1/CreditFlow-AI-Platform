"""Per-domain politeness delay — an in-process, per-worker limiter (not
distributed via Redis) since a single scraper worker is the expected
deployment for this scope; if scaled to multiple worker replicas later,
this would need to move to a shared store to stay accurate across them."""
import asyncio
import time
from urllib.parse import urlparse

from app.core.config import settings

_last_request_at: dict[str, float] = {}
_domain_locks: dict[str, asyncio.Lock] = {}


def _domain(url: str) -> str:
    return urlparse(url).netloc


async def wait_for_turn(url: str) -> None:
    domain = _domain(url)
    lock = _domain_locks.setdefault(domain, asyncio.Lock())

    async with lock:
        last = _last_request_at.get(domain)
        if last is not None:
            elapsed = time.monotonic() - last
            remaining = settings.min_seconds_between_requests_per_domain - elapsed
            if remaining > 0:
                await asyncio.sleep(remaining)
        _last_request_at[domain] = time.monotonic()
