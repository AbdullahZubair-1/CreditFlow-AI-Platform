from datetime import UTC, datetime

import redis.asyncio as redis

from app.config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


def current_period() -> str:
    return datetime.now(UTC).strftime("%Y-%m")


def _key(account_id: str, period: str) -> str:
    return f"usage:{account_id}:{period}"


async def get_used_tokens(account_id: str, period: str | None = None) -> int:
    period = period or current_period()
    value = await get_client().get(_key(account_id, period))
    return int(value) if value else 0


async def increment_used_tokens(account_id: str, period: str, amount: int) -> int:
    return await get_client().incrby(_key(account_id, period), amount)


async def set_used_tokens(account_id: str, period: str, amount: int) -> None:
    # ~40 days, comfortably longer than any billing period, so a stale key
    # for an inactive account eventually expires rather than lingering
    # forever; still overwritten every reconciliation pass in the meantime.
    await get_client().set(_key(account_id, period), amount, ex=40 * 24 * 60 * 60)
