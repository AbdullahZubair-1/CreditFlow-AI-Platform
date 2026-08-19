from datetime import datetime
from typing import Any

from pydantic import BaseModel


class SessionResponse(BaseModel):
    jti: str
    user_id: str
    account_id: str
    expires_in_seconds: int


class AccountDirectoryEntry(BaseModel):
    account_id: str
    name: str
    type: str
    plan_tier: str
    total_revenue_cents: int = 0


class AccountOverviewResponse(BaseModel):
    account_id: str
    name: str | None = None
    type: str | None = None
    plan_tier: str | None = None
    member_count: int | None = None
    subscription_status: str | None = None
    credit_balance: int | None = None
    usage_this_period_tokens: int | None = None
    usage_quota_tokens: int | None = None
    total_revenue_cents: int = 0
    owner_email: str | None = None
    owner_email_verified: bool | None = None
    owner_created_at: str | None = None


class UserDirectoryEntry(BaseModel):
    user_id: str
    email: str
    email_verified: bool
    is_platform_admin: bool
    created_at: str


class UserDirectoryResponse(BaseModel):
    total_revenue_cents: int
    users: list[UserDirectoryEntry]


class PayoutRequestResponse(BaseModel):
    id: str
    account_id: str
    amount_cents: int
    destination: str
    status: str
    requested_at: str
    completed_at: str | None


class AuditLogEntryResponse(BaseModel):
    id: str
    event_id: str
    event_type: str
    source_exchange: str
    account_id: str | None
    payload: dict[str, Any]
    occurred_at: datetime
    received_at: datetime
