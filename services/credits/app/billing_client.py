"""Direct service-to-service call to Billing to create a one-time Stripe
Checkout Session for a marketplace purchase. Billing is the only service
holding Stripe credentials/customer mappings, so Credits asks it to do the
actual charge rather than duplicating Stripe integration here; the buyer's
identity headers are forwarded exactly as the Gateway would forward them,
since this is an internal call made on the buyer's behalf."""
import httpx

from app.config import settings


async def create_marketplace_checkout_session(
    buyer_account_id: str,
    buyer_user_id: str,
    buyer_role: str,
    amount_cents: int,
    description: str,
    metadata: dict[str, str],
    success_url: str,
    cancel_url: str,
) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"{settings.billing_service_url}/internal/checkout-sessions/one-time",
            json={
                "amount_cents": amount_cents,
                "currency": "usd",
                "description": description,
                "metadata": metadata,
                "success_url": success_url,
                "cancel_url": cancel_url,
            },
            headers={
                "X-User-Id": buyer_user_id,
                "X-Account-Id": buyer_account_id,
                "X-Role": buyer_role,
            },
        )
        response.raise_for_status()
        return response.json()["checkout_url"]
