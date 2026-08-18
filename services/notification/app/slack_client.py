import logging

import httpx

from app.config import settings

logger = logging.getLogger("notification.slack")


async def send_ops_alert(text: str) -> None:
    """Optional — Slack Incoming Webhooks need no OAuth app review, per
    the spec. With no webhook configured, this just logs instead of
    silently doing nothing, so ops alerts are still visible somewhere."""
    if not settings.slack_webhook_url:
        logger.warning("SLACK ALERT (no webhook configured): %s", text)
        return

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(settings.slack_webhook_url, json={"text": text})
        if response.status_code != 200:
            logger.warning("Slack webhook returned %s: %s", response.status_code, response.text)
