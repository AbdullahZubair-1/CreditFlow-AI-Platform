from dataclasses import dataclass

from fastapi import Header

from app import redis_client
from py_shared.errors import ApiError
from py_shared.jwt import decode_token


@dataclass(frozen=True)
class Identity:
    user_id: str
    account_id: str
    role: str
    jti: str


async def _resolve_identity(token: str) -> Identity:
    try:
        claims = decode_token(token)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("invalid_token", "Access token is invalid or expired.", 401) from exc

    jti = claims.get("jti", "")
    if not await redis_client.is_jti_active(jti):
        raise ApiError("invalid_token", "Access token has been revoked.", 401)

    return Identity(
        user_id=claims["user_id"], account_id=claims["account_id"], role=claims["role"], jti=jti
    )


async def require_jwt(authorization: str | None = Header(default=None)) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError("unauthenticated", "Missing or malformed Authorization header.", 401)
    return await _resolve_identity(authorization.split(" ", 1)[1])


async def require_jwt_from_header_or_query(
    authorization: str | None = Header(default=None), access_token: str | None = None
) -> Identity:
    """Browsers' native EventSource cannot set custom headers, so the SSE
    route is the one place a short-lived access token is accepted via
    query string as a fallback — every other protected route uses
    require_jwt above and only ever accepts the Authorization header."""
    if authorization and authorization.lower().startswith("bearer "):
        return await _resolve_identity(authorization.split(" ", 1)[1])
    if access_token:
        return await _resolve_identity(access_token)
    raise ApiError("unauthenticated", "Missing access token.", 401)
