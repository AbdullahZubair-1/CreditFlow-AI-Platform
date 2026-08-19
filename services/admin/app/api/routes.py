import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import clients, redis_client
from app.db import get_session
from app.identity import Identity, require_access_to_account, require_identity, require_superadmin
from app.models import AuditLog
from app.schemas import (
    AccountDirectoryEntry,
    AccountOverviewResponse,
    AuditLogEntryResponse,
    SessionResponse,
    UserDirectoryEntry,
    UserDirectoryResponse,
)
from py_shared.errors import ApiError

router = APIRouter()


@router.get("/admin/accounts", response_model=list[AccountDirectoryEntry])
async def list_accounts(identity: Identity = Depends(require_identity)) -> list[AccountDirectoryEntry]:
    """SuperAdmin-only cross-account directory."""
    require_superadmin(identity)
    accounts, revenue_by_account = await clients.list_all_accounts(), await clients.get_revenue_by_account()
    return [
        AccountDirectoryEntry(**a, total_revenue_cents=revenue_by_account.get(a["account_id"], 0))
        for a in accounts
    ]


@router.get("/admin/users", response_model=UserDirectoryResponse)
async def list_users(identity: Identity = Depends(require_identity)) -> UserDirectoryResponse:
    """SuperAdmin-only, platform-wide user directory — every user on the
    platform in one flat list, independent of which account(s) they
    belong to or that account's plan tier/type, plus total platform
    revenue as a single figure rather than broken down per account."""
    require_superadmin(identity)
    users, revenue_by_account = await clients.list_all_users(), await clients.get_revenue_by_account()
    return UserDirectoryResponse(
        total_revenue_cents=sum(revenue_by_account.values()),
        users=[UserDirectoryEntry(**u) for u in users],
    )


@router.get("/admin/accounts/{account_id}/overview", response_model=AccountOverviewResponse)
async def get_account_overview(account_id: str, identity: Identity = Depends(require_identity)) -> AccountOverviewResponse:
    require_access_to_account(identity, account_id)

    summary, subscription, balance, usage, revenue_by_account, owner = (
        await clients.get_account_summary(account_id),
        await clients.get_subscription(account_id),
        await clients.get_balance(account_id),
        await clients.get_usage_summary(account_id),
        await clients.get_revenue_by_account(),
        await clients.get_account_owner(account_id),
    )

    # The owner's profile lives in Auth, keyed by user_id — User/Tenant's
    # owner-lookup gives us that id, then a second call resolves it to the
    # email/verification/signup info the SuperAdmin console actually shows.
    owner_user = await clients.get_user(owner["user_id"]) if owner else None

    return AccountOverviewResponse(
        account_id=account_id,
        name=summary.get("name") if summary else None,
        type=summary.get("type") if summary else None,
        plan_tier=summary.get("plan_tier") if summary else None,
        member_count=summary.get("member_count") if summary else None,
        subscription_status=subscription.get("status") if subscription else None,
        credit_balance=balance.get("balance") if balance else None,
        usage_this_period_tokens=usage.get("used_tokens") if usage else None,
        usage_quota_tokens=usage.get("quota_tokens") if usage else None,
        total_revenue_cents=revenue_by_account.get(account_id, 0),
        owner_email=owner_user.get("email") if owner_user else None,
        owner_email_verified=owner_user.get("email_verified") if owner_user else None,
        owner_created_at=owner_user.get("created_at") if owner_user else None,
    )


@router.get("/admin/accounts/{account_id}/sessions", response_model=list[SessionResponse])
async def list_account_sessions(account_id: str, identity: Identity = Depends(require_identity)) -> list[SessionResponse]:
    require_access_to_account(identity, account_id)
    sessions = await redis_client.list_sessions(account_id)
    return [SessionResponse(**s) for s in sessions]


@router.post("/admin/sessions/{jti}/revoke", status_code=204)
async def revoke_session(jti: str, identity: Identity = Depends(require_identity)) -> None:
    session_data = await redis_client.get_session(jti)
    if not session_data:
        raise ApiError("not_found", "Session not found (already expired or revoked).", 404)

    require_access_to_account(identity, session_data.get("account_id", ""))
    await redis_client.revoke_session(jti)


@router.get("/admin/accounts/{account_id}/audit-log", response_model=list[AuditLogEntryResponse])
async def get_account_audit_log(
    account_id: str,
    limit: int = Query(default=100, le=500),
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLogEntryResponse]:
    require_access_to_account(identity, account_id)
    rows = await session.scalars(
        select(AuditLog)
        .where(AuditLog.account_id == uuid.UUID(account_id))
        .order_by(AuditLog.occurred_at.desc())
        .limit(limit)
    )
    return [_to_audit_response(r) for r in rows.all()]


@router.get("/admin/audit-log", response_model=list[AuditLogEntryResponse])
async def get_platform_audit_log(
    limit: int = Query(default=100, le=500),
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLogEntryResponse]:
    """SuperAdmin-only searchable timeline across every account."""
    require_superadmin(identity)
    rows = await session.scalars(select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit))
    return [_to_audit_response(r) for r in rows.all()]


def _to_audit_response(row: AuditLog) -> AuditLogEntryResponse:
    return AuditLogEntryResponse(
        id=str(row.id),
        event_id=row.event_id,
        event_type=row.event_type,
        source_exchange=row.source_exchange,
        account_id=str(row.account_id) if row.account_id else None,
        payload=row.payload,
        occurred_at=row.occurred_at,
        received_at=row.received_at,
    )
