import json

import redis.asyncio as redis

from app.core.config import settings
from py_shared.jwt import ACCESS_TOKEN_TTL_SECONDS

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def store_jti(jti: str, user_id: str, account_id: str) -> None:
    # Stored as JSON (not a bare user_id string) so the Admin/Ops
    # Service's "list active sessions per account" view (which SCANs
    # jti:* directly, sourced live from Redis per the spec) can filter by
    # account_id without a second index to keep in sync.
    await get_client().set(
        f"jti:{jti}", json.dumps({"user_id": user_id, "account_id": account_id}), ex=ACCESS_TOKEN_TTL_SECONDS
    )


async def is_jti_active(jti: str) -> bool:
    return await get_client().exists(f"jti:{jti}") == 1


async def revoke_jti(jti: str) -> None:
    await get_client().delete(f"jti:{jti}")


async def list_active_jtis_for_user(user_id: str) -> list[str]:
    """Same SCAN-jti:*-and-filter approach Admin's session viewer already
    uses — used here so DELETE /account can revoke every one of a user's
    active sessions immediately, not just the one they happened to be
    deleting the account from."""
    client = get_client()
    jtis: list[str] = []
    async for key in client.scan_iter(match="jti:*"):
        raw = await client.get(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if data.get("user_id") == user_id:
            jtis.append(key.removeprefix("jti:"))
    return jtis


async def check_login_rate_limit(email: str, ip: str) -> bool:
    """Returns True if the attempt is allowed, False if rate-limited."""
    client = get_client()
    key = f"login_attempts:{email}:{ip}"
    count = await client.incr(key)
    if count == 1:
        await client.expire(key, 60)
    return count <= settings.login_rate_limit_per_minute
