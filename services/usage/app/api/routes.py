import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import redis_client
from app.db import get_session
from app.identity import Identity, require_identity
from app.models import UsageLedger
from app.quota import get_plan_tier, get_quota
from app.schemas import ModelUsageSummary, PrecheckRequest, PrecheckResponse, UsageSummaryResponse

router = APIRouter()


@router.post("/precheck", response_model=PrecheckResponse)
async def precheck(
    body: PrecheckRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> PrecheckResponse:
    plan_tier = await get_plan_tier(session, uuid.UUID(identity.account_id))
    quota = get_quota(plan_tier)
    used = await redis_client.get_used_tokens(identity.account_id)

    return PrecheckResponse(
        allowed=used < quota,
        used_tokens=used,
        quota_tokens=quota,
        remaining_tokens=max(0, quota - used),
        plan_tier=plan_tier,
    )


async def _build_summary(session: AsyncSession, account_id: uuid.UUID) -> UsageSummaryResponse:
    plan_tier = await get_plan_tier(session, account_id)
    quota = get_quota(plan_tier)

    month_start = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    rows = await session.execute(
        select(
            UsageLedger.model,
            func.sum(UsageLedger.total_tokens),
            func.sum(UsageLedger.cost_cents),
            func.count(UsageLedger.id),
        )
        .where(UsageLedger.account_id == account_id, UsageLedger.created_at >= month_start)
        .group_by(UsageLedger.model)
    )
    by_model = [
        ModelUsageSummary(model=model, total_tokens=int(tokens), cost_cents=int(cost), call_count=int(count))
        for model, tokens, cost, count in rows.all()
    ]
    used_tokens = sum(m.total_tokens for m in by_model)

    return UsageSummaryResponse(
        account_id=str(account_id),
        period=redis_client.current_period(),
        plan_tier=plan_tier,
        used_tokens=used_tokens,
        quota_tokens=quota,
        by_model=by_model,
    )


@router.get("/summary", response_model=UsageSummaryResponse)
async def summary(
    identity: Identity = Depends(require_identity), session: AsyncSession = Depends(get_session)
) -> UsageSummaryResponse:
    return await _build_summary(session, uuid.UUID(identity.account_id))


@router.get("/internal/accounts/{account_id}/summary", response_model=UsageSummaryResponse)
async def internal_get_summary(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> UsageSummaryResponse:
    """Service-to-service only — the Gateway explicitly rejects any
    /internal/* path on its proxy routes. Backs the Admin/Ops Service's
    per-account overview, which needs any account's usage, not just the
    caller's own (GET /summary above is identity-scoped)."""
    return await _build_summary(session, account_id)
