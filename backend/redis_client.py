"""
Redis connection pool and typed helper methods.

Key schema (all keys namespaced by uid for multi-tenant isolation):
  user:{uid}:profile          HASH  — name, email, timezone, created_at
  user:{uid}:tokens           HASH  — access_token, refresh_token, token_expiry
  user:{uid}:rules            STRING (JSON) — list of notification rule objects
  gmail:watch:{uid}           HASH  — history_id, watch_expiry
  utility:{uid}:{pid}         HASH  — service, amount, currency, due_date,
                                       status, email_subject, email_id, created_at
  due:{uid}                   ZSET  — member=pid, score=due_date epoch (UTC)
  notify:job:{uid}:{job_id}   HASH  — payment_id, fire_at, channels, sent
  push:subs:{uid}             SET   — serialised PushSubscription JSON blobs
  email_uid_map               HASH  — gmail_address → uid  (routing webhook calls)
  sessions:{sid}              HASH  — uid, issued_at, expiry
"""

import json
from typing import Any, Optional
from redis.asyncio import Redis, ConnectionPool
from backend.config import settings

# ---------------------------------------------------------------------------
# Connection pool (shared across the process)
# ---------------------------------------------------------------------------
_pool: Optional[ConnectionPool] = None


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool.from_url(settings.redis_url, decode_responses=True)
    return _pool


def get_redis() -> Redis:
    """Return a Redis client backed by the shared connection pool."""
    return Redis(connection_pool=get_pool())


# ---------------------------------------------------------------------------
# Typed helpers
# ---------------------------------------------------------------------------

class RedisClient:
    """Thin wrapper around Redis with domain-specific methods."""

    def __init__(self) -> None:
        self.r = get_redis()

    # ---- User profile -------------------------------------------------------

    async def save_user_profile(self, uid: str, data: dict) -> None:
        await self.r.hset(f"user:{uid}:profile", mapping=data)

    async def get_user_profile(self, uid: str) -> Optional[dict]:
        result = await self.r.hgetall(f"user:{uid}:profile")
        return result or None

    async def save_user_tokens(self, uid: str, tokens: dict) -> None:
        await self.r.hset(f"user:{uid}:tokens", mapping=tokens)

    async def get_user_tokens(self, uid: str) -> Optional[dict]:
        result = await self.r.hgetall(f"user:{uid}:tokens")
        return result or None

    # ---- Email → UID routing ------------------------------------------------

    async def map_email_to_uid(self, email: str, uid: str) -> None:
        await self.r.hset("email_uid_map", email, uid)

    async def uid_from_email(self, email: str) -> Optional[str]:
        return await self.r.hget("email_uid_map", email)

    # ---- Gmail watch state --------------------------------------------------

    async def save_gmail_watch(self, uid: str, data: dict) -> None:
        await self.r.hset(f"gmail:watch:{uid}", mapping=data)

    async def get_gmail_watch(self, uid: str) -> Optional[dict]:
        result = await self.r.hgetall(f"gmail:watch:{uid}")
        return result or None

    async def all_gmail_watch_uids(self) -> list[str]:
        """Return all UIDs that have a registered Gmail watch."""
        keys = await self.r.keys("gmail:watch:*")
        return [k.split(":", 2)[2] for k in keys]

    # ---- Payment records ----------------------------------------------------

    async def save_payment(self, uid: str, payment_id: str, data: dict) -> None:
        await self.r.hset(f"utility:{uid}:{payment_id}", mapping=data)
        # Keep the sorted-set index in sync.
        due_epoch = float(data.get("due_epoch", 0))
        await self.r.zadd(f"due:{uid}", {payment_id: due_epoch})

    async def get_payment(self, uid: str, payment_id: str) -> Optional[dict]:
        result = await self.r.hgetall(f"utility:{uid}:{payment_id}")
        return result or None

    async def list_payments(self, uid: str) -> list[dict]:
        """Return all payments for a user sorted by due date ascending."""
        pids = await self.r.zrange(f"due:{uid}", 0, -1)
        if not pids:
            return []
        pipe = self.r.pipeline()
        for pid in pids:
            pipe.hgetall(f"utility:{uid}:{pid}")
        results = await pipe.execute()
        return [r for r in results if r]

    async def update_payment_status(self, uid: str, payment_id: str, status: str) -> None:
        await self.r.hset(f"utility:{uid}:{payment_id}", "status", status)

    async def payment_exists_for_email(self, uid: str, email_id: str) -> bool:
        """Guard against processing the same Gmail message twice."""
        keys = await self.r.keys(f"utility:{uid}:*")
        for key in keys:
            val = await self.r.hget(key, "email_id")
            if val == email_id:
                return True
        return False

    # ---- Notification rules -------------------------------------------------

    async def save_rules(self, uid: str, rules: list[dict]) -> None:
        await self.r.set(f"user:{uid}:rules", json.dumps(rules))

    async def get_rules(self, uid: str) -> list[dict]:
        raw = await self.r.get(f"user:{uid}:rules")
        return json.loads(raw) if raw else []

    # ---- Notification job audit trail ---------------------------------------

    async def save_notify_job(self, uid: str, job_id: str, data: dict) -> None:
        await self.r.hset(f"notify:job:{uid}:{job_id}", mapping=data)

    async def mark_notify_job_sent(self, uid: str, job_id: str) -> None:
        await self.r.hset(f"notify:job:{uid}:{job_id}", "sent", "true")

    # ---- Web Push subscriptions ---------------------------------------------

    async def add_push_subscription(self, uid: str, subscription: dict) -> None:
        await self.r.sadd(f"push:subs:{uid}", json.dumps(subscription))

    async def get_push_subscriptions(self, uid: str) -> list[dict]:
        raw = await self.r.smembers(f"push:subs:{uid}")
        return [json.loads(s) for s in raw]

    async def remove_push_subscription(self, uid: str, subscription: dict) -> None:
        await self.r.srem(f"push:subs:{uid}", json.dumps(subscription))

    # ---- Session store (JWT backing) ----------------------------------------

    async def save_session(self, sid: str, uid: str, expiry: int) -> None:
        await self.r.hset(f"sessions:{sid}", mapping={"uid": uid, "expiry": expiry})
        await self.r.expireat(f"sessions:{sid}", expiry)

    async def get_session(self, sid: str) -> Optional[dict]:
        result = await self.r.hgetall(f"sessions:{sid}")
        return result or None

    async def delete_session(self, sid: str) -> None:
        await self.r.delete(f"sessions:{sid}")


# Module-level singleton convenience accessor.
def redis_client() -> RedisClient:
    return RedisClient()
