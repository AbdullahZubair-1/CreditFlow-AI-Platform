import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from sqlalchemy import select

from app import email_client
from app.db import async_session_factory
from app.email_client import EmailError
from app.models import NotificationLog
from py_shared.rabbitmq import get_confirm_channel, get_connection, publish_event

logger = logging.getLogger("notification.notify")

DOMAIN_EVENTS_EXCHANGE = "domain_events"

_connection: aio_pika.abc.AbstractConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None


async def _get_channel() -> aio_pika.abc.AbstractChannel:
    global _connection, _channel
    if _channel is None or _channel.is_closed:
        _connection = await get_connection()
        _channel = await get_confirm_channel(_connection)
    return _channel


async def _publish_notification_sent(notification_type: str, recipient_email: str) -> None:
    try:
        channel = await _get_channel()
        envelope = {
            "event_id": str(uuid.uuid4()),
            "event_type": "notification.sent",
            "occurred_at": datetime.now(UTC).isoformat(),
            "data": {"notification_type": notification_type, "recipient_email": recipient_email},
        }
        await publish_event(channel, DOMAIN_EVENTS_EXCHANGE, "notification.sent", envelope)
    except Exception:  # noqa: BLE001
        logger.exception("failed to publish notification.sent for %s", notification_type)


async def send_and_log(
    notification_type: str, recipient_email: str, subject: str, html: str, event_id: str | None = None
) -> None:
    """Sends the email, and — regardless of success or failure — logs it
    to notification_log for auditing, per the spec's explicit requirement
    ("Log every notification sent (type, recipient, status)").

    event_id is this handler's own idempotency check (see the comment on
    NotificationLog.source_event_id) — a crash between send_email()
    succeeding and this function's own commit would otherwise cause a
    redelivered event to send the same email twice."""
    if event_id:
        async with async_session_factory() as session:
            already_sent = await session.scalar(
                select(NotificationLog).where(
                    NotificationLog.source_event_id == event_id, NotificationLog.status == "sent"
                )
            )
            if already_sent:
                logger.info("skipping duplicate send for event %s (%s)", event_id, notification_type)
                return

    try:
        message_id = await email_client.send_email(recipient_email, subject, html)
    except EmailError as exc:
        async with async_session_factory() as session:
            session.add(
                NotificationLog(
                    source_event_id=event_id,
                    notification_type=notification_type,
                    recipient_email=recipient_email,
                    subject=subject,
                    status="failed",
                    error_reason=str(exc)[:255],
                )
            )
            await session.commit()
        logger.exception("failed to send %s email to %s", notification_type, recipient_email)
        return

    async with async_session_factory() as session:
        session.add(
            NotificationLog(
                source_event_id=event_id,
                notification_type=notification_type,
                recipient_email=recipient_email,
                subject=subject,
                status="sent",
                provider_message_id=message_id,
            )
        )
        await session.commit()

    await _publish_notification_sent(notification_type, recipient_email)
