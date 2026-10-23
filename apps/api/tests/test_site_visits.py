"""The site-visit calendar (leads/visits.py, D-016): calendar days in IST, filters, confirm,
reschedule, complete, no-show, cancel, who handles it, and the lead moving to `site_visit`."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user
from empire_api.leads.models import LeadActivity, SiteVisit
from empire_api.leads.visits import HANDLER_INVALID, NEEDS_TIME
from empire_api.timeutil import IST, today_ist
from leads_support import LEADS, VISITS, enquiry, lead_by_reference, published_project, submit_ok
from projects_support import audit_rows, events, ok

Texts = dict[str, dict[str, Any]]


@pytest.fixture
def live(owner: SignedIn, qr_present: None) -> dict[str, Any]:
    return published_project(owner)


def request_visit(
    client: TestClient,
    texts: Texts,
    project: dict[str, Any],
    n: int,
    day: date,
    slot: str = "morning",
) -> str:
    body = enquiry(texts, n, name=f"Buyer {n}", project_slug=project["slug"], source="site_visit")
    return submit_ok(
        client, {**body, "preferred_date": day.isoformat(), "preferred_slot": slot}, "site-visits"
    )


def visit_of(owner: SignedIn, db: Session, reference: str) -> dict[str, Any]:
    lead = lead_by_reference(db, reference)
    [visit] = ok(owner.client.get(VISITS, params={"lead_id": str(lead.id)}))
    return dict(visit)


def change(owner: SignedIn, visit_id: str, **body: Any) -> Any:
    return owner.client.patch(f"{VISITS}/{visit_id}", json=body, headers=owner.headers())


def ist(day: date, hour: int, minute: int = 0) -> str:
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=IST).isoformat()


def test_a_visit_shows_its_lead_and_project(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, live: dict[str, Any]
) -> None:
    day = today_ist() + timedelta(days=2)
    ref = request_visit(client, texts, live, 1, day, "afternoon")
    visit = visit_of(owner, db, ref)
    assert visit["lead_reference"] == ref and visit["lead_name"] == "Buyer 1"
    assert visit["lead_phone_e164"] == "+919876500001" and visit["lead_status"] == "new"
    assert visit["project"] == {"id": live["id"], "slug": live["slug"], "name": live["name"]}
    assert (visit["preferred_date"], visit["preferred_slot"]) == (day.isoformat(), "afternoon")
    assert (visit["status"], visit["confirmed_for"], visit["handled_by"]) == (
        "requested",
        None,
        None,
    )
    lead = ok(owner.client.get(f"{LEADS}/{visit['lead_id']}"))
    assert lead["next_visit"]["id"] == visit["id"]


def test_confirming_needs_a_time_and_moves_the_lead_forward(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, live: dict[str, Any]
) -> None:
    day = today_ist() + timedelta(days=1)
    visit = visit_of(owner, db, request_visit(client, texts, live, 1, day))
    refused = change(owner, visit["id"], status="confirmed")
    assert refused.status_code == 422
    assert refused.json()["errors"] == [{"field": "confirmed_for", "message": NEEDS_TIME}]
    naive = change(owner, visit["id"], status="confirmed", confirmed_for="2026-10-24T11:00:00")
    assert naive.status_code == 422  # a time without a timezone is ambiguous
    done = ok(change(owner, visit["id"], status="confirmed", confirmed_for=ist(day, 11)))
    assert done["status"] == "confirmed"
    assert datetime.fromisoformat(done["confirmed_for"]).astimezone(IST).hour == 11
    assert done["lead_status"] == "site_visit"
    moved = events(db, "lead.status_changed")
    assert [(e.payload["from"], e.payload["to"], e.payload["via"]) for e in moved] == [
        ("new", "site_visit", "site_visit_confirmed")
    ]
    [updated] = events(db, "site_visit.updated")
    assert updated.payload["status"] == "confirmed" and updated.contains_personal_data is False
    kinds = db.scalars(
        select(LeadActivity.kind)
        .where(LeadActivity.lead_id == visit["lead_id"])
        .order_by(LeadActivity.created_at)
    ).all()
    assert kinds[-2:] == ["visit_updated", "status_changed"]


def test_a_confirm_never_moves_a_lead_backwards(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, live: dict[str, Any]
) -> None:
    day = today_ist() + timedelta(days=1)
    visit = visit_of(owner, db, request_visit(client, texts, live, 1, day))
    ok(
        owner.client.patch(
            f"{LEADS}/{visit['lead_id']}", json={"status": "negotiation"}, headers=owner.headers()
        )
    )
    done = ok(change(owner, visit["id"], status="confirmed", confirmed_for=ist(day, 10)))
    assert done["lead_status"] == "negotiation"


def test_reschedule_complete_no_show_and_cancel(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, live: dict[str, Any]
) -> None:
    day = today_ist() + timedelta(days=1)
    visit = visit_of(owner, db, request_visit(client, texts, live, 1, day))
    ok(change(owner, visit["id"], status="confirmed", confirmed_for=ist(day, 10)))
    later = ok(change(owner, visit["id"], confirmed_for=ist(day + timedelta(days=1), 16, 30)))
    assert datetime.fromisoformat(later["confirmed_for"]).astimezone(IST).date() == day + timedelta(
        days=1
    )
    for status in ("completed", "no_show", "cancelled", "requested"):
        assert ok(change(owner, visit["id"], status=status))["status"] == status
    assert change(owner, visit["id"], status=None).status_code == 422
    assert change(owner, visit["id"], status="lost").status_code == 422
    audited = audit_rows(db, "site_visit.updated")
    assert audited[1].changes["confirmed_for"][0] != audited[1].changes["confirmed_for"][1]


def test_handled_by_and_notes(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    live: dict[str, Any],
    app: FastAPI,
) -> None:
    visit = visit_of(owner, db, request_visit(client, texts, live, 1, today_ist()))
    sales = make_user("sales", email="h@example.com", name="Handler")
    marketer = make_user("marketing", email="m@example.com")
    done = ok(change(owner, visit["id"], handled_by_user_id=str(sales.id), notes="Gate 2 pass"))
    assert done["handled_by"] == {"id": str(sales.id), "name": "Handler"}
    assert done["notes"] == "Gate 2 pass"
    wrong = change(owner, visit["id"], handled_by_user_id=str(marketer.id))
    assert wrong.json()["errors"] == [{"field": "handled_by_user_id", "message": HANDLER_INVALID}]
    [row] = audit_rows(db, "site_visit.updated")
    assert row.changes["notes"] == ["[hidden]", "[hidden]"]
    assert "Gate 2" not in str(row.changes)
    activity = db.scalars(
        select(LeadActivity.data).where(LeadActivity.kind == "visit_updated")
    ).all()
    assert "Gate 2" not in str(activity)
    cleared = ok(change(owner, visit["id"], notes="", handled_by_user_id=None))
    assert cleared["notes"] is None and cleared["handled_by"] is None


def test_nothing_changed_writes_nothing(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, live: dict[str, Any]
) -> None:
    visit = visit_of(owner, db, request_visit(client, texts, live, 1, today_ist()))
    ok(change(owner, visit["id"], status="requested"))
    assert audit_rows(db, "site_visit.updated") == []


def test_the_calendar_uses_the_confirmed_day_in_ist_and_filters(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    live: dict[str, Any],
    intake_unlimited: None,
) -> None:
    today = today_ist()
    first = visit_of(owner, db, request_visit(client, texts, live, 1, today + timedelta(days=5)))
    second = visit_of(owner, db, request_visit(client, texts, live, 2, today + timedelta(days=1)))
    third = visit_of(owner, db, request_visit(client, texts, live, 3, today + timedelta(days=3)))
    # The first buyer agreed to come earlier: 00:30 IST on day 2 (still day 1 in UTC).
    ok(
        change(
            owner,
            first["id"],
            status="confirmed",
            confirmed_for=ist(today + timedelta(days=2), 0, 30),
        )
    )
    order = [v["lead_name"] for v in ok(owner.client.get(VISITS))]
    assert order == ["Buyer 2", "Buyer 1", "Buyer 3"]
    day2 = (today + timedelta(days=2)).isoformat()
    on_day2 = ok(owner.client.get(VISITS, params={"from": day2, "to": day2}))
    assert [v["lead_name"] for v in on_day2] == ["Buyer 1"]
    assert [
        v["lead_name"] for v in ok(owner.client.get(VISITS, params={"status": "requested"}))
    ] == [
        "Buyer 2",
        "Buyer 3",
    ]
    other = published_project(owner, "Other Site")
    assert ok(owner.client.get(VISITS, params={"project_id": other["id"]})) == []
    assert second and third


def test_an_unknown_visit_is_404(owner: SignedIn) -> None:
    response = change(owner, "01a16862-56ac-74cc-b260-0dfe5c63b4c5", status="cancelled")
    assert response.status_code == 404


def test_sample_visits_are_flagged(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, live: dict[str, Any]
) -> None:
    visit = visit_of(owner, db, request_visit(client, texts, live, 1, today_ist()))
    db.execute(update(SiteVisit).where(SiteVisit.id == visit["id"]).values(is_sample=True))
    db.commit()
    assert ok(owner.client.get(VISITS))[0]["is_sample"] is True
