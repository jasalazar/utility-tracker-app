"""
Admin analytics routes — all protected by require_admin.

Endpoints:
  GET /api/admin/summary   — platform-wide headline numbers
  GET /api/admin/services  — per-service breakdown sorted by total amount
  GET /api/admin/timeline  — monthly payment totals for the last 12 months
  GET /api/admin/users     — all users with their individual payment stats

All aggregations are computed on the fly from Redis. No secondary store.
At scale, move to DuckDB or a dedicated analytics DB; the endpoint contracts
(response shapes) would remain identical.
"""

import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends

from backend.auth.middleware import require_admin
from backend.redis_client import get_redis

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Internal helpers — scan Redis for cross-user data
# ---------------------------------------------------------------------------

async def _all_payments() -> list[dict]:
    """
    Return every payment record across all users.
    Key pattern: utility:{uid}:{payment_id}
    Each returned dict is enriched with uid and payment_id fields.
    """
    r = get_redis()
    payments: list[dict] = []
    async for key in r.scan_iter("utility:*:*"):
        parts = key.split(":", 2)
        if len(parts) != 3:
            continue
        record = await r.hgetall(key)
        if record:
            record.setdefault("uid", parts[1])
            record.setdefault("payment_id", parts[2])
            payments.append(record)
    return payments


async def _all_user_profiles() -> list[dict]:
    """
    Return every user profile.
    Key pattern: user:{uid}:profile
    Each returned dict is enriched with a uid field.
    """
    r = get_redis()
    profiles: list[dict] = []
    async for key in r.scan_iter("user:*:profile"):
        parts = key.split(":", 2)
        if len(parts) != 3:
            continue
        record = await r.hgetall(key)
        if record:
            record.setdefault("uid", parts[1])
            profiles.append(record)
    return profiles


def _is_overdue(payment: dict, now: datetime) -> bool:
    due = payment.get("due_date", "")
    if not due:
        return False
    try:
        due_dt = datetime.strptime(due, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        return payment.get("status") == "pending" and due_dt < now
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# GET /api/admin/summary
# ---------------------------------------------------------------------------

@router.get("/summary")
async def summary(_uid: str = Depends(require_admin)) -> dict:
    """Platform-wide headline numbers."""
    now = datetime.now(timezone.utc)
    payments = await _all_payments()
    profiles = await _all_user_profiles()

    pending = [p for p in payments if p.get("status") == "pending"]
    paid    = [p for p in payments if p.get("status") == "paid"]
    overdue = [p for p in pending if _is_overdue(p, now)]

    def _sum(records: list[dict]) -> float:
        return round(sum(float(r.get("amount", 0)) for r in records), 2)

    return {
        "total_users":          len(profiles),
        "total_payments":       len(payments),
        "pending_count":        len(pending),
        "paid_count":           len(paid),
        "overdue_count":        len(overdue),
        "total_pending_amount": _sum(pending),
        "total_paid_amount":    _sum(paid),
        "total_overdue_amount": _sum(overdue),
    }


# ---------------------------------------------------------------------------
# GET /api/admin/services
# ---------------------------------------------------------------------------

@router.get("/services")
async def services(_uid: str = Depends(require_admin)) -> list[dict]:
    """Per-service breakdown across all users, sorted by total amount descending."""
    payments = await _all_payments()

    bucket: dict[str, dict] = defaultdict(lambda: {"count": 0, "total": 0.0, "paid": 0, "pending": 0, "overdue": 0})
    now = datetime.now(timezone.utc)

    for p in payments:
        name = p.get("service_name") or "Unknown"
        amount = float(p.get("amount", 0))
        status = p.get("status", "pending")

        bucket[name]["count"]  += 1
        bucket[name]["total"]  += amount
        bucket[name][status if status in ("paid", "pending") else "pending"] += 1
        if _is_overdue(p, now):
            bucket[name]["overdue"] += 1

    result = []
    for name, data in sorted(bucket.items(), key=lambda x: -x[1]["total"]):
        count = data["count"]
        result.append({
            "service_name":  name,
            "count":         count,
            "total_amount":  round(data["total"], 2),
            "avg_amount":    round(data["total"] / count, 2) if count else 0.0,
            "paid_count":    data["paid"],
            "pending_count": data["pending"],
            "overdue_count": data["overdue"],
        })

    return result


# ---------------------------------------------------------------------------
# GET /api/admin/timeline
# ---------------------------------------------------------------------------

@router.get("/timeline")
async def timeline(_uid: str = Depends(require_admin)) -> list[dict]:
    """
    Monthly payment totals for the last 13 months (current month + 12 prior),
    sorted chronologically. Months with no payments are included as zero rows
    so the chart always renders a full 13-month window.
    """
    payments = await _all_payments()

    monthly: dict[str, dict] = defaultdict(
        lambda: {"count": 0, "total": 0.0, "paid_count": 0, "pending_count": 0}
    )

    for p in payments:
        due = p.get("due_date", "")
        if not due or len(due) < 7:
            continue
        month = due[:7]  # YYYY-MM
        amount = float(p.get("amount", 0))
        monthly[month]["count"]  += 1
        monthly[month]["total"]  += amount
        if p.get("status") == "paid":
            monthly[month]["paid_count"]    += 1
        else:
            monthly[month]["pending_count"] += 1

    # Build the full 13-month window so the chart is always complete.
    now = datetime.now(timezone.utc)
    window: list[dict] = []
    for offset in range(12, -1, -1):
        # Step back month by month.
        target = (now.replace(day=1) - timedelta(days=1) * 0) if offset == 0 \
                 else (now.replace(day=1) - timedelta(days=offset * 28))
        # Normalise to the first of the target month.
        key = target.strftime("%Y-%m")
        data = monthly.get(key, {})
        window.append({
            "month":         key,
            "count":         data.get("count", 0),
            "total_amount":  round(data.get("total", 0.0), 2),
            "paid_count":    data.get("paid_count", 0),
            "pending_count": data.get("pending_count", 0),
        })

    return sorted(window, key=lambda r: r["month"])


# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------

@router.get("/users")
async def users(_uid: str = Depends(require_admin)) -> list[dict]:
    """All registered users with per-user payment statistics."""
    now = datetime.now(timezone.utc)
    payments = await _all_payments()
    profiles = await _all_user_profiles()

    # Group payments by uid for O(n) lookup.
    by_uid: dict[str, list[dict]] = defaultdict(list)
    for p in payments:
        by_uid[p["uid"]].append(p)

    result = []
    for profile in sorted(profiles, key=lambda p: p.get("created_at", "0"), reverse=True):
        uid = profile["uid"]
        user_payments = by_uid[uid]

        pending_amount = sum(
            float(p.get("amount", 0))
            for p in user_payments
            if p.get("status") == "pending"
        )
        overdue_count = sum(1 for p in user_payments if _is_overdue(p, now))

        result.append({
            "uid":            uid,
            "name":           profile.get("name", ""),
            "email":          profile.get("email", ""),
            "role":           profile.get("role", "user"),
            "timezone":       profile.get("timezone", ""),
            "created_at":     profile.get("created_at", ""),
            "payment_count":  len(user_payments),
            "pending_amount": round(pending_amount, 2),
            "overdue_count":  overdue_count,
        })

    return result
