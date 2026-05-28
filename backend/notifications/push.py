"""
Browser / Web Push notification channel (VAPID).

Pushes work even when the browser tab is closed, as long as the browser
is running and the user has granted the Notification permission.
"""

import json
import logging
from pywebpush import webpush, WebPushException

from backend.config import settings
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)


async def send_push_to_user(uid: str, title: str, body: str, url: str = "/") -> None:
    """
    Send a Web Push notification to all registered browser endpoints for uid.
    Stale or invalid subscriptions are automatically removed.
    """
    rc = redis_client()
    subscriptions = await rc.get_push_subscriptions(uid)

    if not subscriptions:
        logger.debug("No push subscriptions for uid=%s", uid)
        return

    payload = json.dumps({"title": title, "body": body, "url": url})
    stale: list[dict] = []

    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=settings.vapid_private_key,
                vapid_claims={"sub": settings.vapid_email},
            )
            logger.debug("Push sent to uid=%s endpoint=%s", uid, sub.get("endpoint", "")[:40])
        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response else None
            if status_code in (404, 410):
                # Subscription no longer valid — remove it.
                stale.append(sub)
                logger.info("Removed stale push subscription for uid=%s", uid)
            else:
                logger.error("WebPush failed uid=%s: %s", uid, exc)
        except Exception as exc:
            logger.error("Unexpected push error uid=%s: %s", uid, exc)

    for sub in stale:
        await rc.remove_push_subscription(uid, sub)
