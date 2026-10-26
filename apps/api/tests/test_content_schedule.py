"""The schedule tick (ARCHITECTURE §10): scheduled pages go live and come down on time, a
blocked or missed publish is cancelled and audited, offers announce their start and end exactly
once, and the drain endpoint runs the tick before delivering events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    create_offer,
    create_page,
    later,
    patch_page,
    publish_page,
    soon,
    unpublish_page,
)
from empire_api.content import page_rules
from empire_api.content.models import Offer, Page
from empire_api.content.schedule import schedule_tick
from empire_api.seo.models import Redirect
from projects_support import audit_rows, events, ok


def test_scheduled_publish_and_unpublish(owner: SignedIn, db: Session) -> None:
    page = create_page(owner, publish_at=soon(1), unpublish_at=soon(3))
    assert schedule_tick().published == 0  # not due yet
    result = schedule_tick(now=later(25))
    assert result.published == 1
    db.expire_all()
    row = db.get(Page, page["id"])
    assert row is not None and row.publish_state == "published" and row.publish_at is None
    published = events(db, "page.published")
    assert len(published) == 1 and published[0].payload["scheduled"] is True
    assert published[0].actor_id is None
    assert audit_rows(db, "page.published")[-1].actor_user_id is None
    assert schedule_tick(now=later(26)).published == 0  # once only
    assert schedule_tick(now=later(73)).unpublished == 1
    db.expire_all()
    row = db.get(Page, page["id"])
    assert row is not None and row.publish_state == "draft" and row.unpublish_at is None
    assert events(db, "page.unpublished")[-1].payload["scheduled"] is True


def test_a_blocked_scheduled_publish_is_cancelled(
    owner: SignedIn, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    page = create_page(owner, publish_at=soon(1))
    row = db.get(Page, page["id"])
    assert row is not None
    row.is_sample = True
    db.commit()
    monkeypatch.setattr(page_rules, "is_production", lambda: True)
    assert schedule_tick(now=later(25)).skipped == 1
    db.expire_all()
    row = db.get(Page, page["id"])
    assert row is not None and row.publish_state == "draft" and row.publish_at is None
    cancelled = audit_rows(db, "page.scheduled_publish_cancelled")
    assert page_rules.SAMPLE_ON_LIVE_SITE in cancelled[0].changes["reason"][1]
    assert events(db, "page.published") == []


def test_a_missed_window_is_cancelled_not_published(owner: SignedIn, db: Session) -> None:
    page = create_page(owner, publish_at=soon(1), unpublish_at=soon(2))
    assert schedule_tick(now=later(72)).skipped == 1
    db.expire_all()
    row = db.get(Page, page["id"])
    assert row is not None and row.publish_state == "draft"
    assert row.publish_at is None and row.unpublish_at is None
    assert events(db, "page.published") == []


def test_going_live_on_schedule_claims_the_path(owner: SignedIn, db: Session) -> None:
    db.add(Redirect(from_path="/offers-2026", to_path="/contact"))
    db.commit()
    create_page(owner, title="Offers 2026", publish_at=soon(1))
    schedule_tick(now=later(25))
    db.expire_all()
    assert db.query(Redirect).count() == 0
    assert events(db, "redirect.changed")[-1].payload["change"] == "deleted"


def test_offers_announce_start_and_end_once(owner: SignedIn, db: Session) -> None:
    offer = create_offer(owner, is_active=True, starts_at=soon(1), ends_at=soon(2))
    assert offer["state"] == "scheduled"
    assert events(db, "offer.started") == []
    assert schedule_tick(now=later(30)).offers_started == 1
    assert schedule_tick(now=later(31)).offers_started == 0
    db.expire_all()
    row = db.get(Offer, offer["id"])
    assert row is not None and row.went_live_at is not None and row.is_live_announced
    assert schedule_tick(now=later(60)).offers_ended == 1
    assert schedule_tick(now=later(61)).offers_ended == 0
    assert len(events(db, "offer.started")) == 1 and len(events(db, "offer.ended")) == 1


def test_the_drain_endpoint_runs_the_tick(owner: SignedIn, client: TestClient, db: Session) -> None:
    page = create_page(owner, publish_at=soon(1))
    row = db.get(Page, page["id"])
    assert row is not None
    row.publish_at = datetime.now(UTC) - timedelta(minutes=1)  # due now (bypassing the API rule)
    db.commit()
    response = client.post(
        "/api/v1/internal/outbox/drain",
        headers={"X-Internal-Key": "test-internal-key-0123456789-abcdefghijklmnop"},
    )
    assert response.status_code == 200, response.text
    db.expire_all()
    row = db.get(Page, page["id"])
    assert row is not None and row.publish_state == "published"
    assert events(db, "page.published")[0].status == "delivered"


def test_an_edit_that_makes_an_offer_live_announces_it_at_once(
    owner: SignedIn, db: Session
) -> None:
    offer = create_offer(owner)
    assert offer["state"] == "inactive" and offer["has_been_live"] is False
    live = ok(
        owner.client.patch(
            f"/api/v1/admin/offers/{offer['id']}", json={"is_active": True}, headers=owner.headers()
        )
    )
    assert live["state"] == "live" and live["has_been_live"] is True
    assert len(events(db, "offer.started")) == 1 and len(events(db, "offer.changed")) == 1
    off = ok(
        owner.client.patch(
            f"/api/v1/admin/offers/{offer['id']}",
            json={"is_active": False},
            headers=owner.headers(),
        )
    )
    assert off["state"] == "inactive"
    assert len(events(db, "offer.ended")) == 1


def test_page_schedule_can_be_cleared(owner: SignedIn) -> None:
    page = create_page(owner, publish_at=soon(1))
    cleared = ok(patch_page(owner, page["id"], {"publish_at": None}))
    assert cleared["publish_at"] is None


def test_a_live_page_cant_be_scheduled_to_publish(owner: SignedIn) -> None:
    """M2: a publish time on a page that is already live has nothing to do, and would bring the
    page back after someone took it down."""
    page = create_page(owner)
    ok(publish_page(owner, page["id"]))
    refused = patch_page(owner, page["id"], {"publish_at": soon(1)})
    assert refused.status_code == 422 and refused.json()["errors"][0]["field"] == "publish_at"
    ok(patch_page(owner, page["id"], {"unpublish_at": soon(1)}))  # the take-down time is fine


def _stale_publish_at(db: Session, page_id: str) -> None:
    """A live page carrying a publish time that has passed (data saved before the M2 fix)."""
    row = db.get(Page, page_id)
    assert row is not None
    row.publish_at = datetime.now(UTC) - timedelta(hours=1)
    db.commit()


@pytest.mark.parametrize("how", ["unpublish", "patch_draft", "scheduled_take_down"])
def test_a_stale_publish_time_never_brings_a_page_back(
    owner: SignedIn, db: Session, how: str
) -> None:
    """M2 end to end: live page with a passed publish_at → taken down → the tick leaves it a
    draft, because every way of taking a page down clears publish_at."""
    page = create_page(owner)
    ok(publish_page(owner, page["id"]))
    if how == "scheduled_take_down":
        ok(patch_page(owner, page["id"], {"unpublish_at": soon(1)}))
    _stale_publish_at(db, page["id"])
    if how == "unpublish":
        ok(unpublish_page(owner, page["id"]))
    elif how == "patch_draft":
        ok(patch_page(owner, page["id"], {"publish_state": "draft"}))
    else:
        assert schedule_tick(now=later(25)).unpublished == 1
    db.expire_all()
    row = db.get(Page, page["id"])
    assert row is not None and row.publish_state == "draft" and row.publish_at is None
    result = schedule_tick(now=later(26))
    assert result.published == 0 and result.skipped == 0
    db.expire_all()
    row = db.get(Page, page["id"])
    assert row is not None and row.publish_state == "draft"
    assert len(events(db, "page.published")) == 1  # only the first, manual publish
