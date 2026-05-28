"""
LangGraph: Email Processing Pipeline
=====================================

Graph nodes (in execution order):
  fetch_email        — pull full email body from Gmail API
  classify           — Claude decides: utility email or not?
  extract            — Claude extracts service / amount / due-date
  persist            — write payment record to Redis
  plan_notifications — schedule APScheduler jobs per user's rules

Conditional edge after classify:
  is_utility=True  → extract
  is_utility=False → END  (logged to LangSmith, nothing stored)
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, TypedDict

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import StateGraph, END
from pydantic import BaseModel, Field
from googleapiclient.discovery import build

from backend.config import settings
from backend.redis_client import redis_client
from backend.auth.oauth import get_valid_credentials

from langsmith import traceable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------

_llm = ChatAnthropic(model=settings.anthropic_model, temperature=0)


# ---------------------------------------------------------------------------
# Pydantic schemas for structured Claude output
# ---------------------------------------------------------------------------

class ClassificationResult(BaseModel):
    is_utility: bool = Field(description="True if this email is a utility or subscription payment notification")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score between 0 and 1")
    reason: str = Field(description="One-line explanation of the decision")


class PaymentExtraction(BaseModel):
    service_name: str = Field(description="Name of the utility or service provider (e.g. 'Eversource', 'Comcast')")
    amount: float = Field(description="Payment amount as a decimal number")
    currency: str = Field(default="CAD", description="ISO 4217 currency code")
    due_date: str = Field(description="Payment due date in YYYY-MM-DD format")
    account_number: Optional[str] = Field(default=None, description="Account or customer number if visible")
    confirmation_number: Optional[str] = Field(default=None, description="Confirmation or reference number if visible")


# ---------------------------------------------------------------------------
# Pipeline state
# ---------------------------------------------------------------------------

class EmailPipelineState(TypedDict):
    uid: str
    history_id: str
    # Set by fetch_email
    message_id: Optional[str]
    email_subject: Optional[str]
    email_body: Optional[str]
    email_sender: Optional[str]
    # Set by classify
    is_utility: bool
    classification_confidence: float
    classification_reason: str
    # Set by extract
    service_name: Optional[str]
    amount: Optional[float]
    currency: str
    due_date: Optional[str]
    account_number: Optional[str]
    confirmation_number: Optional[str]
    # Set by persist
    payment_id: Optional[str]
    # Accumulated errors (non-fatal)
    errors: list[str]


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

async def fetch_email(state: EmailPipelineState) -> dict:
    """
    Use the Gmail history API to find messages added since the last known
    history ID, then fetch the most recent one.
    """
    uid = state["uid"]
    history_id = state["history_id"]

    creds = await get_valid_credentials(uid)
    if not creds:
        return {"errors": state["errors"] + ["No credentials for uid"]}

    service = build("gmail", "v1", credentials=creds)
    rc = redis_client()
    watch = await rc.get_gmail_watch(uid)
    last_history_id = watch.get("history_id", history_id) if watch else history_id

    # List messages added since last checkpoint.
    try:
        history = service.users().history().list(
            userId="me",
            startHistoryId=last_history_id,
            historyTypes=["messageAdded"],
        ).execute()
    except Exception as exc:
        logger.error("fetch_email history list failed: %s", exc)
        return {"errors": state["errors"] + [str(exc)]}

    messages = []
    for record in history.get("history", []):
        for added in record.get("messagesAdded", []):
            messages.append(added["message"]["id"])

    # Update stored history ID.
    await rc.save_gmail_watch(uid, {
        "history_id": history_id,
        "watch_expiry": watch.get("watch_expiry", "0") if watch else "0",
    })

    if not messages:
        return {"errors": state["errors"] + ["No new messages in history"]}

    # Process the most recently added message.
    msg_id = messages[-1]

    # Guard: skip if we already processed this Gmail message.
    if await rc.payment_exists_for_email(uid, msg_id):
        return {"errors": state["errors"] + [f"Message {msg_id} already processed"]}

    # Fetch the full message.
    try:
        msg = service.users().messages().get(
            userId="me", id=msg_id, format="full"
        ).execute()
    except Exception as exc:
        logger.error("fetch_email get message failed: %s", exc)
        return {"errors": state["errors"] + [str(exc)]}

    # Extract subject.
    headers = {h["name"]: h["value"] for h in msg["payload"].get("headers", [])}
    subject = headers.get("Subject", "(no subject)")
    sender = headers.get("From", "")

    # Extract body — prefer plain text.
    body = _extract_body(msg["payload"])

    return {
        "message_id": msg_id,
        "email_subject": subject,
        "email_body": body,
        "email_sender": sender,
    }


def _extract_body(payload: dict) -> str:
    """Recursively extract plain-text body from a Gmail message payload."""
    import base64

    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")

    if mime_type == "text/plain" and body_data:
        return base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = _extract_body(part)
        if result:
            return result

    # Fall back to HTML if no plain text.
    if mime_type == "text/html" and body_data:
        raw = base64.urlsafe_b64decode(body_data + "==").decode("utf-8", errors="replace")
        # Very rough HTML strip — sufficient for LLM context.
        import re
        return re.sub(r"<[^>]+>", " ", raw)

    return ""

@traceable
async def classify(state: EmailPipelineState) -> dict:
    """Ask Claude whether this email is a utility/service payment notice."""
    if not state.get("email_body") and not state.get("email_subject"):
        return {
            "is_utility": False,
            "classification_confidence": 0.0,
            "classification_reason": "No email content available",
        }

    structured_llm = _llm.with_structured_output(ClassificationResult)

    messages = [
        SystemMessage(content=(
            "You are an expert at identifying household utility and subscription "
            "payment notification emails. Classify the following email."
        )),
        HumanMessage(content=(
            f"Subject: {state.get('email_subject', '')}\n\n"
            f"From: {state.get('email_sender', '')}\n\n"
            f"Body:\n{state.get('email_body', '')[:4000]}"
        )),
    ]

    try:
        result: ClassificationResult = await structured_llm.ainvoke(messages)
    except Exception as exc:
        logger.error("classify LLM call failed: %s", exc)
        return {
            "is_utility": False,
            "classification_confidence": 0.0,
            "classification_reason": f"LLM error: {exc}",
        }

    logger.info(
        "classify: is_utility=%s confidence=%.2f reason=%s",
        result.is_utility, result.confidence, result.reason,
    )
    return {
        "is_utility": result.is_utility,
        "classification_confidence": result.confidence,
        "classification_reason": result.reason,
    }

@traceable
async def extract(state: EmailPipelineState) -> dict:
    """Ask Claude to extract structured payment details from the email."""
    structured_llm = _llm.with_structured_output(PaymentExtraction)

    messages = [
        SystemMessage(content=(
            "You are an expert at extracting payment information from utility and "
            "subscription emails. Extract the payment details accurately. "
            "Use YYYY-MM-DD format for dates. If the due date is not explicit but "
            "a billing period end date is present, use that. "
            "Amount should be a decimal number without currency symbols."
        )),
        HumanMessage(content=(
            f"Subject: {state.get('email_subject', '')}\n\n"
            f"From: {state.get('email_sender', '')}\n\n"
            f"Body:\n{state.get('email_body', '')[:4000]}"
        )),
    ]

    try:
        result: PaymentExtraction = await structured_llm.ainvoke(messages)
    except Exception as exc:
        logger.error("extract LLM call failed: %s", exc)
        return {"errors": state["errors"] + [f"Extraction error: {exc}"]}

    return {
        "service_name": result.service_name,
        "amount": result.amount,
        "currency": result.currency,
        "due_date": result.due_date,
        "account_number": result.account_number,
        "confirmation_number": result.confirmation_number,
    }


async def persist(state: EmailPipelineState) -> dict:
    """Write the extracted payment record to Redis."""
    if not state.get("due_date") or not state.get("amount"):
        return {"errors": state["errors"] + ["Missing required fields after extraction"]}

    payment_id = str(uuid.uuid4())
    uid = state["uid"]

    # Compute UTC epoch for the due date (used as ZSET score).
    try:
        due_dt = datetime.strptime(state["due_date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        due_epoch = due_dt.timestamp()
    except ValueError:
        due_epoch = 0.0

    rc = redis_client()
    await rc.save_payment(uid, payment_id, {
        "payment_id": payment_id,
        "service_name": state.get("service_name", "Unknown"),
        "amount": str(state.get("amount", 0)),
        "currency": state.get("currency", "CAD"),
        "due_date": state.get("due_date", ""),
        "due_epoch": str(due_epoch),
        "account_number": state.get("account_number") or "",
        "confirmation_number": state.get("confirmation_number") or "",
        "status": "pending",
        "email_subject": state.get("email_subject", ""),
        "email_id": state.get("message_id", ""),
        "email_sender": state.get("email_sender", ""),
        "created_at": str(int(datetime.now(timezone.utc).timestamp())),
    })

    logger.info("Payment persisted: uid=%s payment_id=%s service=%s due=%s",
                uid, payment_id, state.get("service_name"), state.get("due_date"))

    service = state.get("service_name", "Unknown")
    amount  = str(state.get("amount", 0))
    currency = state.get("currency", "CAD")
    due_date = state.get("due_date", "")

    # Push a real-time event so the Dashboard refreshes immediately.
    try:
        from backend.notifications.websocket import broadcast_to_user
        logger.info("Broadcasting payment_added to uid=%s", uid)
        await broadcast_to_user(uid, {
            "type": "payment_added",
            "payment_id": payment_id,
            "service_name": service,
            "amount": amount,
            "currency": currency,
            "due_date": due_date,
        })
    except Exception as exc:
        logger.warning("broadcast_to_user failed (non-fatal): %s", exc)

    # Immediately notify the macOS daemon so the user sees a Notification
    # Centre alert the moment the bill is detected — separate from the
    # scheduled reminders that fire before the due date.
    try:
        from backend.notifications.macos_pub import publish_macos_notification
        await publish_macos_notification(
            uid=uid,
            title=f"New bill detected: {service}",
            subtitle=f"Due {due_date}",
            body=f"{currency} {amount}",
        )
    except Exception as exc:
        logger.warning("macOS immediate notification failed (non-fatal): %s", exc)

    return {"payment_id": payment_id}


async def plan_notifications(state: EmailPipelineState) -> dict:
    """
    Schedule APScheduler notification jobs based on the user's rules.
    Import is deferred to avoid circular imports (scheduler imports agents).
    """
    if not state.get("payment_id"):
        return {}

    from backend.scheduler.jobs import schedule_payment_notifications
    await schedule_payment_notifications(
        uid=state["uid"],
        payment_id=state["payment_id"],
        due_date_str=state.get("due_date", ""),
    )
    return {}


# ---------------------------------------------------------------------------
# Conditional edge router
# ---------------------------------------------------------------------------

def _route_after_classify(state: EmailPipelineState) -> str:
    if state.get("is_utility") and state.get("email_body"):
        return "extract"
    return END


# ---------------------------------------------------------------------------
# Build and compile the graph
# ---------------------------------------------------------------------------

def build_email_pipeline():
    graph = StateGraph(EmailPipelineState)

    graph.add_node("fetch_email", fetch_email)
    graph.add_node("classify", classify)
    graph.add_node("extract", extract)
    graph.add_node("persist", persist)
    graph.add_node("plan_notifications", plan_notifications)

    graph.set_entry_point("fetch_email")
    graph.add_edge("fetch_email", "classify")
    graph.add_conditional_edges("classify", _route_after_classify, {"extract": "extract", END: END})
    graph.add_edge("extract", "persist")
    graph.add_edge("persist", "plan_notifications")
    graph.add_edge("plan_notifications", END)

    return graph.compile()


# Compiled graph — import and call .ainvoke() from the webhook handler.
email_pipeline = build_email_pipeline()
