"""Most events this service consumes carry an account_id or user_id, not
an email address — Auth owns the only source of truth for that. These
helpers call the two /internal/* endpoints added specifically to support
Notification (see Auth's and User/Tenant's app/api/routes.py), direct
service-to-service, bypassing the Gateway (which explicitly refuses to
proxy /internal/* paths).
"""
import httpx

from app.core.config import settings


class ResolutionError(Exception):
    pass


async def resolve_email_by_user_id(user_id: str) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.auth_service_url}/internal/users/{user_id}")
        if response.status_code != 200:
            raise ResolutionError(f"could not resolve email for user {user_id}: {response.status_code}")
        return response.json()["email"]


async def resolve_owner_email(account_id: str) -> str:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.user_tenant_service_url}/internal/accounts/{account_id}/owner")
        if response.status_code != 200:
            raise ResolutionError(f"could not resolve owner for account {account_id}: {response.status_code}")
        owner_user_id = response.json()["user_id"]

    return await resolve_email_by_user_id(owner_user_id)
