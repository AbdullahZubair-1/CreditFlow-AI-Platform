import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika

from py_shared.rabbitmq import get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("ai_generation.events")

EXCHANGE = "ai_events"

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


async def publish_generation_completed(
    account_id: str, generation_job_id: str, model: str, prompt_tokens: int, completion_tokens: int, total_tokens: int, cost_cents: int
) -> None:
    try:
        channel = await get_channel()
        await publish_event(
            channel,
            EXCHANGE,
            "ai.generation_completed",
            _envelope(
                "ai.generation_completed",
                {
                    "account_id": account_id,
                    "generation_job_id": generation_job_id,
                    "model": model,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": total_tokens,
                    "cost_cents": cost_cents,
                },
            ),
        )
    except Exception:  # noqa: BLE001
        # Best-effort, same tradeoff as Credits' event publishing — the
        # generation_jobs row is already committed and is the source of
        # truth; Usage's ledger entry for this call would just be delayed
        # until the next successful publish elsewhere, which is an
        # accepted gap for this slice (Outbox is scoped to Billing only).
        logger.exception("failed to publish ai.generation_completed for job %s", generation_job_id)


async def publish_generation_failed(account_id: str, generation_job_id: str, model: str, reason: str) -> None:
    try:
        channel = await get_channel()
        await publish_event(
            channel,
            EXCHANGE,
            "ai.generation_failed",
            _envelope(
                "ai.generation_failed",
                {"account_id": account_id, "generation_job_id": generation_job_id, "model": model, "reason": reason},
            ),
        )
    except Exception:  # noqa: BLE001
        logger.exception("failed to publish ai.generation_failed for job %s", generation_job_id)
