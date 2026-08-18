"""Periodic job keeping LinkedIn access tokens valid ahead of expiry.

Note: LinkedIn's default 3-legged OAuth token doesn't support the
refresh_token grant unless your Developer App has been specifically
granted refresh-token capability — most local/test apps won't have it.
This job still runs and does the right thing either way: it refreshes
connections that do have a refresh_token, and logs a warning (not an
error — nothing is actually broken) for the ones that will need the user
to reconnect once their access token expires.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app import linkedin_client
from app.config import settings
from app.crypto import decrypt_token, encrypt_token
from app.db import async_session_factory
from app.linkedin_client import LinkedInError
from app.models import SocialConnection

logger = logging.getLogger("social_publishing.token_refresh")


async def refresh_due_connections() -> None:
    cutoff = datetime.now(UTC) + timedelta(seconds=settings.token_refresh_ahead_of_expiry_seconds)

    async with async_session_factory() as session:
        due = (
            await session.scalars(select(SocialConnection).where(SocialConnection.expires_at <= cutoff))
        ).all()

    for connection in due:
        if not connection.refresh_token_encrypted:
            logger.warning(
                "LinkedIn connection for account %s expires soon with no refresh_token — user will need to reconnect.",
                connection.account_id,
            )
            continue

        try:
            refresh_token = decrypt_token(connection.refresh_token_encrypted)
            token_response = await linkedin_client.refresh_access_token(refresh_token)
        except LinkedInError:
            logger.exception("failed to refresh LinkedIn token for account %s", connection.account_id)
            continue

        async with async_session_factory() as session:
            row = await session.get(SocialConnection, (connection.account_id, connection.user_id))
            row.access_token_encrypted = encrypt_token(token_response["access_token"])
            if token_response.get("refresh_token"):
                row.refresh_token_encrypted = encrypt_token(token_response["refresh_token"])
            row.expires_at = datetime.now(UTC) + timedelta(seconds=token_response.get("expires_in", 60 * 24 * 60 * 60))
            await session.commit()


async def run_token_refresh_loop() -> None:
    while True:
        try:
            await refresh_due_connections()
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.exception("token refresh pass failed, will retry")

        await asyncio.sleep(settings.token_refresh_check_interval_seconds)
