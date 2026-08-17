from datetime import datetime

from pydantic import BaseModel, EmailStr


class AccountResponse(BaseModel):
    id: str
    type: str
    name: str
    plan_tier: str
    role: str


class CreateTeamAccountRequest(BaseModel):
    name: str


class InviteRequest(BaseModel):
    email: EmailStr
    role: str = "member"


class InviteResponse(BaseModel):
    invite_id: str


class AcceptInviteResponse(BaseModel):
    account_id: str
    role: str


class UpdateRoleRequest(BaseModel):
    role: str


class MemberResponse(BaseModel):
    user_id: str
    role: str
    joined_at: datetime
