from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import PLAN_TOKEN_QUOTAS
from app.models import AccountPlan


async def get_plan_tier(session: AsyncSession, account_id) -> str:
    row = await session.get(AccountPlan, account_id)
    return row.plan_tier if row else "free"


def get_quota(plan_tier: str) -> int:
    return PLAN_TOKEN_QUOTAS.get(plan_tier, PLAN_TOKEN_QUOTAS["free"])
