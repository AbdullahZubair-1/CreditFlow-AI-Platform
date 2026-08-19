"""Service-to-service read-only calls to Auth — this service owns
accounts/membership but not identity/email, and accept_invite needs to
resolve a user_id to an email to verify an invite is actually being
accepted by the person it was addressed to."""
import httpx

from app.core.config import settings


async def get_user_email(user_id: str) -> str | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.auth_service_url}/internal/users/{user_id}")
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json().get("email")
