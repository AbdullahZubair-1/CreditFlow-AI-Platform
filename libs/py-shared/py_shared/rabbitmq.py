"""RabbitMQ publish/consume helpers shared by every CreditFlow service.

Conventions enforced here (per the platform spec):
  - one durable topic exchange per domain, publisher confirms on every publish
  - all messages published with delivery_mode=2 (persistent)
  - every queue gets a matching <queue>.dlx dead-letter exchange/queue with
    a bounded retry count (via an x-death header check) before landing there
  - consumers are idempotent: callers supply is_processed/mark_processed
    hooks backed by their own service's processed_events table
"""
from __future__ import annotations

import asyncio
import datetime
import decimal
import json
import logging
import os
from typing import Any, Awaitable, Callable

import aio_pika
from aio_pika import DeliveryMode, ExchangeType, Message
from aio_pika.abc import AbstractIncomingMessage

logger = logging.getLogger("py_shared.rabbitmq")


def _json_default(value: Any) -> Any:
    """Handles the handful of common Python types that aren't natively
    JSON-serializable but show up regularly in event payloads sourced from
    third-party SDKs — Stripe's Event objects in particular return several
    numeric fields (tax amounts, exchange rates) as decimal.Decimal rather
    than float or int, which crashed publish_event with a bare
    `TypeError: Object of type Decimal is not JSON serializable` on every
    Stripe webhook carrying one of those fields, even after converting the
    outer Event object itself to a plain dict."""
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")

MAX_RETRIES = 5
CONNECT_MAX_ATTEMPTS = 10
CONNECT_INITIAL_DELAY_SECONDS = 1.0
CONNECT_MAX_DELAY_SECONDS = 30.0


def _amqp_url() -> str:
    return os.environ.get("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")


async def get_connection() -> aio_pika.RobustConnection:
    """Retries the *initial* connection with exponential backoff.

    Found in practice: a Docker healthcheck can report RabbitMQ "healthy"
    microseconds before its AMQP listener actually accepts connections.
    `connect_robust()` handles reconnection after a connection drops, but
    a failure on the very first attempt raises immediately — and since
    every caller here is a bare `asyncio.create_task(start_consumer())`
    with no supervisor above it, that exception silently kills the
    consumer task forever while the service's HTTP endpoints keep working
    fine, with nothing in the logs to make it obvious short of grepping
    for "Connection refused" at startup.
    """
    delay = CONNECT_INITIAL_DELAY_SECONDS
    last_exc: Exception | None = None

    for attempt in range(1, CONNECT_MAX_ATTEMPTS + 1):
        try:
            return await aio_pika.connect_robust(_amqp_url())
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt == CONNECT_MAX_ATTEMPTS:
                break
            logger.warning(
                "RabbitMQ connection attempt %d/%d failed (%s), retrying in %.1fs",
                attempt,
                CONNECT_MAX_ATTEMPTS,
                exc,
                delay,
            )
            await asyncio.sleep(delay)
            delay = min(delay * 2, CONNECT_MAX_DELAY_SECONDS)

    raise ConnectionError(
        f"Could not connect to RabbitMQ after {CONNECT_MAX_ATTEMPTS} attempts"
    ) from last_exc


async def publish_event(
    channel: aio_pika.abc.AbstractChannel,
    exchange_name: str,
    routing_key: str,
    payload: dict[str, Any],
) -> None:
    exchange = await channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)
    message = Message(
        body=json.dumps(payload, default=_json_default).encode(),
        delivery_mode=DeliveryMode.PERSISTENT,
        content_type="application/json",
    )
    # channel must have been opened with publisher confirms (see get_confirm_channel)
    await exchange.publish(message, routing_key=routing_key)


async def get_confirm_channel(connection: aio_pika.abc.AbstractConnection) -> aio_pika.abc.AbstractChannel:
    channel = await connection.channel(publisher_confirms=True)
    return channel


