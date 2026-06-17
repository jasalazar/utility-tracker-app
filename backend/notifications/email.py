"""
Email notification channel — sends payment reminders via the Gmail API
using the authenticated user's own account as the sender.

INACTIVE: not currently used. The app dropped the gmail.send scope to stay
least-intrusive, so this channel is unwired from the notify subgraph. Kept for
a future re-implementation via a system mailer (e.g. no-reply@utilitytracker.org).
See the project backlog.
"""

import base64
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from googleapiclient.discovery import build

from backend.auth.oauth import get_valid_credentials

logger = logging.getLogger(__name__)


def _build_html(user_name: str, payment: dict) -> str:
    service = payment.get("service_name", "Utility")
    amount = payment.get("amount", "0")
    currency = payment.get("currency", "USD")
    due_date = payment.get("due_date", "N/A")
    account = payment.get("account_number", "")
    account_line = f"<p><strong>Account:</strong> {account}</p>" if account else ""

    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:500px;margin:auto;padding:24px">
      <h2 style="color:#1a56db">Utility Payment Reminder</h2>
      <p>Hi {user_name},</p>
      <p>This is a reminder that the following payment is coming up:</p>
      <table style="border-collapse:collapse;width:100%">
        <tr><td style="padding:8px;border:1px solid #e5e7eb"><strong>Service</strong></td>
            <td style="padding:8px;border:1px solid #e5e7eb">{service}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e5e7eb"><strong>Amount Due</strong></td>
            <td style="padding:8px;border:1px solid #e5e7eb">{currency} {amount}</td></tr>
        <tr><td style="padding:8px;border:1px solid #e5e7eb"><strong>Due Date</strong></td>
            <td style="padding:8px;border:1px solid #e5e7eb">{due_date}</td></tr>
      </table>
      {account_line}
      <p style="margin-top:24px;color:#6b7280;font-size:12px">
        Sent by Utility Tracker &mdash; manage your reminders at your dashboard.
      </p>
    </body></html>
    """


async def send_payment_reminder(to_email: str, user_name: str, payment: dict) -> None:
    """Send an HTML payment reminder email using the user's own Gmail account."""
    if not to_email:
        logger.warning("send_payment_reminder: no recipient email")
        return

    uid = payment.get("uid") or await _uid_from_email(to_email)
    if not uid:
        logger.warning("send_payment_reminder: cannot resolve uid for %s", to_email)
        return

    creds = await get_valid_credentials(uid)
    if not creds:
        logger.warning("send_payment_reminder: no credentials for uid=%s", uid)
        return

    service_name = payment.get("service_name", "Utility")
    due_date = payment.get("due_date", "")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Payment Reminder: {service_name} due {due_date}"
    msg["From"] = to_email
    msg["To"] = to_email

    html_body = _build_html(user_name, payment)
    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")

    service = build("gmail", "v1", credentials=creds)
    service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()

    logger.info("Reminder email sent to %s for %s due %s", to_email, service_name, due_date)


async def _uid_from_email(email: str) -> str | None:
    from backend.redis_client import redis_client
    rc = redis_client()
    return await rc.uid_from_email(email)
