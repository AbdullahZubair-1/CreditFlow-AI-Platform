import redis.asyncio as redis

from app.core.config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(settings.redis_url, decode_responses=True)
    return _client


# Token bucket, per the spec ("Redis token-bucket or sliding-window
# counters") — a fixed-window counter (this file's previous
# implementation) lets a caller burst up to 2x the limit right across a
# window boundary (limit requests at 0:59, another limit at 1:00). A token
# bucket smooths that out: capacity refills continuously at limit/60
# tokens per second instead of resetting in a lump every 60s.
#
# Runs as a single Lua script so the read-refill-check-write cycle is
# atomic under concurrent requests hitting the same key — a plain
# GET-then-SET from Python would race two simultaneous requests into both
# reading the same starting token count.
_TOKEN_BUCKET_SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])

local time_parts = redis.call('TIME')
local now = tonumber(time_parts[1]) + tonumber(time_parts[2]) / 1000000

local bucket = redis.call('HMGET', key, 'tokens', 'ts')
local tokens = tonumber(bucket[1])
local ts = tonumber(bucket[2])

if tokens == nil then
  tokens = capacity
  ts = now
end

local elapsed = math.max(0, now - ts)
tokens = math.min(capacity, tokens + elapsed * refill_rate)

local allowed = 0
if tokens >= 1 then
  tokens = tokens - 1
  allowed = 1
end

redis.call('HMSET', key, 'tokens', tostring(tokens), 'ts', tostring(now))
redis.call('EXPIRE', key, 120)

return allowed
"""


async def check_rate_limit(key: str, limit_per_minute: int) -> bool:
    """Token bucket per Redis key, capacity = limit_per_minute, refilling
    at limit_per_minute/60 tokens per second. Returns True if allowed."""
    client = get_client()
    full_key = f"ratelimit:{key}"
    refill_rate = limit_per_minute / 60.0
    allowed = await client.eval(_TOKEN_BUCKET_SCRIPT, 1, full_key, limit_per_minute, refill_rate)
    return bool(allowed)


async def is_jti_active(jti: str) -> bool:
    return await get_client().exists(f"jti:{jti}") == 1