async def declare_durable_queue_with_dlx(
    channel: aio_pika.abc.AbstractChannel,
    exchange_name: str,
    queue_name: str,
    routing_keys: list[str],
) -> aio_pika.abc.AbstractQueue:
    dlx_name = f"{exchange_name}.dlx"
    dlq_name = f"{queue_name}.dlq"

    dlx = await channel.declare_exchange(dlx_name, ExchangeType.TOPIC, durable=True)
    dlq = await channel.declare_queue(dlq_name, durable=True)
    await dlq.bind(dlx, routing_key="#")

    exchange = await channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)
    queue = await channel.declare_queue(
        queue_name,
        durable=True,
        arguments={
            "x-dead-letter-exchange": dlx_name,
        },
    )
    for key in routing_keys:
        await queue.bind(exchange, routing_key=key)
    return queue


def _retry_count(message: AbstractIncomingMessage) -> int:
    headers = message.headers or {}
    try:
        return int(headers.get("x-retry-count", 0))
    except (TypeError, ValueError):
        return 0


async def consume(
    channel: aio_pika.abc.AbstractChannel,
    queue: aio_pika.abc.AbstractQueue,
    exchange_name: str,
    handler: Callable[[dict[str, Any]], Awaitable[None]],
    is_processed: Callable[[str], Awaitable[bool]],
    mark_processed: Callable[[str], Awaitable[None]],
) -> None:
    """Consume messages with idempotent, bounded-retry processing.

    `is_processed`/`mark_processed` are backed by the calling service's own
    processed_events table (unique constraint on event_id) so redelivery
    after a crash never double-applies an event.

    IMPORTANT — what this actually guarantees, and what it doesn't:
    `handler(payload)` runs, and only *after* it returns successfully does
    `mark_processed(event_id)` run; only after *that* does this function's
    `message.process()` context manager ack the message back to the
    broker. That ordering means the processed_events check reliably
    catches redelivery that happens *after* both of those have already
    committed (e.g. the ack itself was lost in transit) — but it does
    nothing for a crash that lands *between* handler's own commit and
    mark_processed's commit (exactly what a "kill the container mid-burst"
    reliability test will probe). In that window, is_processed() is still
    False, so redelivery re-runs `handler` in full. Every handler passed
    here therefore needs its own idempotency check against its own
    schema (e.g. "does a row for this invoice_id/generation_job_id
    already exist") — the processed_events table is necessary but not
    sufficient on its own. Several handlers across this codebase were
    missing that second check and got fixed during a dedicated reliability
    pass; see each affected service's app/events.py for the specific
    "why this check exists" comment.

    Native RabbitMQ x-death headers only populate once a message has
    already been dead-lettered once, so a plain reject(requeue=False) on
    first failure would skip straight to the DLQ with zero retries. Instead
    we track our own x-retry-count header and manually republish to the
    same queue on failure, only dead-lettering once MAX_RETRIES is reached.
    """
    exchange = await channel.declare_exchange(exchange_name, ExchangeType.TOPIC, durable=True)

    async def on_message(message: AbstractIncomingMessage) -> None:
        async with message.process(requeue=False, ignore_processed=True):
            payload = json.loads(message.body)
            event_id = payload.get("event_id")

            if event_id and await is_processed(event_id):
                logger.info("skipping already-processed event %s", event_id)
                return

            try:
                await handler(payload)
            except Exception:
                retry_count = _retry_count(message) + 1
                if retry_count > MAX_RETRIES:
                    logger.exception(
                        "event exceeded %d retries, routing to DLX: %s", MAX_RETRIES, payload
                    )
                    await message.reject(requeue=False)
                    return

                logger.exception(
                    "handler failed (attempt %d/%d), requeuing: %s",
                    retry_count,
                    MAX_RETRIES,
                    payload,
                )
                retry_message = Message(
                    body=message.body,
                    delivery_mode=DeliveryMode.PERSISTENT,
                    content_type="application/json",
                    headers={**(message.headers or {}), "x-retry-count": retry_count},
                )
                await exchange.publish(retry_message, routing_key=message.routing_key or "")
                return

            if event_id:
                await mark_processed(event_id)

    await queue.consume(on_message)
