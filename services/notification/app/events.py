import logging
from typing import Any

import aio_pika

from app import identity_resolver, notify, slack_client, templates
from app.db import async_session_factory
from app.identity_resolver import ResolutionError
from app.models import ProcessedEvent
from py_shared.rabbitmq import consume, declare_durable_queue_with_dlx, get_confirm_channel, get_connection

logger = logging.getLogger("notification.events")

USER_EVENTS_EXCHANGE = "user_events"
DOMAIN_EVENTS_EXCHANGE = "domain_events"
BILLING_EVENTS_EXCHANGE = "billing_events"
SOCIAL_EVENTS_EXCHANGE = "social_events"
USAGE_EVENTS_EXCHANGE = "usage_events"

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await get_connection()
        _channel = await get_confirm_channel(_connection)
    return _channel


async def _is_processed(event_id: str) -> bool:
    async with async_session_factory() as session:
        return await session.get(ProcessedEvent, event_id) is not None


async def _mark_processed(event_id: str) -> None:
    async with async_session_factory() as session:
        session.add(ProcessedEvent(event_id=event_id))
        await session.commit()


# --- user_events ---


async def _handle_user_registered(payload: dict[str, Any]) -> None:
    data = payload["data"]
    subject, html = templates.verification_email(data["verification_token"])
    await notify.send_and_log("user.registered", data["email"], subject, html, payload.get("event_id"))


async def _handle_password_reset_requested(payload: dict[str, Any]) -> None:
    data = payload["data"]
    subject, html = templates.password_reset_email(data["otp"])
    await notify.send_and_log("user.password_reset_requested", data["email"], subject, html, payload.get("event_id"))


async def _route_user_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "user.registered":
        await _handle_user_registered(payload)
    elif event_type == "user.password_reset_requested":
        await _handle_password_reset_requested(payload)


# --- domain_events ---


async def _handle_invite_created(payload: dict[str, Any]) -> None:
    data = payload["data"]
    subject, html = templates.invite_email(data["token"], data["role"])
    await notify.send_and_log("invite.created", data["email"], subject, html, payload.get("event_id"))


async def _handle_member_joined(payload: dict[str, Any]) -> None:
    data = payload["data"]
    try:
        email = await identity_resolver.resolve_email_by_user_id(data["user_id"])
    except ResolutionError:
        logger.exception("could not resolve email for member.joined, skipping notification")
        return
    subject, html = templates.member_joined_email(data["role"])
    await notify.send_and_log("member.joined", email, subject, html, payload.get("event_id"))


async def _handle_usage_threshold_reached(payload: dict[str, Any]) -> None:
    data = payload["data"]
    try:
        email = await identity_resolver.resolve_owner_email(data["account_id"])
    except ResolutionError:
        logger.exception("could not resolve owner email for usage.threshold_reached, skipping notification")
        return
    subject, html = templates.usage_threshold_email(data["threshold"], data["used_tokens"], data["quota_tokens"])
    await notify.send_and_log("usage.threshold_reached", email, subject, html, payload.get("event_id"))


async def _route_domain_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "invite.created":
        await _handle_invite_created(payload)
    elif event_type == "member.joined":
        await _handle_member_joined(payload)


# --- billing_events ---


async def _handle_invoice_paid(payload: dict[str, Any]) -> None:
    data = payload["data"]
    try:
        email = await identity_resolver.resolve_owner_email(data["account_id"])
    except ResolutionError:
        logger.exception("could not resolve owner email for invoice.paid, skipping notification")
        return
    subject, html = templates.invoice_paid_email(data["amount_cents"], data.get("plan_tier", "free"))
    await notify.send_and_log("invoice.paid", email, subject, html, payload.get("event_id"))


async def _handle_payment_failed(payload: dict[str, Any]) -> None:
    data = payload["data"]
    try:
        email = await identity_resolver.resolve_owner_email(data["account_id"])
    except ResolutionError:
        logger.exception("could not resolve owner email for payment.failed, skipping notification")
        return
    subject, html = templates.payment_failed_email()
    await notify.send_and_log("payment.failed", email, subject, html, payload.get("event_id"))
    await slack_client.send_ops_alert(f"Payment failed for account {data['account_id']}")


async def _route_billing_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "invoice.paid":
        await _handle_invoice_paid(payload)
    elif event_type == "payment.failed":
        await _handle_payment_failed(payload)


# --- social_events ---


async def _handle_post_published(payload: dict[str, Any]) -> None:
    data = payload["data"]
    try:
        email = await identity_resolver.resolve_owner_email(data["account_id"])
    except ResolutionError:
        logger.exception("could not resolve owner email for post.published, skipping notification")
        return
    subject, html = templates.post_published_email(data["linkedin_post_id"])
    await notify.send_and_log("post.published", email, subject, html, payload.get("event_id"))


async def _handle_post_failed(payload: dict[str, Any]) -> None:
    data = payload["data"]
    try:
        email = await identity_resolver.resolve_owner_email(data["account_id"])
    except ResolutionError:
        logger.exception("could not resolve owner email for post.failed, skipping notification")
    else:
        subject, html = templates.post_failed_email(data["reason"])
        await notify.send_and_log("post.failed", email, subject, html, payload.get("event_id"))

    await slack_client.send_ops_alert(f"Post failed for account {data['account_id']}: {data['reason']}")


async def _route_social_event(payload: dict[str, Any]) -> None:
    event_type = payload.get("event_type")
    if event_type == "post.published":
        await _handle_post_published(payload)
    elif event_type == "post.failed":
        await _handle_post_failed(payload)


async def start_consumers() -> None:
    channel = await get_channel()

    user_queue = await declare_durable_queue_with_dlx(
        channel,
        USER_EVENTS_EXCHANGE,
        "notification.user_events",
        routing_keys=["user.registered", "user.password_reset_requested"],
    )
    domain_queue = await declare_durable_queue_with_dlx(
        channel,
        DOMAIN_EVENTS_EXCHANGE,
        "notification.domain_events",
        routing_keys=["invite.created", "member.joined"],
    )
    usage_queue = await declare_durable_queue_with_dlx(
        channel, USAGE_EVENTS_EXCHANGE, "notification.usage_events", routing_keys=["usage.threshold_reached"]
    )
    billing_queue = await declare_durable_queue_with_dlx(
        channel, BILLING_EVENTS_EXCHANGE, "notification.billing_events", routing_keys=["invoice.paid", "payment.failed"]
    )
    social_queue = await declare_durable_queue_with_dlx(
        channel, SOCIAL_EVENTS_EXCHANGE, "notification.social_events", routing_keys=["post.published", "post.failed"]
    )

    await consume(channel, user_queue, USER_EVENTS_EXCHANGE, _route_user_event, _is_processed, _mark_processed)
    await consume(channel, domain_queue, DOMAIN_EVENTS_EXCHANGE, _route_domain_event, _is_processed, _mark_processed)
    await consume(channel, billing_queue, BILLING_EVENTS_EXCHANGE, _route_billing_event, _is_processed, _mark_processed)
    await consume(channel, social_queue, SOCIAL_EVENTS_EXCHANGE, _route_social_event, _is_processed, _mark_processed)
    await consume(
        channel, usage_queue, USAGE_EVENTS_EXCHANGE, _handle_usage_threshold_reached, _is_processed, _mark_processed
    )

    logger.info(
        "notification consumers listening on user_events, domain_events, billing_events, social_events, usage_events"
    )
