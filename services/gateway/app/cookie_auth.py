"""Cookie-backed refresh token handling for the three Auth Service
endpoints that hand back a token pair (login, refresh, switch-account).

The spec's stated production target is "access token in memory, refresh
token in an httpOnly cookie set by the Gateway" — this was previously a
documented dev-scope deviation (both tokens in sessionStorage, readable by
any JS on the page). This module is what actually implements the spec's
version: the Gateway is the only party that ever sees the plaintext refresh
token cross a trust boundary with the browser, via a cookie the frontend's
JS cannot read or exfiltrate.
"""
import json

import httpx
from fastapi import Request, Response

from app.config import settings
from app.proxy import get_client

REFRESH_COOKIE_NAME = "creditflow_refresh_token"
REFRESH_COOKIE_MAX_AGE_SECONDS = 30 * 24 * 60 * 60  # matches Auth's refresh token TTL


def set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        httponly=True,
        samesite="lax",
        # Secure=False so this still works over the plain-http localhost dev
        # setup this project runs on; flip to True once the Gateway sits
        # behind HTTPS.
        secure=False,
        max_age=REFRESH_COOKIE_MAX_AGE_SECONDS,
        path="/auth",
    )


def clear_refresh_cookie(response: Response) -> None:
    response.delete_cookie(key=REFRESH_COOKIE_NAME, path="/auth")


def get_refresh_cookie(request: Request) -> str | None:
    return request.cookies.get(REFRESH_COOKIE_NAME)


async def call_auth_and_set_cookie(path: str, json_body: dict) -> Response:
    """Posts json_body to Auth's /{path}, and — on success — strips
    refresh_token out of the response body before it ever reaches the
    browser, setting it as an httpOnly cookie instead."""
    try:
        upstream = await get_client().post(f"{settings.auth_service_url}/{path}", json=json_body)
    except httpx.HTTPError:
        return Response(
            content=json.dumps({"error": {"code": "upstream_unavailable", "message": "Auth Service is unavailable."}}),
            status_code=502,
            media_type="application/json",
        )

    if upstream.status_code >= 400:
        return Response(content=upstream.content, status_code=upstream.status_code, media_type="application/json")

    data = upstream.json()
    refresh_token = data.pop("refresh_token", None)
    response = Response(content=json.dumps(data), status_code=upstream.status_code, media_type="application/json")
    if refresh_token:
        set_refresh_cookie(response, refresh_token)
    return response
