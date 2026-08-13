import redis.asyncio as redis

from app.config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def check_rate_limit(key: str, limit_per_minute: int) -> bool:
    """Fixed-window counter per Redis key. Returns True if allowed."""
    client = get_client()
    full_key = f"ratelimit:{key}"
    count = await client.incr(full_key)
    if count == 1:
        await client.expire(full_key, 60)
    return count <= limit_per_minute


async def is_jti_active(jti: str) -> bool:
    return await get_client().exists(f"jti:{jti}") == 1
