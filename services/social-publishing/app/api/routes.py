import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import linkedin_client
from app.core.config import settings
from app.utils.crypto import create_oauth_state, encrypt_token, verify_oauth_state
from app.core.database import async_session_factory, get_session
from app.core.identity import Identity, require_identity
from app.services.linkedin_client import LinkedInError
from app.models import PublishJob, SocialConnection
from app.schemas import ConnectionStatusResponse, ConnectResponse, PublishJobResponse
from py_shared.errors import ApiError

router = APIRouter()


@router.post("/social/linkedin/connect", response_model=ConnectResponse)
async def connect(identity: Identity = Depends(require_identity)) -> ConnectResponse:
    state = create_oauth_state(identity.account_id, identity.user_id)
    return ConnectResponse(authorize_url=linkedin_client.build_authorize_url(state))


@router.get("/social/linkedin/callback")
async def callback(code: str | None = None, state: str | None = None, error: str | None = None):
    """Public — LinkedIn redirects the browser here directly, with no way
    to carry our Authorization header, so the caller's identity travels
    in the signed `state` param created by /connect above instead."""
    if error or not code or not state:
        return RedirectResponse(f"{settings.frontend_connections_url}?error=linkedin_denied")

    try:
        claims = verify_oauth_state(state)
    except ValueError:
        return RedirectResponse(f"{settings.frontend_connections_url}?error=invalid_state")

    try:
        token_response = await linkedin_client.exchange_code_for_token(code)
        member_urn = await linkedin_client.get_member_urn(token_response["access_token"])
    except LinkedInError:
        return RedirectResponse(f"{settings.frontend_connections_url}?error=linkedin_error")

    account_id = uuid.UUID(claims["account_id"])
    user_id = uuid.UUID(claims["user_id"])
    expires_at = datetime.now(UTC) + timedelta(seconds=token_response.get("expires_in", 60 * 24 * 60 * 60))

    async with async_session_factory() as session:
        existing = await session.get(SocialConnection, (account_id, user_id))
        if existing:
            existing.linkedin_member_urn = member_urn
            existing.access_token_encrypted = encrypt_token(token_response["access_token"])
            existing.refresh_token_encrypted = (
                encrypt_token(token_response["refresh_token"]) if token_response.get("refresh_token") else None
            )
            existing.expires_at = expires_at
        else:
            session.add(
                SocialConnection(
                    account_id=account_id,
                    user_id=user_id,
                    linkedin_member_urn=member_urn,
                    access_token_encrypted=encrypt_token(token_response["access_token"]),
                    refresh_token_encrypted=(
                        encrypt_token(token_response["refresh_token"])
                        if token_response.get("refresh_token")
                        else None
                    ),
                    expires_at=expires_at,
                )
            )
        await session.commit()

    return RedirectResponse(f"{settings.frontend_connections_url}?connected=true")


@router.get("/social/connections", response_model=ConnectionStatusResponse)
async def get_connection_status(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> ConnectionStatusResponse:
    """Always "my own" connection, not the account's — see models.py's
    SocialConnection docstring for why this is per-user now."""
    connection = await session.get(SocialConnection, (uuid.UUID(identity.account_id), uuid.UUID(identity.user_id)))
    if not connection:
        return ConnectionStatusResponse(connected=False)
    return ConnectionStatusResponse(
        connected=True, linkedin_member_urn=connection.linkedin_member_urn, expires_at=connection.expires_at
    )


@router.delete("/social/connections", status_code=204)
async def disconnect(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> None:
    connection = await session.get(SocialConnection, (uuid.UUID(identity.account_id), uuid.UUID(identity.user_id)))
    if not connection:
        raise ApiError("not_found", "You don't have a LinkedIn connection to disconnect.", 404)
    await session.delete(connection)
    await session.commit()


@router.get("/social/publish-jobs", response_model=list[PublishJobResponse])
async def list_publish_jobs(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> list[PublishJobResponse]:
    rows = await session.scalars(
        select(PublishJob)
        .where(PublishJob.account_id == uuid.UUID(identity.account_id))
        .order_by(PublishJob.created_at.desc())
    )
    return [
        PublishJobResponse(
            id=str(j.id),
            scheduled_post_id=str(j.scheduled_post_id),
            content_id=str(j.content_id),
            status=j.status,
            linkedin_post_id=j.linkedin_post_id,
            error_reason=j.error_reason,
            created_at=j.created_at,
            completed_at=j.completed_at,
        )
        for j in rows.all()
    ]
