"""Direct Redis reads of Auth's jti session keys — "sourced live from
Redis" per the spec, not cached or mirrored anywhere in this service's
own Postgres schema."""
import json

import redis.asyncio as redis

from app.core.config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


async def list_sessions(account_id: str | None = None) -> list[dict]:
    """SCANs all jti:* keys (there's no secondary index by account_id —
    see Auth's app/redis_client.py — so filtering by account happens
    client-side after parsing each key's JSON value). Fine at this
    scope's session volume; would need a real index to stay performant
    at a much larger scale."""
    client = get_client()
    sessions = []

    async for key in client.scan_iter(match="jti:*"):
        raw = await client.get(key)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue

        if account_id and data.get("account_id") != account_id:
            continue

        ttl = await client.ttl(key)
        sessions.append(
            {
                "jti": key.removeprefix("jti:"),
                "user_id": data.get("user_id"),
                "account_id": data.get("account_id"),
                "expires_in_seconds": ttl,
            }
        )

    return sessions


async def get_session(jti: str) -> dict | None:
    raw = await get_client().get(f"jti:{jti}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


async def revoke_session(jti: str) -> None:
    await get_client().delete(f"jti:{jti}")
