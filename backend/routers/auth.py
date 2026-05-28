"""
Auth routes:
  GET  /auth/login         — redirect to Google consent screen
  GET  /auth/callback      — handle OAuth callback, set session cookie
  POST /auth/logout        — revoke session cookie
  GET  /auth/me            — return current user profile
  POST /auth/rewatch       — (re-)register Gmail push watch for current user
  GET  /auth/watch-status  — check Gmail watch registration state
"""

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Response, Request
from fastapi.responses import RedirectResponse

from backend.auth.oauth import build_auth_url, exchange_code, register_gmail_watch
from backend.auth.middleware import create_session_token, get_current_uid, revoke_session, COOKIE_NAME
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

COOKIE_MAX_AGE = 60 * 60 * 24  # 24 hours


@router.get("/login")
async def login(request: Request) -> RedirectResponse:
    """Redirect the browser to Google's OAuth consent page."""
    auth_url, state, code_verifier = build_auth_url()
    response = RedirectResponse(url=auth_url)
    # Short-lived CSRF state cookie.
    response.set_cookie("oauth_state", state, max_age=600, httponly=True, samesite="lax")
    # If the library applied PKCE, carry the verifier in a matching cookie so
    # the callback can complete the token exchange.
    if code_verifier:
        response.set_cookie("code_verifier", code_verifier, max_age=600, httponly=True, samesite="lax")
    return response


@router.get("/callback")
async def callback(
    code: str,
    state: str,
    request: Request,
    response: Response,
) -> RedirectResponse:
    """Handle the OAuth callback, create a session, and redirect to the dashboard."""
    # CSRF check.
    stored_state = request.cookies.get("oauth_state", "")
    if stored_state != state:
        logger.warning("OAuth state mismatch — possible CSRF attempt")
        return RedirectResponse(url="/?error=state_mismatch")

    # Retrieve the PKCE verifier if one was stored at login time.
    code_verifier = request.cookies.get("code_verifier") or None

    user_info = await exchange_code(code, code_verifier=code_verifier)
    uid = user_info["uid"]

    # Register Gmail push notifications for this user.
    try:
        watch = await register_gmail_watch(uid)
        logger.info("Gmail watch registered during callback: uid=%s %s", uid, watch)
    except Exception as exc:
        # Log the full traceback so the failure is visible in the server console.
        logger.exception("Gmail watch registration failed for uid=%s — "
                         "visit POST /auth/rewatch to retry: %s", uid, exc)

    token = await create_session_token(uid)

    redirect = RedirectResponse(url="/dashboard")
    redirect.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=COOKIE_MAX_AGE,
        secure=False,   # Set to True in production behind HTTPS.
    )
    # Clear all temporary OAuth cookies.
    redirect.delete_cookie("oauth_state")
    redirect.delete_cookie("code_verifier")
    return redirect


@router.post("/logout")
async def logout(request: Request, response: Response) -> dict:
    """Revoke the session and clear the cookie."""
    token = request.cookies.get(COOKIE_NAME, "")
    if token:
        await revoke_session(token)
    response.delete_cookie(COOKIE_NAME)
    return {"status": "logged out"}


@router.get("/me")
async def me(uid: str = Depends(get_current_uid)) -> dict:
    """Return the authenticated user's profile."""
    rc = redis_client()
    profile = await rc.get_user_profile(uid)
    if not profile:
        return {"uid": uid}
    return {"uid": uid, **profile}


@router.get("/watch-status")
async def watch_status(uid: str = Depends(get_current_uid)) -> dict:
    """
    Return the current Gmail watch registration state for the logged-in user.
    Useful for diagnosing Pub/Sub delivery issues.
    """
    rc = redis_client()
    watch = await rc.get_gmail_watch(uid)
    if not watch:
        return {"registered": False, "uid": uid}

    expiry_ms = int(watch.get("watch_expiry", "0"))
    expiry_s = expiry_ms / 1000
    now_s = time.time()
    return {
        "registered": True,
        "uid": uid,
        "history_id": watch.get("history_id"),
        "watch_expiry_epoch_ms": expiry_ms,
        "expires_in_hours": round((expiry_s - now_s) / 3600, 1),
        "expired": expiry_s < now_s,
    }


@router.post("/rewatch")
async def rewatch(uid: str = Depends(get_current_uid)) -> dict:
    """
    (Re-)register the Gmail push notification watch for the current user.

    Call this if:
      - The watch was never registered (e.g. it failed silently at login)
      - The watch has expired (Google watches expire after ~7 days)
      - You changed your Pub/Sub topic and need to update the subscription

    Returns the new history_id and expiry on success, or a 502 with the
    Google API error message on failure.
    """
    try:
        watch = await register_gmail_watch(uid)
        return {
            "status": "ok",
            "uid": uid,
            "history_id": watch["history_id"],
            "watch_expiry_epoch_ms": int(watch["watch_expiry"]),
        }
    except Exception as exc:
        logger.exception("rewatch failed for uid=%s", uid)
        raise HTTPException(
            status_code=502,
            detail=f"Gmail watch registration failed: {exc}",
        )
