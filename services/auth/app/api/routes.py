import logging
import uuid
from datetime import UTC, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_session
from app.core.identity import Identity, require_identity
from app.models import Credential, EmailVerificationToken, PasswordResetToken, RefreshToken, User
from app.schemas import (
    DeleteAccountRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    ProfileResponse,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    SwitchAccountRequest,
    TokenPairResponse,
    UpdateProfileRequest,
    VerifyEmailRequest,
)
from app.services import events, redis_client, user_tenant_client
from app.utils import security
from py_shared.errors import ApiError
from py_shared.jwt import decode_token, issue_access_token, issue_refresh_token

router = APIRouter()
logger = logging.getLogger("auth.api")

EMAIL_VERIFICATION_TTL = timedelta(hours=24)


async def _resolve_default_account(user_id: str) -> tuple[str, str]:
    """Picks the first account User/Tenant returns for this user (its own
    /internal/users/{id}/accounts orders by account creation time, so
    this is the user's individual account on their very first login).
    Falls back to the old Slice-1 placeholder (account_id == user_id,
    role owner) if User/Tenant is unreachable or hasn't yet consumed
    user.registered — a brief, rare race right after signup, since event
    delivery is normally sub-second."""
    try:
        accounts = await user_tenant_client.list_user_accounts(user_id)
    except httpx.HTTPError:
        logger.exception("could not resolve accounts for user %s, using placeholder", user_id)
        return user_id, "owner"

    if not accounts:
        logger.warning("user %s has no accounts yet (registration event not yet consumed?), using placeholder", user_id)
        return user_id, "owner"

    return accounts[0]["account_id"], accounts[0]["role"]


async def _resolve_requested_account(user_id: str, requested_account_id: str) -> tuple[str, str]:
    """Validates that user_id is actually a member of requested_account_id
    and returns (account_id, role) for it; falls back to the default
    account if not (e.g. they were removed from a team since their last
    token was issued)."""
    try:
        accounts = await user_tenant_client.list_user_accounts(user_id)
    except httpx.HTTPError:
        logger.exception("could not resolve accounts for user %s, using placeholder", user_id)
        return user_id, "owner"

    for account in accounts:
        if account["account_id"] == requested_account_id:
            return account["account_id"], account["role"]

    if accounts:
        return accounts[0]["account_id"], accounts[0]["role"]
    return user_id, "owner"


@router.post("/signup", response_model=SignupResponse, status_code=201)
async def signup(body: SignupRequest, session: AsyncSession = Depends(get_session)) -> SignupResponse:
    existing = await session.scalar(select(User).where(User.email == body.email))
    if existing:
        raise ApiError("email_already_registered", "An account with this email already exists.", 409)

    user = User(email=body.email)
    session.add(user)
    await session.flush()

    credential = Credential(user_id=user.id, password_hash=security.hash_password(body.password))
    session.add(credential)

    token = security.generate_token()
    verification = EmailVerificationToken(
        user_id=user.id,
        token=token,
        expires_at=datetime.now(UTC) + EMAIL_VERIFICATION_TTL,
    )
    session.add(verification)
    await session.commit()

    await events.publish_user_registered(str(user.id), user.email, token)

    # token is deliberately NOT returned here — Notification actually
    # emails the verification link now (same fix already applied to the
    # forgot-password OTP). Returning it in the API response would let
    # anyone skip email verification entirely for any signup, without
    # ever touching the inbox that "verifies" they own it.
    return SignupResponse(user_id=str(user.id), email=user.email)


@router.post("/verify-email", status_code=204)
async def verify_email(body: VerifyEmailRequest, session: AsyncSession = Depends(get_session)) -> None:
    record = await session.scalar(
        select(EmailVerificationToken).where(EmailVerificationToken.token == body.token)
    )
    if not record or record.used or record.expires_at < datetime.now(UTC):
        raise ApiError("invalid_token", "Verification token is invalid or expired.", 400)

    record.used = True
    user = await session.get(User, record.user_id)
    user.email_verified = True
    await session.commit()


