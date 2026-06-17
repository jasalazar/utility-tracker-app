"""
MCP Server: Utility Tracker (HTTP + per-caller auth via WorkOS AuthKit)
=======================================================================

The multi-user, network-facing sibling of `mcp_server_local.py`.

  - Same sibling-of-FastAPI design: imports backend.redis_client and reads
    the SAME Redis data. It never talks to FastAPI over HTTP.
  - redis_client.py and config.py are used UNCHANGED.
  - Identity is per-request: it comes from a WorkOS AuthKit access token that
    FastMCP validates (signature + expiry + audience) before any tool runs.
    There is no pinned LOCAL_UID here.

Deployment: runs as its own process / docker-compose service on :8787, behind
Cloudflare Tunnel (TLS terminated at the edge; internal hop is plain HTTP).

Required environment variables (provided via .env / docker-compose env_file):
  AUTHKIT_DOMAIN   e.g. https://your-project-xxxxx.authkit.app
  BASE_URL         e.g. https://mcp.utilitytracker.org
  (plus everything backend.config already needs)
"""

import json
import os
from pathlib import Path

# Anchor to project root so backend.config can find `.env` when this is run
# directly (outside a container). Inside the container, env vars are injected
# via env_file, so this is a harmless no-op there.
os.chdir(Path(__file__).resolve().parent.parent)

from fastmcp import FastMCP
from fastmcp.server.auth.providers.workos import AuthKitProvider
from fastmcp.server.dependencies import get_access_token
from fastmcp.exceptions import ToolError

import httpx

from backend.redis_client import redis_client

# ---------------------------------------------------------------------------
# Auth — WorkOS AuthKit is the Authorization Server ("front desk"); this server
# is only the Resource Server ("room door"). FastMCP uses this provider to
# validate every token and to auto-serve /.well-known/oauth-protected-resource.
# ---------------------------------------------------------------------------
auth_provider = AuthKitProvider(
    authkit_domain=os.environ["AUTHKIT_DOMAIN"],
    base_url=os.environ["BASE_URL"],
)

mcp = FastMCP(name="utility-tracker", auth=auth_provider)


# ---------------------------------------------------------------------------
# Identity seam — reads the validated token instead of a constant.
# The token is already verified by FastMCP before any tool runs, so here we
# only read claims; we never trust client-supplied input for identity.
# ---------------------------------------------------------------------------
# The MCP access token carries only the opaque `sub` (= WorkOS user id) and the
# `offline_access` scope — it is NOT an OIDC identity token, so the userinfo
# endpoint rejects it. We resolve the email server-side via the WorkOS
# Management API using a secret API key, then map it to a uid. Cached by `sub`.
_WORKOS_API_KEY = os.environ.get("WORKOS_API_KEY", "")
_email_by_sub: dict[str, str] = {}


async def _email_for_user(workos_user_id: str) -> str | None:
    """Look up a WorkOS user's email by id via the WorkOS Management API."""
    if not _WORKOS_API_KEY:
        raise ToolError("Server misconfigured: WORKOS_API_KEY is not set.")
    url = f"https://api.workos.com/user_management/users/{workos_user_id}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {_WORKOS_API_KEY}"})
    if resp.status_code != 200:
        return None
    return resp.json().get("email")


async def resolve_uid() -> str:
    token = get_access_token()
    if token is None:
        raise ToolError("No authenticated token on this request.")

    sub = (token.claims or {}).get("sub")        # WorkOS user id
    if not sub:
        raise ToolError("Token has no subject (sub) claim.")

    email = _email_by_sub.get(sub)               # cache hit
    if not email:
        email = await _email_for_user(sub)       # WorkOS Management API lookup
        if email:
            _email_by_sub[sub] = email

    if not email:
        raise ToolError("Could not resolve the caller's email from WorkOS.")

    uid = await redis_client().uid_from_email(email)
    if not uid:  # provisioning gap: authenticated, but never onboarded via the web app
        raise ToolError(
            f"No utility-tracker account found for {email}. "
            "Please sign in to the web app once to finish onboarding."
        )
    return uid


# ---- Tools (model-controlled actions) -------------------------------------

@mcp.tool
async def list_payments() -> list[dict]:
    """List ALL of the user's tracked utility bills, ordered by due date
    (soonest first). Returns each payment's service name, amount, currency,
    due date, and status (e.g. 'pending' or 'paid'). Use this to answer
    questions like 'what bills do I have?' or 'what's due this month?'.
    """
    return await redis_client().list_payments(await resolve_uid())


@mcp.tool
async def get_payment(payment_id: str) -> dict:
    """Fetch the full details of ONE utility bill by its payment id, including
    account number, confirmation number, and the source email subject. Use
    this after list_payments when the user asks about a specific bill. The
    payment_id is the 'payment_id' field returned by list_payments.
    """
    payment = await redis_client().get_payment(await resolve_uid(), payment_id)
    if not payment:
        return {"error": f"No payment found with id {payment_id}"}
    return payment


@mcp.tool
async def mark_paid(payment_id: str) -> dict:
    """Mark a utility bill as paid. This MUTATES the record: it sets the
    bill's status to 'paid'. Only call this when the user clearly states a
    specific bill has been paid. The payment_id is from list_payments.
    """
    await redis_client().update_payment_status(await resolve_uid(), payment_id, "paid")
    return {"payment_id": payment_id, "status": "paid"}


# ---- Resource (application/user-controlled, read-only) --------------------

@mcp.resource("payments://current")
async def current_payments_resource() -> str:
    """A read-only snapshot of the authenticated user's payment list as JSON."""
    payments = await redis_client().list_payments(await resolve_uid())
    return json.dumps(payments, indent=2)


# ---------------------------------------------------------------------------
# Entrypoint — HTTP transport. The MCP endpoint mounts at /mcp, so the
# Resource Indicator registered in WorkOS must be  {BASE_URL}/mcp.
# host 0.0.0.0 so cloudflared (a sibling container) can reach it.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8787)
