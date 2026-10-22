"""Outbox delivery, retries, the internal drain endpoint and the daily clean-up (D-010)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from empire_api.db import get_engine, get_sessionmaker
from empire_api.integrations import handlers
from empire_api.integrations.outbox_drain import (
    DRAIN_LOCK_KEY,
    RETRY_DELAYS,
    cleanup,
    drain,
    maybe_cleanup,
)
from empire_api.platform import outbox, rate_limit
from empire_api.platform.models import OutboxEvent, RateLimitBucket
from empire_api.timeutil import utcnow

KEY = {"X-Internal-Key": "test-internal-key-0123456789-abcdefghijklmnop"}


def _emit(type_: str = "test.event") -> int:
    with get_sessionmaker()() as db:
        event = outbox.emit(db, type_=type_, aggregate_type="test", aggregate_id="1", data={"n": 1})
        db.commit()
        return event.id


@pytest.fixture
def failing_handler() -> Iterator[None]:
    def boom(db: Session, event: OutboxEvent) -> None:
        raise RuntimeError("webhook down")

    handlers.on("test.fails")(boom)
    yield
    handlers._registry["test.fails"].remove(boom)  # test-only: undo the registration


def test_events_are_delivered(db: Session) -> None:
    event_id = _emit()
    result = drain()
    assert (result.processed, result.failed, result.remaining) == (1, 0, 0)
    row = db.get(OutboxEvent, event_id)
    assert row is not None and row.status == "delivered" and row.attempts == 1


def test_emit_without_commit_leaves_no_event(db: Session) -> None:
    with get_sessionmaker()() as other:
        outbox.emit(other, type_="test.event", aggregate_type="test", aggregate_id="1")
        other.rollback()
    assert db.scalars(select(OutboxEvent)).all() == []


def test_failures_follow_the_retry_schedule_then_die(db: Session, failing_handler: None) -> None:
    event_id = _emit("test.fails")
    now = utcnow()
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        result = drain(now=now)
        assert result.failed == 1
        db.expire_all()
        row = db.get(OutboxEvent, event_id)
        assert row is not None and row.status == "pending" and row.attempts == attempt
        assert row.available_at == now + delay
        assert drain(now=now).failed == 0  # not due yet
        now = row.available_at
    assert drain(now=now).failed == 1
    db.expire_all()
    row = db.get(OutboxEvent, event_id)
    assert row is not None and row.status == "dead" and row.attempts == len(RETRY_DELAYS) + 1
    assert row.last_error == "RuntimeError: webhook down"


def test_drain_endpoint_needs_the_internal_key(client: TestClient) -> None:
    assert client.post("/api/v1/internal/outbox/drain").status_code == 401
    wrong = client.post("/api/v1/internal/outbox/drain", headers={"X-Internal-Key": "wrong"})
    assert wrong.status_code == 401
    _emit()
    ok = client.post("/api/v1/internal/outbox/drain", headers=KEY)
    assert ok.status_code == 200
    assert ok.json() == {"processed": 1, "failed": 0, "remaining": 0}


def test_only_one_drain_runs_at_a_time(client: TestClient) -> None:
    with get_engine().connect() as holder:
        holder.execute(text("SELECT pg_advisory_lock(:k)"), {"k": DRAIN_LOCK_KEY})
        try:
            busy = client.post("/api/v1/internal/outbox/drain", headers=KEY)
            assert busy.status_code == 429
            assert busy.headers["retry-after"] == "30"
        finally:
            holder.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": DRAIN_LOCK_KEY})
            holder.commit()
    assert client.post("/api/v1/internal/outbox/drain", headers=KEY).status_code == 200


def test_cleanup_removes_expired_rows_once_a_day(db: Session) -> None:
    rate_limit.hit("test:key", limit=5, window_seconds=60, now=utcnow() - timedelta(hours=2))
    assert maybe_cleanup() is True
    assert db.scalars(select(RateLimitBucket)).all() == []
    assert maybe_cleanup() is False  # already ran today
    assert maybe_cleanup(now=utcnow() + timedelta(hours=25)) is True
    assert cleanup()["rate_limit_buckets"] == 0


def test_rate_limit_counts_within_a_window() -> None:
    now = utcnow()
    results = [rate_limit.hit("test:rl", limit=2, window_seconds=600, now=now) for _ in range(3)]
    assert [r.allowed for r in results] == [True, True, False]
    later = rate_limit.hit("test:rl", limit=2, window_seconds=600, now=now + timedelta(seconds=601))
    assert later.allowed
