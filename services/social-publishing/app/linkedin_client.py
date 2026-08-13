"""Thin wrapper around the LinkedIn APIs this service needs: OAuth 2.0 /
OIDC for connect, the Assets API for image upload, and UGC Posts for
publishing. Credentials are placeholders (see app/config.py) — every
developer registers their own LinkedIn Developer App for local testing,
per the spec, since LinkedIn issues API access per app rather than
sharing one set of credentials across a team.
"""
from urllib.parse import urlencode

import httpx

from app.config import settings


class LinkedInError(Exception):
    pass


def build_authorize_url(state: str) -> str:
    params = {
        "response_type": "code",
        "client_id": settings.linkedin_client_id,
        "redirect_uri": settings.linkedin_redirect_uri,
        "scope": settings.linkedin_scopes,
        "state": state,
    }
    return f"{settings.linkedin_auth_base_url}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            settings.linkedin_token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.linkedin_redirect_uri,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        if response.status_code != 200:
            raise LinkedInError(f"token exchange failed ({response.status_code}): {response.text}")
        return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            settings.linkedin_token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": settings.linkedin_client_id,
                "client_secret": settings.linkedin_client_secret,
            },
        )
        if response.status_code != 200:
            raise LinkedInError(f"token refresh failed ({response.status_code}): {response.text}")
        return response.json()


async def get_member_urn(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            settings.linkedin_userinfo_url, headers={"Authorization": f"Bearer {access_token}"}
        )
        if response.status_code != 200:
            raise LinkedInError(f"userinfo failed ({response.status_code}): {response.text}")
        member_id = response.json()["sub"]
        return f"urn:li:person:{member_id}"


async def register_image_upload(access_token: str, member_urn: str) -> tuple[str, str]:
    """Returns (upload_url, asset_urn)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            settings.linkedin_images_register_url,
            json={
                "registerUploadRequest": {
                    "recipes": ["urn:li:digitalmediaRecipe:feedshare-image"],
                    "owner": member_urn,
                    "serviceRelationships": [
                        {"relationshipType": "OWNER", "identifier": "urn:li:userGeneratedContent"}
                    ],
                }
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if response.status_code != 200:
            raise LinkedInError(f"register upload failed ({response.status_code}): {response.text}")

        value = response.json()["value"]
        upload_url = value["uploadMechanism"]["com.linkedin.digitalmedia.uploading.MediaUploadHttpRequest"][
            "uploadUrl"
        ]
        asset_urn = value["asset"]
        return upload_url, asset_urn


async def upload_image_binary(upload_url: str, access_token: str, image_bytes: bytes) -> None:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.put(
            upload_url, content=image_bytes, headers={"Authorization": f"Bearer {access_token}"}
        )
        if response.status_code not in (200, 201):
            raise LinkedInError(f"image upload failed ({response.status_code}): {response.text}")


async def create_ugc_post(access_token: str, member_urn: str, text: str, asset_urn: str | None) -> str:
    """Returns the created post's id/URN."""
    share_content: dict = {
        "shareCommentary": {"text": text},
        "shareMediaCategory": "IMAGE" if asset_urn else "NONE",
    }
    if asset_urn:
        share_content["media"] = [{"status": "READY", "media": asset_urn}]

    body = {
        "author": member_urn,
        "lifecycleState": "PUBLISHED",
        "specificContent": {"com.linkedin.ugc.ShareContent": share_content},
        "visibility": {"com.linkedin.ugc.MemberNetworkVisibility": "PUBLIC"},
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            settings.linkedin_ugc_posts_url,
            json=body,
            headers={"Authorization": f"Bearer {access_token}", "X-Restli-Protocol-Version": "2.0.0"},
        )
        if response.status_code not in (200, 201):
            raise LinkedInError(f"UGC post failed ({response.status_code}): {response.text}")

        return response.headers.get("x-restli-id") or response.json().get("id", "")
