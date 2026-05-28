#!/usr/bin/env python3
"""
macOS Notifier Daemon
=====================
Subscribes to Redis Pub/Sub channels `notify:*` and fires native macOS
Notification Centre alerts via osascript.

Run directly:   python notifier/daemon.py
Install as LaunchAgent: python notifier/install.py
"""

import json
import logging
import os
import subprocess
import sys
import time

import redis

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("notifier")

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
PATTERN = "notify:*"


def show_notification(title: str, subtitle: str = "", body: str = "") -> None:
    """
    Display a native macOS notification via osascript.
    The `display notification` command supports title, subtitle, and body.
    """
    # Escape double-quotes to prevent injection.
    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace('"', '\\"')

    script = f'display notification "{esc(body)}" with title "{esc(title)}"'
    if subtitle:
        script += f' subtitle "{esc(subtitle)}"'

    try:
        subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            timeout=5,
        )
        logger.info("Notification shown: %s", title)
    except subprocess.CalledProcessError as exc:
        logger.error("osascript failed: %s", exc.stderr.decode())
    except FileNotFoundError:
        logger.error("osascript not found — are you running on macOS?")
    except subprocess.TimeoutExpired:
        logger.warning("osascript timed out")


def run() -> None:
    logger.info("Connecting to Redis at %s", REDIS_URL)
    r = redis.from_url(REDIS_URL, decode_responses=True)

    # Verify connection.
    try:
        r.ping()
    except redis.ConnectionError as exc:
        logger.error("Cannot connect to Redis: %s", exc)
        sys.exit(1)

    pubsub = r.pubsub()
    pubsub.psubscribe(PATTERN)
    logger.info("Subscribed to pattern '%s'. Waiting for notifications…", PATTERN)

    for message in pubsub.listen():
        if message["type"] != "pmessage":
            continue

        try:
            payload = json.loads(message["data"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("Malformed message: %s", message["data"])
            continue

        title = payload.get("title", "Utility Tracker")
        subtitle = payload.get("subtitle", "")
        body = payload.get("body", "")

        logger.info("Received notification — title=%s", title)
        show_notification(title, subtitle, body)


if __name__ == "__main__":
    while True:
        try:
            run()
        except Exception as exc:
            logger.error("Daemon crashed: %s — restarting in 10s", exc)
            time.sleep(10)
