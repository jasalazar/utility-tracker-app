"""
WebSocket connection registry and broadcast helpers.

Maintains an in-memory map of uid → set of active WebSocket connections.
When the server broadcasts to a uid, every open tab for that user receives
the message and displays it as a popup toast.

Connection state is intentionally in-memory (not Redis) because WebSocket
handles are not serialisable and are scoped to the current process lifetime.
"""

import json
import logging
import asyncio
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# uid → set of connected WebSocket objects
_connections: dict[str, set[WebSocket]] = defaultdict(set)
_lock = asyncio.Lock()


async def connect(uid: str, ws: WebSocket) -> None:
    """Register a new WebSocket connection for uid."""
    await ws.accept()
    async with _lock:
        _connections[uid].add(ws)
    logger.info("WebSocket connected uid=%s open_connections=%d", uid, len(_connections[uid]))


async def disconnect(uid: str, ws: WebSocket) -> None:
    """Unregister a WebSocket connection."""
    async with _lock:
        _connections[uid].discard(ws)
        if not _connections[uid]:
            del _connections[uid]
    logger.info("WebSocket disconnected uid=%s", uid)


async def broadcast_to_user(uid: str, payload: Any) -> None:
    """
    Send a JSON payload to all open WebSocket connections for uid.
    Silently removes dead connections.
    """
    async with _lock:
        sockets = set(_connections.get(uid, set()))

    if not sockets:
        logger.info("broadcast_to_user: no active sockets for uid=%s — message not delivered", uid)
        return

    dead: list[WebSocket] = []
    message = json.dumps(payload)

    for ws in sockets:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)

    if dead:
        async with _lock:
            for ws in dead:
                _connections[uid].discard(ws)
