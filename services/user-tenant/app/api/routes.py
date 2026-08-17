import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import events
from app.config import settings
from app.db import get_session
from app.identity import Identity, require_identity
from app.models import Account, AccountMember, Invite
from app.schemas import (
    AcceptInviteResponse,
    AccountResponse,
    CreateTeamAccountRequest,
    InviteRequest,
    InviteResponse,
    MemberResponse,
    UpdateRoleRequest,
)
from py_shared.errors import ApiError

router = APIRouter()

MANAGE_ROLES = {"owner", "admin"}


async def _require_membership(
    session: AsyncSession, account_id: uuid.UUID, user_id: uuid.UUID
) -> AccountMember:
    member = await session.scalar(
        select(AccountMember).where(
            AccountMember.account_id == account_id, AccountMember.user_id == user_id
        )
    )
    if not member:
        raise ApiError("forbidden", "You are not a member of this account.", 403)
    return member


@router.get("/me/accounts", response_model=list[AccountResponse])
async def list_my_accounts(
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> list[AccountResponse]:
    rows = await session.execute(
        select(Account, AccountMember.role)
        .join(AccountMember, AccountMember.account_id == Account.id)
        .where(AccountMember.user_id == uuid.UUID(identity.user_id))
    )
    accounts = rows.all()
    if not accounts:
        return []

    count_rows = await session.execute(
        select(AccountMember.account_id, func.count())
        .where(AccountMember.account_id.in_([a.id for a, _ in accounts]))
        .group_by(AccountMember.account_id)
    )
    counts = dict(count_rows.all())

    return [
        AccountResponse(
            id=str(a.id),
            type=a.type,
            name=a.name,
            plan_tier=a.plan_tier,
            role=role,
            member_count=counts.get(a.id, 1),
        )
        for a, role in accounts
    ]


@router.post("/accounts", response_model=AccountResponse, status_code=201)
async def create_team_account(
    body: CreateTeamAccountRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> AccountResponse:
    account = Account(type="team", name=body.name)
    session.add(account)
    await session.flush()

    session.add(AccountMember(account_id=account.id, user_id=uuid.UUID(identity.user_id), role="owner"))
    await session.commit()

    await events.publish_account_created(str(account.id), "team", account.name)
    await events.publish_member_joined(str(account.id), identity.user_id, "owner")

    return AccountResponse(
        id=str(account.id), type=account.type, name=account.name, plan_tier=account.plan_tier, role="owner"
    )


@router.post("/accounts/{account_id}/invite", response_model=InviteResponse, status_code=201)
async def invite_member(
    account_id: uuid.UUID,
    body: InviteRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> InviteResponse:
    member = await _require_membership(session, account_id, uuid.UUID(identity.user_id))
    if member.role not in MANAGE_ROLES:
        raise ApiError("forbidden", "Only owners/admins can invite members.", 403)

    account = await session.get(Account, account_id)
    if not account or account.plan_tier != "team":
        raise ApiError("team_plan_required", "Inviting team members requires the Team plan.", 403)

    token = uuid.uuid4().hex
    invite = Invite(
        account_id=account_id,
        email=body.email,
        role=body.role,
        token=token,
        expires_at=datetime.now(UTC) + timedelta(days=settings.invite_ttl_days),
    )
    session.add(invite)
    await session.commit()

    await events.publish_invite_created(str(invite.id), str(account_id), body.email, token, body.role)

    # token is deliberately NOT returned here — Notification actually
    # emails the invite link now. Returning it in the API response would
    # let the inviter (or anyone reading the response) hand out working
    # invite links without the invitee's email ever being involved at
    # all, defeating the point of inviting a specific person.
    return InviteResponse(invite_id=str(invite.id))


@router.post("/invites/{token}/accept", response_model=AcceptInviteResponse)
async def accept_invite(
    token: str,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> AcceptInviteResponse:
    invite = await session.scalar(select(Invite).where(Invite.token == token))
    if not invite or invite.status != "pending" or invite.expires_at < datetime.now(UTC):
        raise ApiError("invalid_invite", "Invite is invalid, expired, or already used.", 400)

    invite.status = "accepted"
    session.add(
        AccountMember(account_id=invite.account_id, user_id=uuid.UUID(identity.user_id), role=invite.role)
    )
    await session.commit()

    await events.publish_member_joined(str(invite.account_id), identity.user_id, invite.role)

    return AcceptInviteResponse(account_id=str(invite.account_id), role=invite.role)


@router.get("/accounts/{account_id}/members", response_model=list[MemberResponse])
async def list_members(
    account_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> list[MemberResponse]:
    await _require_membership(session, account_id, uuid.UUID(identity.user_id))
    rows = await session.scalars(
        select(AccountMember).where(AccountMember.account_id == account_id)
    )
    return [
        MemberResponse(user_id=str(m.user_id), role=m.role, joined_at=m.created_at) for m in rows.all()
    ]


@router.patch("/accounts/{account_id}/members/{user_id}", response_model=MemberResponse)
async def update_member_role(
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    body: UpdateRoleRequest,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> MemberResponse:
    caller = await _require_membership(session, account_id, uuid.UUID(identity.user_id))
    if caller.role not in MANAGE_ROLES:
        raise ApiError("forbidden", "Only owners/admins can change roles.", 403)

    target = await _require_membership(session, account_id, user_id)
    target.role = body.role
    await session.commit()

    return MemberResponse(user_id=str(target.user_id), role=target.role, joined_at=target.created_at)


@router.delete("/accounts/{account_id}/members/{user_id}", status_code=204)
async def remove_member(
    account_id: uuid.UUID,
    user_id: uuid.UUID,
    identity: Identity = Depends(require_identity),
    session: AsyncSession = Depends(get_session),
) -> None:
    caller = await _require_membership(session, account_id, uuid.UUID(identity.user_id))
    if caller.role not in MANAGE_ROLES:
        raise ApiError("forbidden", "Only owners/admins can remove members.", 403)

    target = await _require_membership(session, account_id, user_id)
    await session.delete(target)
    await session.commit()


@router.get("/internal/users/{user_id}/accounts")
async def internal_list_user_accounts(user_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Service-to-service only — the Gateway explicitly rejects any
    /internal/* path on its proxy routes. Used by Auth to pick a default
    account_id/role to scope a JWT to at login (and to validate an
    account-switch request), since Auth owns identity but not
    account/membership data."""
    rows = await session.execute(
        select(Account, AccountMember.role)
        .join(AccountMember, AccountMember.account_id == Account.id)
        .where(AccountMember.user_id == user_id)
        .order_by(Account.created_at)
    )
    return [
        {"account_id": str(a.id), "role": role, "type": a.type, "name": a.name} for a, role in rows.all()
    ]


@router.get("/internal/accounts")
async def internal_list_accounts(session: AsyncSession = Depends(get_session)) -> list[dict]:
    """Service-to-service only (see the /internal/* note on the owner
    lookup below) — backs the Admin/Ops Service's SuperAdmin-only
    cross-account directory."""
    rows = await session.scalars(select(Account))
    return [
        {"account_id": str(a.id), "name": a.name, "type": a.type, "plan_tier": a.plan_tier}
        for a in rows.all()
    ]


@router.get("/internal/accounts/{account_id}/summary")
async def internal_get_account_summary(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    """Service-to-service only — backs the Admin/Ops Service's per-account
    overview (name/type/plan_tier/member_count), one of the "read-only
    calls" the spec describes pulling from User/Tenant, Billing, Credits,
    and Usage."""
    account = await session.get(Account, account_id)
    if not account:
        raise ApiError("not_found", "Account not found.", 404)

    member_count = await session.scalar(
        select(func.count()).select_from(AccountMember).where(AccountMember.account_id == account_id)
    )
    return {
        "account_id": str(account_id),
        "name": account.name,
        "type": account.type,
        "plan_tier": account.plan_tier,
        "member_count": member_count,
    }


@router.get("/internal/accounts/{account_id}/owner")
async def internal_get_account_owner(account_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    """Service-to-service only — the Gateway explicitly rejects any
    /internal/* path on its proxy routes (see _reject_internal_paths in
    services/gateway/app/api/routes.py) so this is unreachable from the
    public internet. Used by the Notification Service to find who to
    email for account-level events (invoice.paid, usage.threshold_reached,
    etc.) that carry only an account_id, not a user_id."""
    owner = await session.scalar(
        select(AccountMember).where(AccountMember.account_id == account_id, AccountMember.role == "owner")
    )
    if not owner:
        raise ApiError("not_found", "No owner found for this account.", 404)
    return {"account_id": str(account_id), "user_id": str(owner.user_id)}
