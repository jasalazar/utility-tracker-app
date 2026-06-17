"""
Google OAuth 2.0 helpers.

Flow:
  1. build_auth_url()   → redirect user to Google consent screen
  2. exchange_code()    → trade the auth code for access + refresh tokens
  3. refresh_tokens()   → silently renew an expired access token
  4. register_gmail_watch() → subscribe to Gmail push notifications via Pub/Sub
"""

import json
import uuid
import time
import logging
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

from backend.config import settings
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)

# Gmail scopes required by the app.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/gmail.readonly",
]

# ---------------------------------------------------------------------------
# OAuth flow helpers
# ---------------------------------------------------------------------------

def _make_flow() -> Flow:
    client_config = {
        "web": {
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_redirect_uri],
        }
    }
    flow = Flow.from_client_config(client_config, scopes=SCOPES)
    flow.redirect_uri = settings.google_redirect_uri
    return flow


def _extract_code_verifier(flow: Flow) -> Optional[str]:
    """
    Newer versions of google-auth-oauthlib automatically apply PKCE when
    building the authorization URL.  The code_verifier is stored inside the
    flow/session object but its exact location varies by library version.
    Try every known location and return the first non-empty value found.
    """
    candidates = [
        lambda f: f.code_verifier,                               # future attribute
        lambda f: f.oauth2session.code_verifier,                 # requests-oauthlib session
        lambda f: f.oauth2session._client.code_verifier,         # oauthlib client
        lambda f: f.oauth2session._client._code_verifier,        # private variant
    ]
    for getter in candidates:
        try:
            value = getter(flow)
            if value:
                return str(value)
        except AttributeError:
            continue
    return None


def build_auth_url() -> tuple[str, str, Optional[str]]:
    """
    Return (authorization_url, state, code_verifier).
    code_verifier is non-None when the library applied PKCE automatically.
    The caller must persist it (e.g. in a short-lived cookie) and pass it
    back to exchange_code() so the token exchange succeeds.
    """
    flow = _make_flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",   # Force refresh_token on every login.
    )
    code_verifier = _extract_code_verifier(flow)
    return auth_url, state, code_verifier


async def exchange_code(code: str, code_verifier: Optional[str] = None) -> dict:
    """
    Exchange an OAuth authorisation code for credentials.
    code_verifier must be supplied when PKCE was used in build_auth_url().
    Returns a dict with uid, email, name, and the raw tokens.
    """
    flow = _make_flow()
    fetch_kwargs: dict = {"code": code}
    if code_verifier:
        fetch_kwargs["code_verifier"] = code_verifier
    flow.fetch_token(**fetch_kwargs)
    creds = flow.credentials

    # Fetch user info from Google.
    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()

    email: str = user_info["email"]
    name: str = user_info.get("name", email)

    rc = redis_client()

    # Re-use existing uid if the user has logged in before.
    uid = await rc.uid_from_email(email)
    is_new_user = not uid
    if is_new_user:
        uid = str(uuid.uuid4())

    # Assign role — re-evaluated on every login so changes to ADMIN_EMAILS
    # take effect the next time the user signs in.
    role = "admin" if email.lower() in settings.admin_email_list else "user"

    # Build the profile update. created_at is only stamped on first login so
    # subsequent logins don't overwrite the original registration timestamp.
    profile_update: dict = {
        "name": name,
        "email": email,
        "timezone": settings.default_timezone,
        "role": role,
    }
    if is_new_user:
        profile_update["created_at"] = str(int(time.time()))

    await rc.save_user_profile(uid, profile_update)
    await rc.save_user_tokens(uid, {
        "access_token": creds.token,
        "refresh_token": creds.refresh_token or "",
        "token_expiry": str(int(creds.expiry.timestamp())) if creds.expiry else "0",
        "scopes": json.dumps(list(creds.scopes or [])),
    })
    await rc.map_email_to_uid(email, uid)

    return {"uid": uid, "email": email, "name": name}


# ---------------------------------------------------------------------------
# Token refresh
# ---------------------------------------------------------------------------

async def get_valid_credentials(uid: str) -> Optional[Credentials]:
    """
    Return a valid Credentials object for uid, refreshing silently if needed.
    Returns None if no tokens are stored.
    """
    rc = redis_client()
    tokens = await rc.get_user_tokens(uid)
    if not tokens:
        return None

    creds = Credentials(
        token=tokens.get("access_token"),
        refresh_token=tokens.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        scopes=json.loads(tokens.get("scopes", "[]")),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        # Persist the new access token.
        await rc.save_user_tokens(uid, {
            "access_token": creds.token,
            "refresh_token": creds.refresh_token or tokens.get("refresh_token", ""),
            "token_expiry": str(int(creds.expiry.timestamp())) if creds.expiry else "0",
            "scopes": json.dumps(list(creds.scopes or [])),
        })

    return creds


# ---------------------------------------------------------------------------
# Gmail Push Notification registration
# ---------------------------------------------------------------------------

async def register_gmail_watch(uid: str) -> dict:
    """
    Register (or renew) a Gmail push notification watch for uid.
    Google will send new-mail events to our Pub/Sub topic.
    Watch expiry is ~7 days; the scheduler renews it daily.

    Returns a dict with history_id and watch_expiry on success.
    Raises RuntimeError if credentials are missing.
    Lets Google API exceptions propagate so callers can surface them.
    """
    creds = await get_valid_credentials(uid)
    if not creds:
        raise RuntimeError(f"No OAuth credentials found for uid={uid}")

    service = build("gmail", "v1", credentials=creds)
    # This will raise googleapiclient.errors.HttpError on API-level failures
    # (e.g. topic does not exist, insufficient permissions).
    response = service.users().watch(
        userId="me",
        body={
            "topicName": settings.google_pubsub_topic,
            "labelIds": ["INBOX"],
        },
    ).execute()

    watch_data = {
        "history_id": str(response["historyId"]),
        "watch_expiry": str(response["expiration"]),  # ms epoch
    }
    rc = redis_client()
    await rc.save_gmail_watch(uid, watch_data)
    logger.info(
        "Gmail watch registered: uid=%s history_id=%s expires=%s",
        uid, response["historyId"], response["expiration"],
    )
    return watch_data


async def stop_gmail_watch(uid: str) -> None:
    """Unregister the Gmail push watch for uid (e.g. on account deletion)."""
    creds = await get_valid_credentials(uid)
    if not creds:
        return
    service = build("gmail", "v1", credentials=creds)
    service.users().stop(userId="me").execute()
