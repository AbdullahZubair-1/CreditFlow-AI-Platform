import httpx

from app.core.config import settings


async def get_content(account_id: str, user_id: str, content_id: str) -> dict:
    """Direct service-to-service call (bypassing the Gateway) to fetch the
    post text/image for a scheduled item — Content owns that data, Social
    Publishing only owns the LinkedIn-side publishing mechanics."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            f"{settings.content_service_url}/content/{content_id}",
            headers={"X-User-Id": user_id, "X-Account-Id": account_id, "X-Role": "owner"},
        )
        response.raise_for_status()
        return response.json()
