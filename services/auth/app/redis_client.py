import redis.asyncio as redis

from app.config import settings
from py_shared.jwt import ACCESS_TOKEN_TTL_SECONDS

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def store_jti(jti: str, user_id: str) -> None:
    await get_client().set(f"jti:{jti}", user_id, ex=ACCESS_TOKEN_TTL_SECONDS)


async def is_jti_active(jti: str) -> bool:
    return await get_client().exists(f"jti:{jti}") == 1


async def revoke_jti(jti: str) -> None:
    await get_client().delete(f"jti:{jti}")


async def check_login_rate_limit(email: str, ip: str) -> bool:
    """Returns True if the attempt is allowed, False if rate-limited."""
    client = get_client()
    key = f"login_attempts:{email}:{ip}"
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, 60)
    return count <= settings.login_rate_limit_per_minute
