"""Deliver outbox events and run the daily clean-up (ARCHITECTURE §9–10, D-010).

How it works:
  1. Claim up to 50 due `pending` rows with FOR UPDATE SKIP LOCKED: two workers (or the sweep
     and a request's drain_soon) never take the same row.
  2. Run each row's handlers inside a savepoint. Success → `delivered`.
  3. Failure → attempts + 1 and retry after 1 min, 5 min, 30 min, 2 h, 6 h, 24 h; after the
     7th failure the row is `dead` and an error is logged (Sentry picks it up). A
     `PermanentDeliveryError` (handlers.py) makes the row `dead` at once, with the same alert.

PERF: free hosting calls the drain every 15 minutes from Cloud Scheduler (D-007) so the
database can sleep in between; `drain_soon` covers time-critical events right after a request.
Each scheduled run (and each worker loop) first runs the schedule tick (content/schedule.py,
ARCHITECTURE §10: scheduled page publish/unpublish, offer start/end).
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

from fastapi import BackgroundTasks, Request
from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from empire_api.ai import handlers as ai_handlers
from empire_api.content.schedule import schedule_tick
from empire_api.db import get_engine, get_sessionmaker, rows_affected
from empire_api.integrations import handlers as integration_handlers
from empire_api.integrations.conversions import handlers as conversion_handlers
from empire_api.integrations.handlers import PermanentDeliveryError, handlers_for
from empire_api.leads.erasure import anonymise_inactive
from empire_api.logs import get_logger
from empire_api.mail import handlers as mail_handlers
from empire_api.media import handlers as media_handlers
from empire_api.media.uploads import discard_stale_intents
from empire_api.platform.models import OutboxEvent, RateLimitBucket
from empire_api.site_settings.models import Setting
from empire_api.timeutil import utcnow
from empire_api.users.models import PasswordResetToken, SignInChallenge, UserSession

# DO NOT CHANGE without updating ARCHITECTURE §9: the schedule is documented and relied on by
# the "dead events" alert wording.
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=30),
    timedelta(hours=2),
    timedelta(hours=6),
    timedelta(hours=24),
)
BATCH_SIZE = 50
# A fixed key for pg_try_advisory_lock so only one drain endpoint run happens at a time.
DRAIN_LOCK_KEY = 7_100_312_001
CLEANUP_EVERY = timedelta(hours=24)
_CLEANUP_SETTING = "system.cleanup"

log = get_logger(__name__)
# Modules whose outbox handlers register on import (handlers.on); listed so they always load.
HANDLER_MODULES = (
    media_handlers,
    mail_handlers,
    integration_handlers,
    conversion_handlers,
    ai_handlers,
)


@dataclass(frozen=True)
class DrainResult:
    processed: int
    failed: int
    remaining: int


def _schedule_retry(row: OutboxEvent, exc: BaseException, now: datetime) -> None:
    row.attempts += 1
    row.last_error = f"{type(exc).__name__}: {exc}"[:2000]
    if isinstance(exc, PermanentDeliveryError):
        row.status = "dead"
        log.error(
            "outbox_event_dead",
            event_type=row.type,
            event_id=str(row.event_id),
            reason="permanent",
            error_type=type(exc).__name__,
        )
    elif row.attempts > len(RETRY_DELAYS):
        row.status = "dead"
        log.error("outbox_event_dead", event_type=row.type, event_id=str(row.event_id))
        # TODO(phase-6): email the owner a daily digest of dead events (ARCHITECTURE §9).
    else:
        row.available_at = now + RETRY_DELAYS[row.attempts - 1]


# Events only the scheduled sweep delivers, never `drain_soon` after a request: re-indexing for
# the AI assistant (D-059) can queue one event per page, and each may call the provider. Taken
# soon, they queued ahead of revalidation and invite emails and delayed them past 10 s.
SWEEP_ONLY: Final = frozenset({"ai.reindex"})


def drain(
    *, limit: int = BATCH_SIZE, now: datetime | None = None, skip: frozenset[str] = frozenset()
) -> DrainResult:
    """Deliver due events once. Safe to run from several processes at the same time."""
    now = now or utcnow()
    processed = failed = 0
    with get_sessionmaker()() as db, db.begin():
        due = select(OutboxEvent).where(
            OutboxEvent.status == "pending", OutboxEvent.available_at <= now
        )
        if skip:
            due = due.where(OutboxEvent.type.not_in(skip))
        rows = db.scalars(
            due.order_by(OutboxEvent.id).limit(limit).with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            try:
                with db.begin_nested():
                    for handler in handlers_for(row.type):
                        handler(db, row)
            except Exception as exc:  # noqa: BLE001 — any handler failure must be retried
                failed += 1
                _schedule_retry(row, exc, now)
            else:
                processed += 1
                row.attempts += 1
                row.status = "delivered"
                row.delivered_at = utcnow()
                row.last_error = None
    with get_sessionmaker()() as db:
        remaining = int(
            db.scalar(
                select(func.count()).select_from(OutboxEvent).where(OutboxEvent.status == "pending")
            )
            or 0
        )
    return DrainResult(processed=processed, failed=failed, remaining=remaining)


def drain_with_lock() -> DrainResult | None:
    """Drain while holding the advisory lock. None = another run holds it (caller → 429)."""
    with get_engine().connect() as conn:
        got = conn.execute(text("SELECT pg_try_advisory_lock(:k)"), {"k": DRAIN_LOCK_KEY})
        if not got.scalar_one():
            return None
        try:
            run_tick_safely()
            result = drain()
            maybe_cleanup()
            return result
        finally:
            conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": DRAIN_LOCK_KEY})
            conn.commit()


def run_tick_safely() -> None:
    """The schedule tick (content/schedule.py) before a drain, so the events it writes go out
    in the same run. WHY never raise: a broken tick must not stop event delivery; it is logged
    (Sentry) and the next run tries again."""
    try:
        schedule_tick()
    except Exception:
        log.exception("schedule_tick_failed")


def _drain_quietly(budget_seconds: float) -> None:
    started = time.monotonic()
    try:
        while time.monotonic() - started < budget_seconds:
            # WHY one event per transaction: a batch keeps every row it took locked until the
            # last handler returns. With CMS writes, lead alerts and ad sends all delivered soon
            # (D-054, D-057), one slow call (a revalidation, an ad API) held an invite email
            # back for over 15 s under load. One at a time, each event goes out as soon as its
            # own handlers finish. The 15-minute sweep still takes full batches.
            result = drain(limit=1, skip=SWEEP_ONLY)
            if result.processed + result.failed == 0:
                break
    except Exception:  # WHY: never fail a request because delivery failed; the sweep retries
        log.exception("drain_soon_failed")


def drain_soon(background: BackgroundTasks, budget_seconds: float = 3.0) -> None:
    """Deliver new events right after the response is sent (lead alerts within seconds).

    The 15-minute sweep retries anything this misses (ARCHITECTURE §10).
    """
    background.add_task(_drain_quietly, budget_seconds)


def deliver_writes_soon(request: Request, background: BackgroundTasks) -> None:
    """Router dependency: after any change in the CMS, deliver its events at once (`drain_soon`).

    WHY: without it, a published project or an edited page reached the website only on the
    15-minute sweep, which staff read as "Publish didn't work" (L7a). Reads deliver nothing.
    """
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        drain_soon(background)


def cleanup(now: datetime | None = None) -> dict[str, int]:
    """Delete expired sessions, used/expired reset tokens, old rate-limit buckets and sign-in
    challenges (two-factor second steps), send
    unconfirmed direct uploads to be destroyed (media/uploads.discard_stale_intents), and
    anonymise leads with no activity for the retention period (leads/erasure.py, SECURITY.md §8).
    """
    now = now or utcnow()
    old_sessions = delete(UserSession).where(
        or_(
            UserSession.expires_at < now - timedelta(days=1),
            UserSession.revoked_at < now - timedelta(days=30),
        )
    )
    old_tokens = delete(PasswordResetToken).where(
        PasswordResetToken.expires_at < now - timedelta(days=1)
    )
    old_buckets = delete(RateLimitBucket).where(RateLimitBucket.expires_at < now)
    old_challenges = delete(SignInChallenge).where(
        SignInChallenge.expires_at < now - timedelta(days=1)
    )
    with get_sessionmaker()() as db, db.begin():
        sessions = rows_affected(db.execute(old_sessions))
        tokens = rows_affected(db.execute(old_tokens))
        buckets = rows_affected(db.execute(old_buckets))
        challenges = rows_affected(db.execute(old_challenges))
        uploads = discard_stale_intents(db, now)
    # WHY its own transaction: a problem anonymising one lead must not undo the session and
    # token clean-up above (it raises after they are committed, and the next run retries).
    with get_sessionmaker()() as db, db.begin():
        anonymised = anonymise_inactive(db, now)
    # The AI index's daily backstop (D-059): queue only, no model call here.
    with get_sessionmaker()() as db, db.begin():
        ai_queued = ai_handlers.queue_everything(db)
    counts = {
        "sessions": sessions,
        "reset_tokens": tokens,
        "rate_limit_buckets": buckets,
        "sign_in_challenges": challenges,
        "unconfirmed_uploads": uploads,
        "leads_anonymised": anonymised,
        "ai_reindex_queued": ai_queued,
    }
    log.info("cleanup_done", **counts)
    return counts


def maybe_cleanup(now: datetime | None = None) -> bool:
    """Run `cleanup()` if it hasn't run in the last 24 hours. Returns True when it ran."""
    now = now or utcnow()
    with get_sessionmaker()() as db:
        row = db.get(Setting, _CLEANUP_SETTING)
        last = row.value.get("last_run_at") if row else None
        if last and now - datetime.fromisoformat(last) < CLEANUP_EVERY:
            return False
        cleanup(now)
        _mark_cleanup(db, row, now)
        return True


def _mark_cleanup(db: Session, row: Setting | None, now: datetime) -> None:
    value = {"last_run_at": now.isoformat()}
    if row is None:
        db.add(Setting(key=_CLEANUP_SETTING, value=value))
    else:
        row.value = value
    db.commit()
