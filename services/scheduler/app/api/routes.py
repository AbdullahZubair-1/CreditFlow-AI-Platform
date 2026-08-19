import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import RECURRENCE_CADENCES
from app.core.database import get_session
from app.core.identity import Identity, require_identity
from app.models import AvailableContent, ScheduledPost
from app.schemas import CreateScheduleRequest, RescheduleRequest, ScheduledPostResponse
from py_shared.errors import ApiError

router = APIRouter()


def _to_response(row: ScheduledPost) -> ScheduledPostResponse:
    return ScheduledPostResponse(
        id=str(row.id),
        account_id=str(row.account_id),
        content_id=str(row.content_id),
        publish_at=row.publish_at,
        status=row.status,
        recurrence=row.recurrence,
        occurrences_fired=row.occurrences_fired,
        created_at=row.created_at,
    )


@router.post("/scheduled", response_model=ScheduledPostResponse, status_code=201)
async def create_schedule(
    body: CreateScheduleRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ScheduledPostResponse:
    if body.recurrence not in RECURRENCE_CADENCES:
        raise ApiError("invalid_recurrence", f"recurrence must be one of {sorted(RECURRENCE_CADENCES)}.", 400)
    if body.publish_at.tzinfo is None:
        raise ApiError("invalid_publish_at", "publish_at must be timezone-aware.", 400)
    if body.publish_at <= datetime.now(UTC):
        raise ApiError("invalid_publish_at", "publish_at must be in the future.", 400)

    content_id = uuid.UUID(body.content_id)
    known = await session.get(AvailableContent, content_id)
    if not known or known.account_id != uuid.UUID(identity.account_id):
        raise ApiError("content_not_found", "This content item is not available to your account.", 404)
    if known.status != "approved":
        raise ApiError(
            "content_not_approved", "Only approved content can be scheduled. Approve it first in Content Studio.", 409
        )

    row = ScheduledPost(
        account_id=uuid.UUID(identity.account_id),
        content_id=content_id,
        created_by_user_id=uuid.UUID(identity.user_id),
        publish_at=body.publish_at,
        recurrence=body.recurrence,
    )
    session.add(row)
    await session.commit()

    return _to_response(row)


@router.get("/scheduled", response_model=list[ScheduledPostResponse])
async def list_schedule(
    start: datetime = Query(...),
    end: datetime = Query(...),
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> list[ScheduledPostResponse]:
    """Calendar view — all scheduled items for the caller's account within
    [start, end]. Times are stored and compared in UTC; converting to the
    viewer's local timezone for display is the frontend's job."""
    rows = await session.scalars(
        select(ScheduledPost).where(
            ScheduledPost.account_id == uuid.UUID(identity.account_id),
            ScheduledPost.publish_at >= start,
            ScheduledPost.publish_at <= end,
        ).order_by(ScheduledPost.publish_at)
    )
    return [_to_response(r) for r in rows.all()]


@router.get("/scheduled/{scheduled_id}", response_model=ScheduledPostResponse)
async def get_schedule(
    scheduled_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ScheduledPostResponse:
    row = await session.get(ScheduledPost, scheduled_id)
    if not row or row.account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Scheduled post not found.", 404)
    return _to_response(row)


@router.patch("/scheduled/{scheduled_id}", response_model=ScheduledPostResponse)
async def reschedule(
    scheduled_id: uuid.UUID,
    body: RescheduleRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> ScheduledPostResponse:
    row = await session.get(ScheduledPost, scheduled_id)
    if not row or row.account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Scheduled post not found.", 404)
    if row.status != "scheduled":
        raise ApiError("invalid_state", "Only pending scheduled posts can be rescheduled.", 409)

    if body.publish_at is not None:
        if body.publish_at.tzinfo is None:
            raise ApiError("invalid_publish_at", "publish_at must be timezone-aware.", 400)
        if body.publish_at <= datetime.now(UTC):
            raise ApiError("invalid_publish_at", "publish_at must be in the future.", 400)
        row.publish_at = body.publish_at
    if body.recurrence is not None:
        if body.recurrence not in RECURRENCE_CADENCES:
            raise ApiError("invalid_recurrence", f"recurrence must be one of {sorted(RECURRENCE_CADENCES)}.", 400)
        row.recurrence = body.recurrence

    await session.commit()
    return _to_response(row)


@router.delete("/scheduled/{scheduled_id}", status_code=204)
async def cancel_schedule(
    scheduled_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    row = await session.get(ScheduledPost, scheduled_id)
    if not row or row.account_id != uuid.UUID(identity.account_id):
        raise ApiError("not_found", "Scheduled post not found.", 404)
    if row.status != "scheduled":
        raise ApiError("invalid_state", "Only pending scheduled posts can be cancelled.", 409)

    row.status = "cancelled"
    await session.commit()
