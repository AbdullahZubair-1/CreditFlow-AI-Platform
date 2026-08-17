"""Plan-tier gating for features restricted to paid plans (LinkedIn
Connections, Calendar/Scheduler, Marketplace) — Free-plan accounts can't
reach any of these. Billing owns the real Subscription.plan_tier, so this
calls its internal endpoint and caches the result briefly in Redis rather
than round-tripping to Billing on every single gated request.
"""
import httpx

from app.config import settings
from app.redis_client import get_client
from py_shared.errors import ApiError

PLAN_CACHE_TTL_SECONDS = 30
PAID_PLAN_TIERS = {"pro", "team"}

_client: httpx.AsyncClient | None = None


def _http_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=5.0)
    return _client


async def get_plan_tier(account_id: str) -> str:
    redis = get_client()
    cache_key = f"plan_tier:{account_id}"
    cached = await redis.get(cache_key)
    if cached:
        return cached

    try:
        response = await _http_client().get(f"{settings.billing_service_url}/internal/accounts/{account_id}/subscription")
        response.raise_for_status()
        plan_tier = response.json()["plan_tier"]
    except httpx.HTTPError:
        # Fail closed on the paywall (treat as free/unpaid) rather than
        # silently granting a paid feature for free during a Billing
        # outage — this gates a product feature, not a security boundary,
        # so a brief false-negative during an outage is the safer default.
        plan_tier = "free"

    await redis.set(cache_key, plan_tier, ex=PLAN_CACHE_TTL_SECONDS)
    return plan_tier


async def require_paid_plan(account_id: str) -> None:
    plan_tier = await get_plan_tier(account_id)
    if plan_tier not in PAID_PLAN_TIERS:
        raise ApiError(
            "plan_upgrade_required", "This feature requires the Pro or Team plan.", 403, {"plan_tier": plan_tier}
        )
