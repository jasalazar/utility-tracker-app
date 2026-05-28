"""
APScheduler setup and job management.

The scheduler uses a Redis job store (DB index 2) so jobs survive restarts.
Two categories of jobs:

  1. Payment notification jobs   — created dynamically by plan_notifications
                                   for each extracted utility email.
  2. Gmail watch renewal job     — daily, renews all users' Gmail watches
                                   before Google's 7-day expiry.
"""

import uuid
import logging
import asyncio
from datetime import datetime, timezone, timedelta

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor

from backend.config import settings
from backend.redis_client import redis_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Scheduler singleton
# ---------------------------------------------------------------------------

def _build_scheduler() -> AsyncIOScheduler:
    redis_url = settings.redis_url
    # Parse host/port from the URL for APScheduler's RedisJobStore.
    # Expected format: redis://host:port/db
    from urllib.parse import urlparse
    parsed = urlparse(redis_url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 6379

    jobstores = {
        "default": RedisJobStore(
            host=host,
            port=port,
            db=settings.redis_scheduler_db,
        )
    }
    executors = {"default": AsyncIOExecutor()}
    return AsyncIOScheduler(jobstores=jobstores, executors=executors)


scheduler: AsyncIOScheduler = _build_scheduler()


# ---------------------------------------------------------------------------
# Notification job target (called by APScheduler at fire time)
# ---------------------------------------------------------------------------

def _run_notification_job(uid: str, payment_id: str, job_id: str, channels: list[str]) -> None:
    """
    Synchronous wrapper required by APScheduler.
    Runs the async notify_subgraph in the event loop.
    """
    from backend.agents.notify_subgraph import notify_subgraph

    async def _inner():
        await notify_subgraph.ainvoke({
            "uid": uid,
            "payment_id": payment_id,
            "job_id": job_id,
            "channels": channels,
            "payment": None,
            "user_profile": None,
            "results": {},
        })

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_inner())
        else:
            loop.run_until_complete(_inner())
    except Exception as exc:
        logger.error("Notification job failed uid=%s pid=%s: %s", uid, payment_id, exc)


# ---------------------------------------------------------------------------
# Schedule notifications for a newly persisted payment
# ---------------------------------------------------------------------------

async def schedule_payment_notifications(
    uid: str,
    payment_id: str,
    due_date_str: str,
) -> None:
    """
    Read the user's notification rules and create an APScheduler job for
    each rule whose computed fire_at is still in the future.
    """
    if not due_date_str:
        logger.warning("schedule_payment_notifications: no due date for pid=%s", payment_id)
        return

    rc = redis_client()
    rules = await rc.get_rules(uid)
    profile = await rc.get_user_profile(uid)
    tz_name = (profile or {}).get("timezone", settings.default_timezone)

    try:
        user_tz = pytz.timezone(tz_name)
    except Exception:
        user_tz = pytz.utc

    try:
        due_date = datetime.strptime(due_date_str, "%Y-%m-%d")
    except ValueError:
        logger.error("schedule_payment_notifications: bad due_date '%s'", due_date_str)
        return

    now_utc = datetime.now(timezone.utc)

    for rule in rules:
        days_before = int(rule.get("days_before", 0))
        hour = int(rule.get("hour", 9))
        minute = int(rule.get("minute", 0))
        channels = rule.get("channels", ["email"])

        # Compute fire time in user's local timezone, then convert to UTC.
        fire_local = user_tz.localize(
            due_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            - timedelta(days=days_before)
        )
        fire_utc = fire_local.astimezone(timezone.utc)

        if fire_utc <= now_utc:
            logger.debug("Skipping past fire_at=%s for pid=%s", fire_utc, payment_id)
            continue

        job_id = str(uuid.uuid4())

        scheduler.add_job(
            _run_notification_job,
            trigger="date",
            run_date=fire_utc,
            id=job_id,
            kwargs={
                "uid": uid,
                "payment_id": payment_id,
                "job_id": job_id,
                "channels": channels,
            },
            replace_existing=False,
        )

        await rc.save_notify_job(uid, job_id, {
            "payment_id": payment_id,
            "fire_at": fire_utc.isoformat(),
            "channels": ",".join(channels),
            "sent": "false",
        })

        logger.info(
            "Notification job scheduled: uid=%s pid=%s fire_at=%s channels=%s",
            uid, payment_id, fire_utc.isoformat(), channels,
        )


# ---------------------------------------------------------------------------
# Gmail watch renewal (daily cron)
# ---------------------------------------------------------------------------

async def _renew_all_gmail_watches() -> None:
    """Renew Gmail push watches for all enrolled users."""
    from backend.auth.oauth import register_gmail_watch

    rc = redis_client()
    uids = await rc.all_gmail_watch_uids()
    logger.info("Renewing Gmail watches for %d user(s)", len(uids))
    for uid in uids:
        try:
            await register_gmail_watch(uid)
        except Exception as exc:
            logger.error("Gmail watch renewal failed for uid=%s: %s", uid, exc)


def _renew_gmail_watches_sync() -> None:
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_renew_all_gmail_watches())
        else:
            loop.run_until_complete(_renew_all_gmail_watches())
    except Exception as exc:
        logger.error("_renew_gmail_watches_sync failed: %s", exc)


# ---------------------------------------------------------------------------
# Startup / shutdown hooks (called from FastAPI lifespan)
# ---------------------------------------------------------------------------

def start_scheduler() -> None:
    scheduler.add_job(
        _renew_gmail_watches_sync,
        trigger="interval",
        hours=24,
        id="gmail_watch_renewal",
        replace_existing=True,
    )
    scheduler.start()
    logger.info("APScheduler started")


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
    logger.info("APScheduler stopped")
