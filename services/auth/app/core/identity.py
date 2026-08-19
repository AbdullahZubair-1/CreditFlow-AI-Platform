from dataclasses import dataclass

from fastapi import Header

from py_shared.errors import ApiError


@dataclass(frozen=True)
class Identity:
    user_id: str


async def require_identity(x_user_id: str | None = Header(default=None)) -> Identity:
    """Every other service reads identity from Gateway-forwarded headers —
    Auth never needed this before because its own routes decode tokens
    directly out of the request body (login/refresh/logout/switch-account
    all predate having a valid access token to check). Profile/account
    management are the first Auth routes that assume the caller already
    has one, so the Gateway special-cases them (like login/refresh) to
    attach the same X-User-Id header every other service gets."""
    if not x_user_id:
        raise ApiError("unauthenticated", "Missing identity header.", 401)
    return Identity(user_id=x_user_id)
