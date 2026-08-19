import uuid
from email.message import EmailMessage

import aiosmtplib

from app.core.config import settings


class EmailError(Exception):
    pass


async def send_email(to: str, subject: str, html: str) -> str:
    """Returns a locally-generated message id — plain SMTP has no
    equivalent to Resend's API returning one in the response body, so
    NotificationLog.provider_message_id is only a delivery receipt from
    Resend's own API, not something SMTP servers hand back the same way."""
    message = EmailMessage()
    message["From"] = settings.smtp_from_email
    message["To"] = to
    message["Subject"] = subject
    message.set_content("This email requires an HTML-capable client to view.")
    message.add_alternative(html, subtype="html")

    try:
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_username,
            password=settings.smtp_password,
            start_tls=True,
        )
    except aiosmtplib.SMTPException as exc:
        raise EmailError(f"SMTP send to {settings.smtp_host}:{settings.smtp_port} failed: {exc}") from exc

    return str(uuid.uuid4())
