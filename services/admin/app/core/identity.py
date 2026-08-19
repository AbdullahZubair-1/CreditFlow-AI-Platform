from dataclasses import dataclass

from fastapi import Header

from py_shared.errors import ApiError

TENANT_ADMIN_ROLES = {"owner", "admin"}


@dataclass(frozen=True)
class Identity:
    user_id: str
    account_id: str
    role: str
    is_superadmin: bool


async def require_identity(
    x_user_id: str | None = Header(default=None),
    x_account_id: str | None = Header(default=None),
    x_role: str | None = Header(default=None),
    x_is_superadmin: str | None = Header(default=None),
) -> Identity:
    if not x_user_id or not x_account_id:
        raise ApiError("unauthenticated", "Missing identity headers.", 401)
    return Identity(
        user_id=x_user_id,
        account_id=x_account_id,
        role=x_role or "member",
        is_superadmin=(x_is_superadmin or "").lower() == "true",
    )


def require_access_to_account(identity: Identity, target_account_id: str) -> None:
    """SuperAdmin (platform-level) can access any account; a TenantAdmin
    (owner/admin role on their own account) can only access their own —
    per the spec's "SuperAdmin role... can view/search across all
    accounts; TenantAdmin restricted to their own account_id."""
    if identity.is_superadmin:
        return
    if identity.role in TENANT_ADMIN_ROLES and identity.account_id == target_account_id:
        return
    raise ApiError("forbidden", "Not authorized to view this account's admin data.", 403)


def require_superadmin(identity: Identity) -> None:
    if not identity.is_superadmin:
        raise ApiError("forbidden", "SuperAdmin access required.", 403)
