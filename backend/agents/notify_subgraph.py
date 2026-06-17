"""
LangGraph: Notification Dispatch Subgraph
==========================================

Invoked by the APScheduler at each scheduled fire time. Loads the payment
record and fires the appropriate notification channels in parallel.

Graph nodes:
  load_payment   — fetch record + user profile from Redis
  dispatch       — fan out to all enabled channels concurrently
"""

import asyncio
import logging
from typing import TypedDict, Optional

from langgraph.graph import StateGraph, END

from backend.redis_client import redis_client

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

class NotifyState(TypedDict):
    uid: str
    payment_id: str
    job_id: str
    channels: list[str]
    # Populated by load_payment
    payment: Optional[dict]
    user_profile: Optional[dict]
    # Results per channel
    results: dict[str, bool]


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------

async def load_payment(state: NotifyState) -> dict:
    rc = redis_client()
    payment = await rc.get_payment(state["uid"], state["payment_id"])
    profile = await rc.get_user_profile(state["uid"])
    return {"payment": payment, "user_profile": profile}


async def dispatch(state: NotifyState) -> dict:
    """Fan out notifications to all configured channels concurrently."""
    if not state.get("payment"):
        logger.warning("dispatch: payment not found uid=%s pid=%s", state["uid"], state["payment_id"])
        return {"results": {}}

    channels = state.get("channels", [])
    tasks = {}

    # Email channel is currently DISABLED (the app no longer requests the
    # gmail.send scope). _send_email is retained below, unwired, for future
    # re-enablement via a system mailer.
    if "browser_push" in channels:
        tasks["browser_push"] = _send_browser_push(state)
    if "ui_popup" in channels:
        tasks["ui_popup"] = _send_ui_popup(state)
    if "macos" in channels:
        tasks["macos"] = _send_macos(state)

    results = {}
    if tasks:
        settled = await asyncio.gather(*tasks.values(), return_exceptions=True)
        for channel, outcome in zip(tasks.keys(), settled):
            if isinstance(outcome, Exception):
                logger.error("Channel %s failed: %s", channel, outcome)
                results[channel] = False
            else:
                results[channel] = outcome

    # Mark the job as sent in Redis.
    rc = redis_client()
    await rc.mark_notify_job_sent(state["uid"], state["job_id"])

    return {"results": results}


# ---------------------------------------------------------------------------
# Per-channel senders (delegate to notification modules)
# ---------------------------------------------------------------------------

async def _send_email(state: NotifyState) -> bool:
    """INACTIVE — not wired into dispatch. The email reminder channel is disabled
    because the app dropped the gmail.send scope to stay least-intrusive. Kept
    (with backend/notifications/email.py) for future re-enablement via a system
    mailer. See the project backlog.
    """
    from backend.notifications.email import send_payment_reminder
    try:
        profile = state["user_profile"] or {}
        payment = state["payment"] or {}
        await send_payment_reminder(
            to_email=profile.get("email", ""),
            user_name=profile.get("name", ""),
            payment=payment,
        )
        return True
    except Exception as exc:
        logger.error("Email send failed: %s", exc)
        return False


async def _send_browser_push(state: NotifyState) -> bool:
    from backend.notifications.push import send_push_to_user
    try:
        payment = state["payment"] or {}
        await send_push_to_user(
            uid=state["uid"],
            title=f"Payment due: {payment.get('service_name', 'Utility')}",
            body=f"${payment.get('amount', '0')} due on {payment.get('due_date', '')}",
        )
        return True
    except Exception as exc:
        logger.error("Browser push failed: %s", exc)
        return False


async def _send_ui_popup(state: NotifyState) -> bool:
    from backend.notifications.websocket import broadcast_to_user
    try:
        payment = state["payment"] or {}
        await broadcast_to_user(state["uid"], {
            "type": "payment_reminder",
            "payment_id": state["payment_id"],
            "service_name": payment.get("service_name", ""),
            "amount": payment.get("amount", ""),
            "due_date": payment.get("due_date", ""),
        })
        return True
    except Exception as exc:
        logger.error("UI popup failed: %s", exc)
        return False


async def _send_macos(state: NotifyState) -> bool:
    from backend.notifications.macos_pub import publish_macos_notification
    try:
        payment = state["payment"] or {}
        await publish_macos_notification(
            uid=state["uid"],
            title=f"Payment Due: {payment.get('service_name', 'Utility')}",
            subtitle=f"Due {payment.get('due_date', '')}",
            body=f"Amount: {payment.get('currency', 'USD')} {payment.get('amount', '0')}",
        )
        return True
    except Exception as exc:
        logger.error("macOS notification failed: %s", exc)
        return False


# ---------------------------------------------------------------------------
# Build graph
# ---------------------------------------------------------------------------

def build_notify_subgraph():
    graph = StateGraph(NotifyState)
    graph.add_node("load_payment", load_payment)
    graph.add_node("dispatch", dispatch)
    graph.set_entry_point("load_payment")
    graph.add_edge("load_payment", "dispatch")
    graph.add_edge("dispatch", END)
    return graph.compile()


notify_subgraph = build_notify_subgraph()
