"""Inbound webhook verification, dedup, and relay-to-RabbitMQ.

Per the Gateway's spec responsibilities: verify the provider's signature,
deduplicate by event id (Redis SETNX, 24h TTL), then publish a normalized
event onto the webhook_events topic exchange so the owning service (e.g.
Billing for Stripe) can consume and process it — the Gateway itself never
touches the domain state.
"""
import logging
from datetime import UTC, datetime

import aio_pika
import stripe

from app.config import settings
from app.redis_client import get_client
from py_shared.rabbitmq import get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("gateway.webhooks")

WEBHOOK_EVENTS_EXCHANGE = "webhook_events"

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await get_connection()
        _channel = await get_confirm_channel(_connection)
    return _channel


async def _dedup(event_id: str) -> bool:
    """Returns True if this is the first time we've seen event_id."""
    client = get_client()
    is_new = await client.setnx(f"webhook_dedup:{event_id}", "1")
    if is_new:
        await client.expire(f"webhook_dedup:{event_id}", settings.webhook_dedup_ttl_seconds)
    return bool(is_new)


async def handle_stripe_webhook(payload: bytes, sig_header: str) -> None:
    event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)

    if not await _dedup(event["id"]):
        logger.info("duplicate stripe webhook %s, skipping relay", event["id"])
        return

    channel = await get_channel()
    envelope = {
        "event_id": event["id"],
        "event_type": f"billing.{event['type']}",
        "occurred_at": datetime.now(UTC).isoformat(),
        # stripe.Event is a StripeObject, not a plain dict — dict-like
        # access (event["id"], event["type"]) works fine on it, but
        # json.dumps (inside publish_event) can't serialize it directly
        # and raised a TypeError on every single webhook delivery. This
        # silently 500'd the relay to RabbitMQ for every Stripe event
        # ever received, so nothing billing-related (plan upgrades,
        # invoices, credit grants) ever actually settled.
        "data": event.to_dict(),
    }
    await publish_event(channel, WEBHOOK_EVENTS_EXCHANGE, envelope["event_type"], envelope)
