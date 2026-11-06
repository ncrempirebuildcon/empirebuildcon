"""Fixed-window rate limits stored in PostgreSQL (D-010, SECURITY.md §1).

How it works:
  1. The window start is "now" rounded down to the window length (e.g. 15 minutes).
  2. One UPSERT increments the counter for (key, window_start) and returns the new count.
  3. Over the limit → the caller answers 429 with Retry-After = seconds to the next window.

INVARIANT: the counter is written on its own connection and committed at once, so a request
that later fails (wrong password → 401) still counts. Never move this into the request session.
That connection comes from the small side pool (db.get_side_engine, D-054), never the request
pool: a request holding its session must not wait for a second connection from the same pool.
PERF: one tiny write per limited request; the daily clean-up deletes expired buckets.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import text

from empire_api.db import get_side_engine
from empire_api.errors import ApiProblem
from empire_api.timeutil import utcnow

_UPSERT = text(
    """
    INSERT INTO rate_limit_bucket (key, window_start, count, expires_at)
    VALUES (:key, :window_start, 1, :expires_at)
    ON CONFLICT (key, window_start)
    DO UPDATE SET count = rate_limit_bucket.count + 1
    RETURNING count
    """
)


@dataclass(frozen=True)
class RateResult:
    allowed: bool
    count: int
    retry_after: int


def _window_start(now: datetime, window_seconds: int) -> datetime:
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(epoch - epoch % window_seconds, tz=now.tzinfo)


def hit(key: str, *, limit: int, window_seconds: int, now: datetime | None = None) -> RateResult:
    """Count one attempt against `key`. Returns whether it is within `limit` for the window."""
    now = now or utcnow()
    start = _window_start(now, window_seconds)
    ends = start + timedelta(seconds=window_seconds)
    with get_side_engine().begin() as conn:
        count = int(
            conn.execute(
                _UPSERT, {"key": key, "window_start": start, "expires_at": ends}
            ).scalar_one()
        )
    retry_after = max(1, int((ends - now).total_seconds()))
    return RateResult(allowed=count <= limit, count=count, retry_after=retry_after)


def clear(key: str) -> None:
    """Forget every window of `key` (e.g. after a successful sign-in)."""
    with get_side_engine().begin() as conn:
        conn.execute(text("DELETE FROM rate_limit_bucket WHERE key = :key"), {"key": key})


def clear_prefix(prefix: str) -> None:
    """Forget every key that starts with `prefix` (e.g. all networks of one account on unlock)."""
    escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    with get_side_engine().begin() as conn:
        conn.execute(
            text("DELETE FROM rate_limit_bucket WHERE key LIKE :pattern ESCAPE '\\'"),
            {"pattern": escaped + "%"},
        )


def enforce(key: str, *, limit: int, window_seconds: int, message: str) -> None:
    """Raise a 429 problem with Retry-After when `key` is over its limit."""
    result = hit(key, limit=limit, window_seconds=window_seconds)
    if not result.allowed:
        raise ApiProblem(429, message, headers={"Retry-After": str(result.retry_after)})
