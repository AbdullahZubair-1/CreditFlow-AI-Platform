from pydantic import BaseModel


class PrecheckRequest(BaseModel):
    model: str


class PrecheckResponse(BaseModel):
    allowed: bool
    used_tokens: int
    quota_tokens: int
    remaining_tokens: int
    plan_tier: str


class ModelUsageSummary(BaseModel):
    model: str
    total_tokens: int
    cost_cents: int
    call_count: int


class UsageSummaryResponse(BaseModel):
    account_id: str
    period: str
    plan_tier: str
    used_tokens: int
    quota_tokens: int
    by_model: list[ModelUsageSummary]
