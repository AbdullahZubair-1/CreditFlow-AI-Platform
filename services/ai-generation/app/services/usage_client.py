import httpx

from app.core.config import settings


async def precheck(account_id: str, user_id: str, role: str, model: str) -> bool:
    """Synchronous quota check against the Usage Service, called directly
    (service-to-service, bypassing the Gateway) before accepting a
    generation request, per the spec's requirement that generation only
    proceeds after this check succeeds."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{settings.usage_service_url}/precheck",
            json={"model": model},
            headers={"X-User-Id": user_id, "X-Account-Id": account_id, "X-Role": role},
        )
        response.raise_for_status()
        return response.json()["allowed"]
