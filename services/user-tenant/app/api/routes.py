import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import select
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
    return [
        AccountResponse(id=str(a.id), type=a.type, name=a.name, plan_tier=a.plan_tier, role=role)
        for a, role in rows.all()
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

    return InviteResponse(invite_id=str(invite.id), dev_invite_token=token)


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