@router.post("/login", response_model=TokenPairResponse)
async def login(
    body: LoginRequest, request: Request, session: AsyncSession = Depends(get_session)
) -> TokenPairResponse:
    client_ip = request.client.host if request.client else "unknown"
    if not await redis_client.check_login_rate_limit(body.email, client_ip):
        raise ApiError("rate_limited", "Too many login attempts. Try again shortly.", 429)

    user = await session.scalar(select(User).where(User.email == body.email))
    credential = None
    if user:
        credential = await session.scalar(select(Credential).where(Credential.user_id == user.id))

    if not user or not credential or not security.verify_password(body.password, credential.password_hash):
        raise ApiError("invalid_credentials", "Incorrect email or password.", 401)

    if not user.email_verified:
        raise ApiError(
            "email_not_verified",
            "Please verify your email before logging in — check your inbox for the verification link.",
            403,
        )

    account_id, role = await _resolve_default_account(str(user.id))

    access_token, claims = issue_access_token(str(user.id), account_id, role, user.is_platform_admin)
    await redis_client.store_jti(claims.jti, str(user.id), account_id)

    refresh_token, refresh_jti = issue_refresh_token(str(user.id))
    session.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            expires_at=datetime.now(UTC) + timedelta(seconds=30 * 24 * 60 * 60),
        )
    )
    await session.commit()

    await events.publish_user_logged_in(str(user.id))

    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/logout", status_code=204)
async def logout(body: LogoutRequest) -> None:
    try:
        claims = decode_token(body.access_token)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("invalid_token", "Access token is invalid.", 400) from exc
    await redis_client.revoke_jti(claims["jti"])


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_session)) -> TokenPairResponse:
    try:
        claims = decode_token(body.refresh_token)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("invalid_token", "Refresh token is invalid or expired.", 401) from exc

    record = await session.scalar(select(RefreshToken).where(RefreshToken.jti == claims["jti"]))
    if not record or record.revoked:
        raise ApiError("invalid_token", "Refresh token has been revoked.", 401)

    # rotate: revoke the old refresh token, issue a new pair
    record.revoked = True

    user = await session.get(User, record.user_id)
    if body.account_id:
        account_id, role = await _resolve_requested_account(str(user.id), body.account_id)
    else:
        account_id, role = await _resolve_default_account(str(user.id))

    access_token, access_claims = issue_access_token(str(user.id), account_id, role, user.is_platform_admin)
    await redis_client.store_jti(access_claims.jti, str(user.id), account_id)

    new_refresh_token, new_refresh_jti = issue_refresh_token(str(user.id))
    session.add(
        RefreshToken(
            user_id=user.id,
            jti=new_refresh_jti,
            expires_at=datetime.now(UTC) + timedelta(seconds=30 * 24 * 60 * 60),
        )
    )
    await session.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=new_refresh_token)


@router.post("/switch-account", response_model=TokenPairResponse)
async def switch_account(body: SwitchAccountRequest, session: AsyncSession = Depends(get_session)) -> TokenPairResponse:
    """Backs the frontend's Account Switcher — issues a new account-scoped
    JWT for a different account the caller belongs to, per the spec
    ("Account Switcher... triggers a new account-scoped JWT"). Requires a
    currently valid, non-revoked access token (same bar as any protected
    Gateway route) rather than weakening the revocation guarantee to let
    an expired or logged-out token switch accounts."""
    try:
        claims = decode_token(body.access_token)
    except Exception as exc:  # noqa: BLE001
        raise ApiError("invalid_token", "Access token is invalid or expired.", 401) from exc

    if not await redis_client.is_jti_active(claims["jti"]):
        raise ApiError("invalid_token", "Access token has been revoked.", 401)

    user = await session.get(User, uuid.UUID(claims["user_id"]))
    if not user:
        raise ApiError("invalid_token", "Access token is invalid.", 400)

    accounts = await user_tenant_client.list_user_accounts(str(user.id))
    match = next((a for a in accounts if a["account_id"] == body.account_id), None)
    if not match:
        raise ApiError("forbidden", "You are not a member of this account.", 403)

    access_token, access_claims = issue_access_token(
        str(user.id), match["account_id"], match["role"], user.is_platform_admin
    )
    await redis_client.store_jti(access_claims.jti, str(user.id), match["account_id"])

    refresh_token, refresh_jti = issue_refresh_token(str(user.id))
    session.add(
        RefreshToken(
            user_id=user.id,
            jti=refresh_jti,
            expires_at=datetime.now(UTC) + timedelta(seconds=30 * 24 * 60 * 60),
        )
    )
    await session.commit()

    return TokenPairResponse(access_token=access_token, refresh_token=refresh_token)


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> ProfileResponse:
    user = await session.get(User, uuid.UUID(identity.user_id))
    if not user:
        raise ApiError("not_found", "User not found.", 404)
    return ProfileResponse(user_id=str(user.id), email=user.email, name=user.name, email_verified=user.email_verified)


