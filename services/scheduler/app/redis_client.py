import redis.asyncio as redis

from app.config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.celery_redis_url, decode_responses=True)
    return _client


async def try_acquire_lock(key: str, ttl_seconds: int) -> bool:
    """SET NX with a TTL — used to keep an overlapping Celery Beat scan (or
    a second beat/worker instance) from firing the same occurrence twice."""
    return bool(await get_client().set(key, "1", nx=True, ex=ttl_seconds))
