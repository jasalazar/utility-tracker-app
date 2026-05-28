"""
macOS notification channel — publishes a message to the Redis Pub/Sub channel
that the local macOS notifier daemon is subscribed to.

The daemon (notifier/daemon.py) runs as a LaunchAgent on the user's Mac and
calls osascript to display a native Notification Centre alert.
"""

import json
import logging

from backend.redis_client import get_redis

logger = logging.getLogger(__name__)


async def publish_macos_notification(
    uid: str,
    title: str,
    subtitle: str = "",
    body: str = "",
) -> None:
    """
    Publish a notification payload to the Redis channel `notify:{uid}`.
    The macOS daemon subscribed to that channel will display the alert.
    """
    channel = f"notify:{uid}"
    payload = json.dumps({
        "title": title,
        "subtitle": subtitle,
        "body": body,
    })

    r = get_redis()
    receivers = await r.publish(channel, payload)
    logger.debug(
        "macOS notification published uid=%s channel=%s receivers=%d",
        uid, channel, receivers,
    )
