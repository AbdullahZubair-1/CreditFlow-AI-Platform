import stripe
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse

from app import redis_client, sse, webhooks
from app.config import settings
from app.identity import Identity, require_jwt, require_jwt_from_header_or_query
from app.proxy import forward, get_client
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


@router.api_route("/generations", methods=["GET", "POST"])
async def proxy_generations_root(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.ai_generation_service_url, "generations", request, identity)


@router.api_route("/generations/{path:path}", methods=["GET", "POST"])
async def proxy_generations(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.ai_generation_service_url, f"generations/{path}", request, identity)


@router.get("/models")
async def proxy_models(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.ai_generation_service_url, "models", request, identity)


@router.api_route("/content", methods=["GET", "POST"])
async def proxy_content_root(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.content_service_url, "content", request, identity)


@router.api_route("/content/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_content(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.content_service_url, f"content/{path}", request, identity)


@router.api_route("/scheduled", methods=["GET", "POST"])
async def proxy_scheduled_root(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.scheduler_service_url, "scheduled", request, identity)


@router.api_route("/scheduled/{path:path}", methods=["GET", "PATCH", "DELETE"])
async def proxy_scheduled(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.scheduler_service_url, f"scheduled/{path}", request, identity)


@router.get("/social/linkedin/callback")
async def proxy_linkedin_callback(request: Request) -> Response:
    # Public — LinkedIn redirects the browser here directly with no way to
    # attach our Authorization header; the caller's identity travels in
    # the signed `state` param the Social Publishing service verifies
    # itself (see that service's app/crypto.py), not via Gateway auth.
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)
    return await forward(request, settings.social_publishing_service_url, "social/linkedin/callback")


@router.post("/social/linkedin/connect")
async def proxy_linkedin_connect(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.social_publishing_service_url, "social/linkedin/connect", request, identity)


@router.api_route("/social/connections", methods=["GET", "DELETE"])
async def proxy_social_connections(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.social_publishing_service_url, "social/connections", request, identity)


@router.get("/social/publish-jobs")
async def proxy_publish_jobs(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.social_publishing_service_url, "social/publish-jobs", request, identity)


@router.get("/uploads/{path:path}")
async def proxy_uploads(path: str, request: Request) -> Response:
    # Uploaded content images are served unauthenticated, same trust level
    # as the bonus Pollinations.ai-generated image URLs — not a security
    # boundary, just static file serving relayed through the Gateway so
    # the URLs Content returns resolve correctly against it.
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)
    return await forward(request, settings.content_service_url, f"uploads/{path}")


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
    # OpenRouter's chat completions API is request/response (or streaming
    # over the initiating HTTP connection) — it has no webhook delivery
    # model to receive from, so this stub stays a placeholder even after
    # the AI Generation slice landed real streaming via SSE re-relay below.
    raise ApiError("not_implemented", "OpenRouter has no webhook delivery model for chat completions.", 501)


@router.get("/sse/{job_id}")
async def sse_stream(
    job_id: str, identity: Identity = Depends(require_jwt_from_header_or_query)
) -> StreamingResponse:
    # job_id is an unguessable UUID, but still worth confirming the caller
    # actually owns it before handing them a live token stream — reuses
    # AI Generation's existing per-account-scoped lookup rather than
    # duplicating that check here.
    ownership_check = await get_client().get(
        f"{settings.ai_generation_service_url}/generations/{job_id}",
        headers={
            "X-User-Id": identity.user_id,
            "X-Account-Id": identity.account_id,
            "X-Role": identity.role,
        },
    )
    if ownership_check.status_code == 404:
        raise ApiError("not_found", "Generation job not found.", 404)
    ownership_check.raise_for_status()

    return StreamingResponse(sse.stream_generation(job_id), media_type="text/event-stream")
