"""
Gmail Pub/Sub webhook endpoint.

Google pushes a notification here every time a new email arrives in any
enrolled user's inbox. The handler:
  1. Verifies the secret token in the query string.
  2. Decodes the base64 Pub/Sub message.
  3. Resolves the Gmail address to an internal uid.
  4. Fires the LangGraph email pipeline as a background task.
"""

import base64
import json
import logging
import asyncio

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status

from backend.config import settings
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter()


async def _run_pipeline(uid: str, history_id: str) -> None:
    """Run the email pipeline in the background."""
    from backend.agents.email_pipeline import email_pipeline
    try:
        await email_pipeline.ainvoke({
            "uid": uid,
            "history_id": history_id,
            "message_id": None,
            "email_subject": None,
            "email_body": None,
            "email_sender": None,
            "is_utility": False,
            "classification_confidence": 0.0,
            "classification_reason": "",
            "service_name": None,
            "amount": None,
            "currency": "USD",
            "due_date": None,
            "account_number": None,
            "confirmation_number": None,
            "payment_id": None,
            "errors": [],
        })
    except Exception as exc:
        logger.error("Email pipeline failed uid=%s history_id=%s: %s", uid, history_id, exc)


@router.post("/webhook/gmail")
async def gmail_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    token: str = Query(..., description="Verification token"),
) -> dict:
    """
    Receive a Gmail push notification from Google Cloud Pub/Sub.
    Responds with 204 immediately; pipeline runs in the background.
    """
    # 1. Verify the shared secret token.
    if token != settings.pubsub_webhook_token:
        logger.warning("Webhook called with invalid token")
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")

    # 2. Parse the Pub/Sub envelope.
    body = await request.json()
    message = body.get("message", {})
    data_b64 = message.get("data", "")

    if not data_b64:
        # Google sends an empty message on initial subscription — acknowledge it.
        return {"status": "ok"}

    try:
        data = json.loads(base64.b64decode(data_b64).decode("utf-8"))
    except Exception as exc:
        logger.error("Failed to decode Pub/Sub message: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Bad message payload")

    email_address: str = data.get("emailAddress", "")
    history_id: str = str(data.get("historyId", ""))

    if not email_address or not history_id:
        return {"status": "ignored", "reason": "missing fields"}

    # 3. Resolve Gmail address → uid.
    rc = redis_client()
    uid = await rc.uid_from_email(email_address)
    if not uid:
        logger.warning("Webhook: no uid found for email=%s", email_address)
        return {"status": "ignored", "reason": "unknown user"}

    # 4. Fire the pipeline as a background task so we return 200 quickly.
    #    Google Pub/Sub will retry if we return a non-2xx status.
    background_tasks.add_task(_run_pipeline, uid, history_id)
    logger.info("Pipeline enqueued uid=%s history_id=%s", uid, history_id)

    return {"status": "accepted"}
