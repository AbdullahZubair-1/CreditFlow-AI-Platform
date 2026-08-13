from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from app import events, redis_client, security
from app.config import settings
from app.db import get_session
from app.models import Credential, EmailVerificationToken, PasswordResetToken, RefreshToken, User
from app.schemas import (
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    ResetPasswordRequest,
    SignupRequest,
    SignupResponse,
    TokenPairResponse,
    VerifyEmailRequest,
)
from py_shared.errors import ApiError
from py_shared.jwt import decode_token, issue_access_token, issue_refresh_token

router = APIRouter()

EMAIL_VERIFICATION_TTL = timedelta(hours=24)


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

    await events.publish_user_registered(str(user.id), user.email)

    return SignupResponse(user_id=str(user.id), email=user.email, dev_verification_token=token)


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

    # account_id/role are owned by the User/Tenant service; the Gateway
    # composes them in on first login in later slices. For this slice we
    # use the user_id as a placeholder individual-account scope so the
    # token shape is already correct end-to-end.
    account_id = str(user.id)
    role = "owner"

    access_token, claims = issue_access_token(str(user.id), account_id, role)
    await redis_client.store_jti(claims.jti, str(user.id))

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
    account_id = str(user.id)
    role = "owner"

    access_token, access_claims = issue_access_token(str(user.id), account_id, role)
    await redis_client.store_jti(access_claims.jti, str(user.id))

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

    await events.publish_password_reset_requested(str(user.id), user.email)

    return ForgotPasswordResponse(dev_otp=otp)


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
