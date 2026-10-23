"""Erasure on request and the retention clean-up (leads/erasure.py, SECURITY.md §8): the stub,
what stays, the audit row, and nothing personal left anywhere in the database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.integrations.outbox_drain import cleanup
from empire_api.leads import erasure
from empire_api.leads.models import Lead, LeadConsent, LeadNote, SiteVisit
from empire_api.platform.models import OutboxEvent
from empire_api.site_settings.models import Setting
from empire_api.timeutil import today_ist, utcnow
from leads_support import (
    LEADS,
    VISITS,
    enquiry,
    given,
    lead_by_reference,
    published_project,
    submit_ok,
)
from projects_support import audit_rows, ok

Texts = dict[str, dict[str, Any]]
SECRETS = (
    "Priya Singh",
    "9876543210",
    "priya@example.com",
    "budget is tight",
    "https://news.example/ad",
    "gclid-abc-123",
    "Called her twice",
    "Gate 2 pass ready",
)


@pytest.fixture
def full_lead(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, qr_present: None
) -> dict[str, Any]:
    """A lead with every personal field filled, a note, a visit with notes, marketing consent."""
    live = published_project(owner)
    body = enquiry(
        texts,
        name="Priya Singh",
        phone="98765 43210",
        email="priya@example.com",
        message="My budget is tight",
        referrer="https://news.example/ad",
        click_ids={"gclid": "gclid-abc-123"},
        utm={"source": "google", "campaign": "festive"},
        project_slug=live["slug"],
        source="site_visit",
        marketing_consent=given(texts["marketing"]),
        preferred_date=(today_ist() + timedelta(days=2)).isoformat(),
        preferred_slot="morning",
    )
    ref = submit_ok(client, body, "site-visits")
    lead_id = str(lead_by_reference(db, ref).id)
    ok(
        owner.client.post(
            f"{LEADS}/{lead_id}/notes", json={"body": "Called her twice"}, headers=owner.headers()
        ),
        201,
    )
    [visit] = ok(owner.client.get(VISITS, params={"lead_id": lead_id}))
    ok(
        owner.client.patch(
            f"{VISITS}/{visit['id']}", json={"notes": "Gate 2 pass ready"}, headers=owner.headers()
        )
    )
    ok(
        owner.client.patch(
            f"{LEADS}/{lead_id}", json={"status": "contacted"}, headers=owner.headers()
        )
    )
    return {"id": lead_id, "reference": ref, "visit": visit["id"], "project": live}


def database_text(db: Session) -> str:
    """Every row of every table, as text: where personal data could hide."""
    db.expire_all()
    tables = db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all()
    rows = [
        str(db.scalars(text(f'SELECT t::text FROM "{table}" t')).all())  # noqa: S608 — catalog names
        for table in tables
    ]
    return "\n".join(rows)


def erase(owner: SignedIn, lead_id: str) -> None:
    ok(owner.client.delete(f"{LEADS}/{lead_id}", headers=owner.headers()), 204)


def test_erasure_leaves_a_stub_and_nothing_personal_anywhere(
    owner: SignedIn, full_lead: dict[str, Any], db: Session
) -> None:
    before = database_text(db)
    assert all(secret in before for secret in SECRETS)  # the scan can see them
    erase(owner, full_lead["id"])
    after = database_text(db)
    for secret in SECRETS:
        assert secret not in after, secret
    lead = lead_by_reference(db, full_lead["reference"])
    assert (lead.name, lead.phone_e164) == ("[erased]", "[erased]")
    assert lead.email is None and lead.message is None and lead.ip_hash is None
    assert lead.erased_at is not None


def test_erasure_keeps_what_reports_and_the_consent_proof_need(
    owner: SignedIn, full_lead: dict[str, Any], db: Session
) -> None:
    erase(owner, full_lead["id"])
    view = ok(owner.client.get(f"{LEADS}/{full_lead['id']}"))
    assert view["reference"] == full_lead["reference"]
    assert (view["status"], view["source"]) == ("contacted", "site_visit")
    assert view["utm"]["source"] == "google" and view["utm"]["campaign"] == "festive"
    assert view["project"]["id"] == full_lead["project"]["id"]
    assert view["consent"]["text_version"] == 1 and view["consent"]["checkbox_label"]
    assert view["consent"]["page_url"] is None
    assert view["marketing_consent"]["text_version"] == 1
    assert view["erased_at"] is not None
    notes = db.scalars(select(LeadNote.body).where(LeadNote.lead_id == full_lead["id"])).all()
    assert list(notes) == ["[erased]"]
    visit = db.get(SiteVisit, full_lead["visit"])
    assert visit is not None and visit.notes is None and visit.status == "requested"
    timeline = [a["kind"] for a in ok(owner.client.get(f"{LEADS}/{full_lead['id']}/activity"))]
    assert timeline[0] == "erased" and "created" in timeline


def test_erasure_is_audited_and_scrubs_stored_events(
    owner: SignedIn, full_lead: dict[str, Any], db: Session
) -> None:
    erase(owner, full_lead["id"])
    [row] = audit_rows(db, "lead.erased")
    assert row.actor_user_id == owner.user.id
    assert row.changes["reason"] == [None, "request"]
    assert "name" in row.changes["fields"][1] and row.changes["notes"] == [None, 1]
    created = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "lead.created")).all()
    assert [e.payload for e in created] == [
        {"lead_id": full_lead["id"], "reference": full_lead["reference"], "erased": True}
    ]


def test_erasing_twice_changes_nothing_and_the_row_is_never_deleted(
    owner: SignedIn, full_lead: dict[str, Any], db: Session
) -> None:
    """INVARIANT: the lead row itself is never deleted."""
    erase(owner, full_lead["id"])
    erase(owner, full_lead["id"])
    assert len(audit_rows(db, "lead.erased")) == 1
    assert db.get(Lead, full_lead["id"]) is not None
    consent_rows = db.scalars(select(LeadConsent).where(LeadConsent.lead_id == full_lead["id"]))
    assert len(list(consent_rows)) == 2


def test_an_erased_lead_cannot_be_changed(owner: SignedIn, full_lead: dict[str, Any]) -> None:
    erase(owner, full_lead["id"])
    lead = f"{LEADS}/{full_lead['id']}"
    assert (
        owner.client.patch(
            lead, json={"status": "lost", "lost_reason": "other"}, headers=owner.headers()
        ).status_code
        == 409
    )
    assert (
        owner.client.post(f"{lead}/notes", json={"body": "x"}, headers=owner.headers()).status_code
        == 409
    )
    visit = owner.client.patch(
        f"{VISITS}/{full_lead['visit']}", json={"status": "cancelled"}, headers=owner.headers()
    )
    assert visit.status_code == 409


# --- Retention ----------------------------------------------------------------------------------


def age(db: Session, lead_id: str, *, days: int) -> None:
    db.execute(
        update(Lead)
        .where(Lead.id == lead_id)
        .values(last_activity_at=utcnow() - timedelta(days=days))
    )
    db.commit()


def leads_made(client: TestClient, texts: Texts, db: Session, count: int) -> list[str]:
    return [
        str(lead_by_reference(db, submit_ok(client, enquiry(texts, n))).id) for n in range(count)
    ]


def test_leads_inactive_for_three_years_are_anonymised_daily(
    client: TestClient, texts: Texts, db: Session
) -> None:
    old, recent = leads_made(client, texts, db, 2)
    age(db, old, days=3 * 365 + 2)
    age(db, recent, days=2 * 365)
    counts = cleanup()
    assert counts["leads_anonymised"] == 1
    db.expire_all()
    assert db.get(Lead, old).erased_at is not None  # type: ignore[union-attr]
    assert db.get(Lead, recent).erased_at is None  # type: ignore[union-attr]
    [row] = audit_rows(db, "lead.anonymised")
    assert row.actor_user_id is None and row.changes["reason"] == [None, "retention"]
    assert cleanup()["leads_anonymised"] == 0  # already done


def test_the_retention_period_is_a_setting(client: TestClient, texts: Texts, db: Session) -> None:
    [lead] = leads_made(client, texts, db, 1)
    age(db, lead, days=400)
    db.add(Setting(key="privacy", value={"lead_retention_years": 1}))
    db.commit()
    assert erasure.retention_years(db) == 1
    assert cleanup()["leads_anonymised"] == 1


@pytest.mark.parametrize("value", [0, -1, "3", True, None])
def test_a_broken_retention_setting_falls_back_to_three_years(db: Session, value: Any) -> None:
    db.add(Setting(key="privacy", value={"lead_retention_years": value}))
    db.commit()
    assert erasure.retention_years(db) == 3


def test_reading_or_exporting_doesnt_keep_a_lead_alive(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    [lead] = leads_made(client, texts, db, 1)
    age(db, lead, days=3 * 365 + 2)
    ok(owner.client.post(f"{LEADS}/{lead}/read", headers=owner.headers()), 204)
    assert owner.client.get(f"{LEADS}/export.csv", headers=owner.headers()).status_code == 200
    assert cleanup()["leads_anonymised"] == 1


def test_retention_runs_in_batches(
    client: TestClient, texts: Texts, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    for lead in leads_made(client, texts, db, 3):
        age(db, lead, days=4 * 365)
    monkeypatch.setattr(erasure, "RETENTION_BATCH", 2)
    assert cleanup()["leads_anonymised"] == 2
    assert cleanup()["leads_anonymised"] == 1


def test_years_before_handles_the_leap_day() -> None:
    leap = datetime(2028, 2, 29, 12, tzinfo=UTC)
    assert erasure.years_before(leap, 3) == datetime(2025, 2, 28, 12, tzinfo=UTC)
    assert erasure.years_before(datetime(2026, 10, 23, tzinfo=UTC), 3) == datetime(
        2023, 10, 23, tzinfo=UTC
    )
