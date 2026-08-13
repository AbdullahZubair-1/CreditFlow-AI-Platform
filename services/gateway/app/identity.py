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


async def require_jwt(authorization: str | None = Header(default=None)) -> Identity:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise ApiError("unauthenticated", "Missing or malformed Authorization header.", 401)

    token = authorization.split(" ", 1)[1]
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
