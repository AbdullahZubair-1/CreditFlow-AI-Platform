import httpx

from app.config import settings


class EmailError(Exception):
    pass


async def send_email(to: str, subject: str, html: str) -> str:
    """Returns the provider's message id. Resend's REST API: a single
    POST with a bearer token — no SDK needed for this scope."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            "https://api.resend.com/emails",
            json={"from": settings.resend_from_email, "to": [to], "subject": subject, "html": html},
            headers={"Authorization": f"Bearer {settings.resend_api_key}"},
        )
        if response.status_code not in (200, 201):
            raise EmailError(f"Resend returned {response.status_code}: {response.text}")
        return response.json().get("id", "")
