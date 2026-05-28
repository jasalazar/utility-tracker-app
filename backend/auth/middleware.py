"""
JWT-based session middleware.

Tokens are stored in an HttpOnly cookie (not localStorage) to prevent XSS
access. Each token contains a session ID (sid); the actual uid is looked up
from Redis so tokens can be revoked by deleting the session key.
"""

import time
import uuid
import logging
from typing import Optional

from fastapi import Cookie, HTTPException, status, Depends
from jose import JWTError, jwt

from backend.config import settings
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)

COOKIE_NAME = "ut_session"


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------

async def create_session_token(uid: str) -> str:
    """
    Create a signed JWT session token and persist the session in Redis.
    Returns the encoded JWT string (to be set as an HttpOnly cookie).
    """
    sid = str(uuid.uuid4())
    expiry = int(time.time()) + settings.jwt_expiry_hours * 3600

    payload = {
        "sid": sid,
        "exp": expiry,
        "iat": int(time.time()),
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    rc = redis_client()
    await rc.save_session(sid, uid, expiry)
    return token


# ---------------------------------------------------------------------------
# Token verification (FastAPI dependency)
# ---------------------------------------------------------------------------

async def get_current_uid(
    ut_session: Optional[str] = Cookie(default=None),
) -> str:
    """
    FastAPI dependency — validates the session cookie and returns the uid.
    Raise 401 if the cookie is missing, expired, or the session is not in Redis.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not ut_session:
        raise credentials_exception

    try:
        payload = jwt.decode(
            ut_session,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        sid: str = payload.get("sid")
        if not sid:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    rc = redis_client()
    session = await rc.get_session(sid)
    if not session:
        # Session was revoked or expired.
        raise credentials_exception

    return session["uid"]


# ---------------------------------------------------------------------------
# Admin guard (FastAPI dependency)
# ---------------------------------------------------------------------------

async def require_admin(uid: str = Depends(get_current_uid)) -> str:
    """
    FastAPI dependency — extends get_current_uid with an admin role check.
    Raises 403 if the authenticated user does not have role='admin'.
    Use as: uid: str = Depends(require_admin)
    """
    rc = redis_client()
    profile = await rc.get_user_profile(uid)
    if not profile or profile.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return uid


# ---------------------------------------------------------------------------
# Logout helper
# ---------------------------------------------------------------------------

async def revoke_session(token: str) -> None:
    """Invalidate a session by deleting it from Redis."""
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            options={"verify_exp": False},
        )
        sid = payload.get("sid")
        if sid:
            rc = redis_client()
            await rc.delete_session(sid)
    except JWTError:
        pass  # Already invalid — nothing to revoke.
