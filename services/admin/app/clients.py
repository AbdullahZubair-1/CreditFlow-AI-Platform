"""Direct service-to-service calls to the services that own the data the
per-account overview aggregates — the spec's "pulled from Credits, Usage,
and User services (read-only calls, no writes)." Each target exposes an
/internal/* endpoint added specifically to support this (see those
services' app/api/routes.py); the Gateway explicitly refuses to proxy any
of them from the public internet.

complete_payout_request below is the one deliberate exception to
"read-only, no writes": marking a wallet payout completed is a genuine
SuperAdmin action (confirming money was actually sent by hand, since
there's no real bank/PayPal integration behind it), not a read, and
Credits — not Admin — owns the wallet data it mutates.
"""
import httpx

from app.config import settings


async def _get_or_none(url: str) -> dict | None:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()


async def get_account_summary(account_id: str) -> dict | None:
    return await _get_or_none(f"{settings.user_tenant_service_url}/internal/accounts/{account_id}/summary")


async def list_all_accounts() -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.user_tenant_service_url}/internal/accounts")
        response.raise_for_status()
        return response.json()


async def get_subscription(account_id: str) -> dict | None:
    return await _get_or_none(f"{settings.billing_service_url}/internal/accounts/{account_id}/subscription")


async def get_balance(account_id: str) -> dict | None:
    return await _get_or_none(f"{settings.credits_service_url}/internal/accounts/{account_id}/balance")


async def get_usage_summary(account_id: str) -> dict | None:
    return await _get_or_none(f"{settings.usage_service_url}/internal/accounts/{account_id}/summary")


async def get_account_owner(account_id: str) -> dict | None:
    return await _get_or_none(f"{settings.user_tenant_service_url}/internal/accounts/{account_id}/owner")


async def get_user(user_id: str) -> dict | None:
    return await _get_or_none(f"{settings.auth_service_url}/internal/users/{user_id}")


async def list_all_users() -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.auth_service_url}/internal/users")
        response.raise_for_status()
        return response.json()


async def list_payout_requests(status: str | None = None) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        params = {"status": status} if status else {}
        response = await client.get(f"{settings.credits_service_url}/internal/payout-requests", params=params)
        response.raise_for_status()
        return response.json()


async def complete_payout_request(payout_id: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{settings.credits_service_url}/internal/payout-requests/{payout_id}/complete")
        response.raise_for_status()
        return response.json()


async def get_revenue_by_account() -> dict[str, int]:
    """Returns {account_id: total_revenue_cents} for every account with at
    least one paid invoice — a single grouped query on Billing's side
    rather than one call per account, since the SuperAdmin directory
    needs every account's figure at once."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(f"{settings.billing_service_url}/internal/revenue")
        response.raise_for_status()
        return {row["account_id"]: row["total_revenue_cents"] for row in response.json()}