@router.patch("/profile", response_model=ProfileResponse)
async def update_profile(
    body: UpdateProfileRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ProfileResponse:
    user = await session.get(User, uuid.UUID(identity.user_id))
    if not user:
        raise ApiError("not_found", "User not found.", 404)

    user.name = body.name.strip()
    await session.commit()

    return ProfileResponse(user_id=str(user.id), email=user.email, name=user.name, email_verified=user.email_verified)


@router.delete("/account", status_code=204)
async def delete_account(
    body: DeleteAccountRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Real, irreversible self-service account deletion. Requires
    re-entering the password as the actual safety gate (a frontend
    type-to-confirm dialog is a UX speed bump, not a security control on
    its own). Deletes the User row — Credential/RefreshToken/
    EmailVerificationToken/PasswordResetToken all cascade via
    ON DELETE CASCADE — then publishes user.deleted so User/Tenant can
    remove this user's memberships across every account, and revokes
    every active session via Redis so any already-issued access token
    stops working immediately rather than lingering until it expires."""
    user_id = uuid.UUID(identity.user_id)
    user = await session.get(User, user_id)
    if not user:
        raise ApiError("not_found", "User not found.", 404)

    if user.is_platform_admin:
        raise ApiError(
            "superadmin_protected",
            "SuperAdmin accounts cannot be deleted through self-service account deletion.",
            403,
        )

    credential = await session.scalar(select(Credential).where(Credential.user_id == user_id))
    if not credential or not security.verify_password(body.password, credential.password_hash):
        raise ApiError("invalid_credentials", "Incorrect password.", 401)

    active_jtis = await redis_client.list_active_jtis_for_user(str(user_id))

    await session.delete(user)
    await session.commit()

    for jti in active_jtis:
        await redis_client.revoke_jti(jti)

    await events.publish_user_deleted(str(user_id))


@router.post("/forgot-password", response_model=ForgotPasswordResponse)
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(get_session)
) -> ForgotPasswordResponse:
    user = await session.scalar(select(User).where(User.email == body.email))
    if not user:
        # do not leak whether the email exists
        return ForgotPasswordResponse()

    otp = security.generate_otp()
    session.add(
        PasswordResetToken(
            user_id=user.id,
            otp_hash=security.hash_otp(otp),
            expires_at=datetime.now(UTC) + timedelta(seconds=settings.otp_ttl_seconds),
        )
    )
    await session.commit()

    await events.publish_password_reset_requested(str(user.id), user.email, otp)

    # otp is deliberately NOT returned here now that Notification actually
    # emails it (see events.publish_password_reset_requested) — returning
    # it in the API response would let anyone reset any account's password
    # just by knowing their email, without ever touching their inbox.
    return ForgotPasswordResponse()


@router.post("/reset-password", status_code=204)
async def reset_password(body: ResetPasswordRequest, session: AsyncSession = Depends(get_session)) -> None:
    user = await session.scalar(select(User).where(User.email == body.email))
    if not user:
        raise ApiError("invalid_otp", "Invalid or expired OTP.", 400)

    record = await session.scalar(
        select(PasswordResetToken)
        .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used == False)  # noqa: E712
        .order_by(PasswordResetToken.created_at.desc())
    )
    if (
        not record
        or record.expires_at < datetime.now(UTC)
        or not security.verify_otp(body.otp, record.otp_hash)
    ):
        raise ApiError("invalid_otp", "Invalid or expired OTP.", 400)

    record.used = True
    credential = await session.scalar(select(Credential).where(Credential.user_id == user.id))
    credential.password_hash = security.hash_password(body.new_password)
    await session.commit()


@router.get("/internal/users/{user_id}")
async def internal_get_user(user_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    """Service-to-service only — the Gateway explicitly rejects any
    /internal/* path on its proxy routes (see _reject_internal_paths in
    services/gateway/app/api/routes.py) so this is unreachable from the
    public internet. Used by the Notification Service to resolve an email
    address from a user_id carried in an event payload, and by the Admin
    Service to show an account owner's email/signup/verification status
    in the SuperAdmin console."""
    user = await session.get(User, user_id)
    if not user:
        raise ApiError("not_found", "User not found.", 404)
    return {
        "user_id": str(user.id),
        "email": user.email,
        "email_verified": user.email_verified,
        "created_at": user.created_at.isoformat(),
    }


@router.get("/internal/users")
async def internal_list_users(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Service-to-service only, same trust model as internal_get_user above.
    Used by the Admin Service's platform-wide user directory (SuperAdmin
    console) — a flat list of every user on the platform, independent of
    which account(s) they belong to."""
    users = (await session.scalars(select(User).order_by(User.created_at.desc()))).all()
    return [
        {
            "user_id": str(user.id),
            "email": user.email,
            "email_verified": user.email_verified,
            "is_platform_admin": user.is_platform_admin,
            "created_at": user.created_at.isoformat(),
        }
        for user in users
    ]
