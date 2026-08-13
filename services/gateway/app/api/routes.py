import stripe
from fastapi import APIRouter, Depends, Header, Request, Response

from app import redis_client, webhooks
from app.config import settings
from app.identity import Identity, require_jwt
from app.proxy import forward
from py_shared.errors import ApiError

router = APIRouter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _proxy_protected(service_url: str, path: str, request: Request, identity: Identity) -> Response:
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)
    if not await redis_client.check_rate_limit(
        f"account:{identity.account_id}", settings.rate_limit_per_account_per_minute
    ):
        raise ApiError("rate_limited", "Too many requests for this account.", 429)

    return await forward(
        request,
        service_url,
        path,
        extra_headers={
            "X-User-Id": identity.user_id,
            "X-Account-Id": identity.account_id,
            "X-Role": identity.role,
        },
    )


@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_auth(path: str, request: Request) -> Response:
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)
    return await forward(request, settings.auth_service_url, path)


@router.api_route("/me/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_me(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.user_tenant_service_url, f"me/{path}", request, identity)


@router.api_route("/accounts", methods=["GET", "POST"])
async def proxy_accounts_root(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.user_tenant_service_url, "accounts", request, identity)


@router.api_route("/accounts/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_accounts(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.user_tenant_service_url, f"accounts/{path}", request, identity)


@router.api_route("/invites/{path:path}", methods=["GET", "POST"])
async def proxy_invites(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.user_tenant_service_url, f"invites/{path}", request, identity)


@router.api_route("/billing/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_billing(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.billing_service_url, path, request, identity)


@router.api_route("/credits/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_credits(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.credits_service_url, path, request, identity)


@router.api_route("/usage/{path:path}", methods=["GET", "POST"])
async def proxy_usage(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.usage_service_url, path, request, identity)


# --- Webhooks ---


@router.post("/webhooks/stripe")
async def webhook_stripe(request: Request, stripe_signature: str | None = Header(default=None)) -> Response:
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)
    if not stripe_signature:
        raise ApiError("invalid_signature", "Missing Stripe-Signature header.", 400)

    body = await request.body()
    try:
        await webhooks.handle_stripe_webhook(body, stripe_signature)
    except stripe.error.SignatureVerificationError as exc:
        raise ApiError("invalid_signature", "Stripe webhook signature verification failed.", 400) from exc

    return Response(status_code=200)


@router.post("/webhooks/linkedin")
async def webhook_linkedin() -> Response:
    raise ApiError("not_implemented", "LinkedIn webhook arrives with the Social Publishing slice.", 501)


@router.post("/webhooks/openrouter")
async def webhook_openrouter() -> Response:
    raise ApiError("not_implemented", "OpenRouter webhook arrives with the AI Generation slice.", 501)


@router.get("/sse/{job_id}")
async def sse_stream(job_id: str) -> Response:
    raise ApiError("not_implemented", "SSE re-streaming arrives with the AI Generation slice.", 501)
