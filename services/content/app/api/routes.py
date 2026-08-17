import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import storage
from app.config import PUBLISH_ROLES
from app.db import get_session
from app.events import publish_content_created, publish_content_updated
from app.identity import Identity, require_identity
from app.models import Content, ContentVersion
from app.schemas import (
    ContentResponse,
    ContentVersionResponse,
    CreateContentRequest,
    UpdateContentRequest,
    UpdateStatusRequest,
    UploadImageResponse,
)
from py_shared.errors import ApiError

router = APIRouter()

ALLOWED_TRANSITIONS = {
    "draft": {"approved"},
    # "published" is intentionally not a manually settable transition
    # anymore — it's now applied automatically by events.py's
    # post.published consumer, once Social Publishing confirms the
    # content actually went live on LinkedIn. A human clicking a button
    # shouldn't be able to mark something "published" that never was.
    "approved": {"draft"},
    "published": {"draft"},
}


def _to_response(content: Content) -> ContentResponse:
    return ContentResponse(
        id=str(content.id),
        account_id=str(content.account_id),
        created_by_user_id=str(content.created_by_user_id),
        title=content.title,
        body=content.body,
        image_url=content.image_url,
        status=content.status,
        source_generation_job_id=content.source_generation_job_id,
        version=content.version,
        created_at=content.created_at,
        updated_at=content.updated_at,
    )


async def _get_owned_content(session: AsyncSession, content_id: uuid.UUID, account_id: str) -> Content:
    content = await session.get(Content, content_id)
    if not content or content.account_id != uuid.UUID(account_id):
        raise ApiError("not_found", "Content not found.", 404)
    return content


async def _snapshot_version(session: AsyncSession, content: Content, editor_user_id: str) -> None:
    content.version += 1
    session.add(
        ContentVersion(
            content_id=content.id,
            version_number=content.version,
            title=content.title,
            body=content.body,
            image_url=content.image_url,
            edited_by_user_id=uuid.UUID(editor_user_id),
        )
    )


@router.post("/content", response_model=ContentResponse, status_code=201)
async def create_content(
    body: CreateContentRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ContentResponse:
    content = Content(
        account_id=uuid.UUID(identity.account_id),
        created_by_user_id=uuid.UUID(identity.user_id),
        title=body.title,
        body=body.body,
        image_url=body.image_url,
    )
    session.add(content)
    await session.flush()

    session.add(
        ContentVersion(
            content_id=content.id,
            version_number=1,
            title=content.title,
            body=content.body,
            image_url=content.image_url,
            edited_by_user_id=uuid.UUID(identity.user_id),
        )
    )
    await session.commit()

    await publish_content_created(content)
    return _to_response(content)


@router.get("/content", response_model=list[ContentResponse])
async def list_content(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> list[ContentResponse]:
    rows = await session.scalars(
        select(Content).where(Content.account_id == uuid.UUID(identity.account_id)).order_by(Content.created_at.desc())
    )
    return [_to_response(c) for c in rows.all()]


@router.get("/content/{content_id}", response_model=ContentResponse)
async def get_content(
    content_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ContentResponse:
    content = await _get_owned_content(session, content_id, identity.account_id)
    return _to_response(content)


@router.get("/content/{content_id}/versions", response_model=list[ContentVersionResponse])
async def list_versions(
    content_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> list[ContentVersionResponse]:
    await _get_owned_content(session, content_id, identity.account_id)
    rows = await session.scalars(
        select(ContentVersion)
        .where(ContentVersion.content_id == content_id)
        .order_by(ContentVersion.version_number.desc())
    )
    return [
        ContentVersionResponse(
            version_number=v.version_number,
            title=v.title,
            body=v.body,
            image_url=v.image_url,
            edited_by_user_id=str(v.edited_by_user_id),
            created_at=v.created_at,
        )
        for v in rows.all()
    ]


@router.patch("/content/{content_id}", response_model=ContentResponse)
async def update_content(
    content_id: uuid.UUID,
    body: UpdateContentRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ContentResponse:
    content = await _get_owned_content(session, content_id, identity.account_id)

    if body.title is not None:
        content.title = body.title
    if body.body is not None:
        content.body = body.body
    if body.image_url is not None:
        content.image_url = body.image_url

    await _snapshot_version(session, content, identity.user_id)
    await session.commit()

    await publish_content_updated(content)
    return _to_response(content)


@router.post("/content/{content_id}/status", response_model=ContentResponse)
async def update_status(
    content_id: uuid.UUID,
    body: UpdateStatusRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ContentResponse:
    if identity.role not in PUBLISH_ROLES:
        raise ApiError("forbidden", "Only owners/admins can change publish status.", 403)

    content = await _get_owned_content(session, content_id, identity.account_id)

    allowed = ALLOWED_TRANSITIONS.get(content.status, set())
    if body.status not in allowed:
        raise ApiError(
            "invalid_transition", f"Cannot move content from '{content.status}' to '{body.status}'.", 409
        )

    content.status = body.status
    await session.commit()

    await publish_content_updated(content)
    return _to_response(content)


@router.delete("/content/{content_id}", status_code=204)
async def delete_content(
    content_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    content = await _get_owned_content(session, content_id, identity.account_id)
    if content.created_by_user_id != uuid.UUID(identity.user_id) and identity.role not in PUBLISH_ROLES:
        raise ApiError("forbidden", "Only the creator or an owner/admin can delete this content.", 403)

    await session.delete(content)
    await session.commit()


@router.post("/content/{content_id}/image", response_model=UploadImageResponse, status_code=201)
async def upload_image(
    content_id: uuid.UUID,
    file: UploadFile = File(...),
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> UploadImageResponse:
    content = await _get_owned_content(session, content_id, identity.account_id)

    data = await file.read()
    image_url = storage.save_upload(file.filename or "upload", data)
    content.image_url = image_url

    await _snapshot_version(session, content, identity.user_id)
    await session.commit()

    await publish_content_updated(content)
    return UploadImageResponse(image_url=image_url)
