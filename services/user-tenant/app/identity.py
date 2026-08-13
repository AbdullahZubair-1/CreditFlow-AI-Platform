"""Identity extraction for requests arriving via the Gateway.

The Gateway verifies the JWT once and forwards the caller's identity to
every downstream service as trusted headers, so internal services don't
each need their own JWT verification middleware.
"""
from dataclasses import dataclass

from fastapi import Header

from py_shared.errors import ApiError


@dataclass(frozen=True)
class Identity:
    user_id: str
    account_id: str
    role: str


async def require_identity(
    x_user_id: str | None = Header(default=None),
    x_account_id: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
) -> Identity:
    if not x_user_id:
        raise ApiError("unauthenticated", "Missing identity headers.", 401)
    return Identity(user_id=x_user_id, account_id=x_account_id or "", role=x_role or "member")
