"""Auth owns identity, not account/membership data — this fixes a gap
from Slice 1, where login issued a JWT scoped to a placeholder account_id
(the user's own id) instead of the real account created by User/Tenant.
Direct service-to-service call, bypassing the Gateway (which refuses to
proxy /internal/* paths)."""
import httpx

from app.core.config import settings


async def list_user_accounts(user_id: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.user_tenant_service_url}/internal/users/{user_id}/accounts")
        response.raise_for_status()
        return response.json()
