import asyncio

import httpx
import stripe
from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse

from app import cookie_auth, redis_client, sse, webhooks
from app.config import settings
from app.identity import Identity, require_jwt, require_jwt_from_header_or_query
from app.proxy import forward, get_client
from py_shared.errors import ApiError

router = APIRouter()


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _reject_internal_paths(path: str) -> None:
    # Every service reserves an /internal/* namespace for direct
    # service-to-service calls that skip Gateway auth entirely (email
    # lookups, account-owner lookups, etc. — see e.g. Auth's
    # GET /internal/users/{id}). Catch-all proxy routes like
    # /auth/{path:path} would otherwise happily forward those paths to
    # the public internet unauthenticated, since they match on prefix
    # alone. Pretend they don't exist rather than relay them.
    if path == "internal" or path.startswith("internal/"):
        raise ApiError("not_found", "Not found.", 404)


# "Owner" here means the same owner-tier bucket the frontend's OwnerRoute
# guard uses (owner + admin, as opposed to plain member) — see
# frontend/src/components/OwnerRoute.tsx.
OWNER_TIER_ROLES = {"owner", "admin"}


def _require_owner_tier(identity: Identity) -> None:
    """Centralizes role enforcement at the Gateway for the two domains the
    spec's frontend page list marks as Owner-Only in their entirety
    (Billing & Invoices, Credits & Marketplace) — this is in addition to,
    not instead of, each service's own checks. It's a real fix for Credits
    specifically: that service has no server-side role check at all today,
    so without this, any authenticated member could hit its endpoints
    directly (bypassing the frontend's OwnerRoute) despite the page being
    spec'd as owner-only. Content/Scheduler/Social/Admin/Usage/AI
    Generation deliberately do NOT get a blanket gate like this — their
    real permission rules are finer-grained than "owner vs. everyone else"
    (e.g. Content: any member can edit, only owner/admin can publish), so
    duplicating that logic here would either be redundant or actively
    wrong.
    """
    if identity.role not in OWNER_TIER_ROLES:
        raise ApiError("forbidden", "This action requires an owner or admin role.", 403)


async def _proxy_protected(service_url: str, path: str, request: Request, identity: Identity) -> Response:
    _reject_internal_paths(path)
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
            "X-Is-Superadmin": "true" if identity.is_superadmin else "false",
        },
    )


# --- Cookie-backed auth endpoints (login/refresh/switch-account/logout) ---
#
# These four are registered ahead of the generic /auth/{path:path} catch-all
# below (Starlette/FastAPI match routes in registration order, so a literal
# path always needs to come before a path-converter that would otherwise
# swallow it) because they're the only Auth routes that ever hand back a
# refresh token — which the Gateway must intercept and turn into an
# httpOnly cookie rather than let reach browser-readable JS.


@router.post("/auth/login")
async def auth_login(request: Request) -> Response:
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)
    body = await request.json()
    return await cookie_auth.call_auth_and_set_cookie("login", body)


@router.post("/auth/refresh")
async def auth_refresh(request: Request) -> Response:
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)
    refresh_token = cookie_auth.get_refresh_cookie(request)
    if not refresh_token:
        raise ApiError("invalid_token", "No refresh token cookie present.", 401)

    body = await request.json() if await request.body() else {}
    response = await cookie_auth.call_auth_and_set_cookie(
        "refresh", {"refresh_token": refresh_token, "account_id": body.get("account_id")}
    )
    if response.status_code == 401:
        cookie_auth.clear_refresh_cookie(response)
    return response


@router.post("/auth/switch-account")
async def auth_switch_account(request: Request) -> Response:
    body = await request.json()
    return await cookie_auth.call_auth_and_set_cookie("switch-account", body)


@router.post("/auth/logout")
async def auth_logout(request: Request) -> Response:
    response = await forward(request, settings.auth_service_url, "logout")
    cookie_auth.clear_refresh_cookie(response)
    return response


@router.api_route("/auth/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_auth(path: str, request: Request) -> Response:
    _reject_internal_paths(path)
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
    _require_owner_tier(identity)
    return await _proxy_protected(settings.billing_service_url, path, request, identity)


@router.api_route("/credits/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_credits(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    _require_owner_tier(identity)
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


@router.api_route("/scrape-jobs", methods=["GET", "POST"])
async def proxy_scrape_jobs_root(request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.scraper_service_url, "scrape-jobs", request, identity)


@router.get("/scrape-jobs/{path:path}")
async def proxy_scrape_jobs(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.scraper_service_url, f"scrape-jobs/{path}", request, identity)


@router.get("/scraped-documents/{path:path}")
async def proxy_scraped_documents(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.scraper_service_url, f"scraped-documents/{path}", request, identity)


@router.api_route("/admin/{path:path}", methods=["GET", "POST", "PATCH", "DELETE"])
async def proxy_admin(path: str, request: Request, identity: Identity = Depends(require_jwt)) -> Response:
    return await _proxy_protected(settings.admin_service_url, f"admin/{path}", request, identity)


@router.get("/dashboard/summary")
async def dashboard_summary(request: Request, identity: Identity = Depends(require_jwt)) -> dict:
    """The one response-composition endpoint the spec calls for ("Aggregate
    responses where a frontend screen needs data from more than one
    service") — the Owner Dashboard needs plan tier + team size (User/
    Tenant), credit balance (Credits), and usage this period (Usage) all at
    once. Each downstream call is independently best-effort: one service
    being briefly unavailable shouldn't blank out the whole dashboard, so a
    failed section comes back as null rather than failing the request."""
    _require_owner_tier(identity)  # this dashboard surfaces credits balance, an owner-only data domain
    if not await redis_client.check_rate_limit(f"ip:{_client_ip(request)}", settings.rate_limit_per_ip_per_minute):
        raise ApiError("rate_limited", "Too many requests from this IP.", 429)

    headers = {"X-User-Id": identity.user_id, "X-Account-Id": identity.account_id, "X-Role": identity.role}
    client = get_client()

    async def _get(url: str) -> dict | None:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPError:
            return None

    accounts, balance, usage = await asyncio.gather(
        _get(f"{settings.user_tenant_service_url}/me/accounts"),
        _get(f"{settings.credits_service_url}/balance"),
        _get(f"{settings.usage_service_url}/summary"),
    )
    account = next((a for a in (accounts or []) if a.get("id") == identity.account_id), None) if accounts else None

    return {
        "account": account,
        "credits_balance": balance,
        "usage": usage,
    }


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


@router.post("/webhooks/groq")
async def webhook_groq() -> Response:
    # Groq's chat completions API is request/response (or streaming over
    # the initiating HTTP connection) — it has no webhook delivery model
    # to receive from, so this stub stays a placeholder even after the AI
    # Generation slice landed real streaming via SSE re-relay below.
    raise ApiError("not_implemented", "Groq has no webhook delivery model for chat completions.", 501)


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
