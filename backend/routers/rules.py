"""
Notification rules routes:
  GET  /api/rules       — fetch the user's current rules
  PUT  /api/rules       — replace all rules (and reschedule pending jobs)
  GET  /api/push-key    — return the VAPID public key for browser subscription
  POST /api/push-subscribe   — save a new Web Push subscription endpoint
  DELETE /api/push-subscribe — remove a Web Push subscription endpoint
"""

import logging
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator

from backend.auth.middleware import get_current_uid
from backend.config import settings
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["rules"])

VALID_CHANNELS = {"email", "browser_push", "ui_popup", "macos"}


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class NotificationRule(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    days_before: int = Field(ge=0, le=90, description="Days before the due date to fire")
    hour: int = Field(ge=0, le=23, description="Hour of day (user's local timezone)")
    minute: int = Field(ge=0, le=59, description="Minute of hour")
    channels: list[str] = Field(min_length=1, description="Notification channels to use")

    @field_validator("channels")
    @classmethod
    def validate_channels(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_CHANNELS
        if invalid:
            raise ValueError(f"Unknown channels: {invalid}. Valid: {VALID_CHANNELS}")
        return v


class RulesPayload(BaseModel):
    rules: list[NotificationRule]


class PushSubscription(BaseModel):
    endpoint: str
    keys: dict[str, Any]


# ---------------------------------------------------------------------------
# Rules endpoints
# ---------------------------------------------------------------------------

@router.get("/rules")
async def get_rules(uid: str = Depends(get_current_uid)) -> dict:
    rc = redis_client()
    rules = await rc.get_rules(uid)
    return {"rules": rules}


@router.put("/rules")
async def update_rules(body: RulesPayload, uid: str = Depends(get_current_uid)) -> dict:
    """
    Replace all notification rules for the user.
    Existing scheduled jobs are NOT retroactively cancelled here (APScheduler
    manages that via the Redis job store). Future payments will use the new rules.
    """
    rc = redis_client()
    rules_dicts = [r.model_dump() for r in body.rules]
    await rc.save_rules(uid, rules_dicts)
    logger.info("Rules updated for uid=%s count=%d", uid, len(rules_dicts))
    return {"rules": rules_dicts}


# ---------------------------------------------------------------------------
# Web Push endpoints
# ---------------------------------------------------------------------------

@router.get("/push-key")
async def get_vapid_public_key(_uid: str = Depends(get_current_uid)) -> dict:
    """Return the VAPID public key so the browser can subscribe."""
    return {"publicKey": settings.vapid_public_key}


@router.post("/push-subscribe", status_code=status.HTTP_201_CREATED)
async def subscribe_push(
    body: PushSubscription,
    uid: str = Depends(get_current_uid),
) -> dict:
    """Register a browser push subscription endpoint for the user."""
    rc = redis_client()
    await rc.add_push_subscription(uid, body.model_dump())
    return {"status": "subscribed"}


@router.delete("/push-subscribe", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_push(
    body: PushSubscription,
    uid: str = Depends(get_current_uid),
) -> None:
    """Remove a browser push subscription."""
    rc = redis_client()
    await rc.remove_push_subscription(uid, body.model_dump())
