import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import select

from app import redis_client
from app.config import THRESHOLDS
from app.db import async_session_factory
from app.models import AccountPlan, ProcessedEvent, ThresholdFlag, UsageLedger
from app.quota import get_plan_tier, get_quota
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("usage.events")

AI_EVENTS_EXCHANGE = "ai_events"
BILLING_EVENTS_EXCHANGE = "billing_events"
DOMAIN_EVENTS_EXCHANGE = "domain_events"
GENERATION_QUEUE = "usage.ai_generation_completed"
PLAN_QUEUE = "usage.subscription_updated"

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await get_connection()
        _channel = await get_confirm_channel(_connection)
    return _channel


def _envelope(routing_key: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": str(uuid.uuid4()),
        "event_type": routing_key,
        "occurred_at": datetime.now(UTC).isoformat(),
        "data": data,
    }


async def _publish_threshold_reached(account_id: str, threshold: int, used: int, quota: int) -> None:
    try:
        channel = await get_channel()
        await publish_event(
            channel,
            DOMAIN_EVENTS_EXCHANGE,
            "usage.threshold_reached",
            _envelope(
                "usage.threshold_reached",
                {"account_id": account_id, "threshold": threshold, "used_tokens": used, "quota_tokens": quota},
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to publish usage.threshold_reached for account %s", account_id)


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


async def _handle_generation_completed(payload: dict[str, Any]) -> None:
    """The generic processed_events check only guards against redelivery
    *after* both this handler's commit and the outer processed_events row
    have landed — a crash in between (what a forced-restart test probes)
    would otherwise redeliver this event and insert a second usage_ledger
    row for the same generation job, permanently double-counting that
    call's cost/tokens (the Redis counter alone would self-heal via the
    reconciliation loop, but the durable Postgres row would not).
    generation_job_id is this handler's own, same-schema idempotency key."""
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    period = redis_client.current_period()
    generation_job_id = data.get("generation_job_id")

    async with async_session_factory() as session:
        if generation_job_id:
            already_recorded = await session.scalar(
                select(UsageLedger).where(UsageLedger.generation_job_id == generation_job_id)
            )
            if already_recorded:
                return

        session.add(
            UsageLedger(
                account_id=account_id,
                generation_job_id=data.get("generation_job_id"),
                model=data["model"],
                prompt_tokens=data.get("prompt_tokens", 0),
                completion_tokens=data.get("completion_tokens", 0),
                total_tokens=data["total_tokens"],
                cost_cents=data.get("cost_cents", 0),
            )
        )
        plan_tier = await get_plan_tier(session, account_id)
        await session.commit()

    used = await redis_client.increment_used_tokens(str(account_id), period, data["total_tokens"])
    await _check_thresholds(account_id, period, used, get_quota(plan_tier))


async def _check_thresholds(account_id: uuid.UUID, period: str, used: int, quota: int) -> None:
    if quota <= 0:
        return
    percent_used = (used / quota) * 100

    for threshold in THRESHOLDS:
        if percent_used < threshold:
            continue

        async with async_session_factory() as session:
            existing = await session.scalar(
                select(ThresholdFlag).where(
                    ThresholdFlag.account_id == account_id,
                    ThresholdFlag.period == period,
                    ThresholdFlag.threshold == threshold,
                )
            )
            if existing:
                continue

            session.add(ThresholdFlag(account_id=account_id, period=period, threshold=threshold))
            await session.commit()

        await _publish_threshold_reached(str(account_id), threshold, used, quota)


async def _handle_subscription_updated(payload: dict[str, Any]) -> None:
    data = payload["data"]
    account_id = uuid.UUID(data["account_id"])
    plan_tier = data.get("plan_tier")
    if not plan_tier:
        return

    async with async_session_factory() as session:
        row = await session.get(AccountPlan, account_id)
        if row:
            row.plan_tier = plan_tier
        else:
            session.add(AccountPlan(account_id=account_id, plan_tier=plan_tier))
        await session.commit()


async def start_consumers() -> None:
    channel = await get_channel()

    generation_queue = await declare_durable_queue_with_dlx(
        channel, AI_EVENTS_EXCHANGE, GENERATION_QUEUE, routing_keys=["ai.generation_completed"]
    )
    plan_queue = await declare_durable_queue_with_dlx(
        channel, BILLING_EVENTS_EXCHANGE, PLAN_QUEUE, routing_keys=["subscription.updated"]
    )

    await consume(
        channel, generation_queue, AI_EVENTS_EXCHANGE, _handle_generation_completed, _is_processed, _mark_processed
    )
    await consume(
        channel, plan_queue, BILLING_EVENTS_EXCHANGE, _handle_subscription_updated, _is_processed, _mark_processed
    )
    logger.info("usage consumers listening on %s and %s", GENERATION_QUEUE, PLAN_QUEUE)
