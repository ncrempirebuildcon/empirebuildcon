"""Sample leads (`empire-api seed --sample`, leads/seed.py, D-015): marked, unmistakably fake,
across stages and sources, with visits and consent, never alerted, idempotent, never in
production; and the draft consent texts that `seed` adds in development and test."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from conftest import make_user, sign_in
from empire_api.cli import app
from empire_api.config import get_settings
from empire_api.content.models import ConsentText
from empire_api.leads.models import Lead, LeadConsent, SiteVisit
from empire_api.leads.phone import is_sample_number
from empire_api.leads.seed import SampleLeadsRefusedError, seed_sample_leads
from empire_api.platform.models import OutboxEvent

runner = CliRunner()


def test_seed_adds_the_draft_consent_texts_in_development_and_test(db: Session) -> None:
    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0, result.output
    assert "2 draft consent texts" in result.output
    kinds = set(db.scalars(select(ConsentText.kind).where(ConsentText.is_current.is_(True))))
    assert kinds == {"lead_form", "marketing"}
    assert "0 draft consent texts" in runner.invoke(app, ["seed"]).output


def test_seed_sample_adds_twelve_marked_fake_leads_and_four_visits(db: Session) -> None:
    result = runner.invoke(app, ["seed", "--sample"])
    assert result.exit_code == 0, result.output
    assert "Sample leads: 12 added" in result.output and "4 site visits" in result.output
    leads = db.scalars(select(Lead).order_by(Lead.created_at)).all()
    assert len(leads) == 12
    for lead in leads:
        # COMPLIANCE (D-015): obviously fake and marked.
        assert lead.is_sample and lead.name.startswith("Sample Lead ")
        assert is_sample_number(lead.phone_e164)
        assert lead.email is None or lead.email.endswith("@example.com")
    assert {lead.status for lead in leads} == {
        "new",
        "contacted",
        "site_visit",
        "negotiation",
        "booked",
        "lost",
    }
    assert len({lead.source for lead in leads}) >= 7
    assert len({lead.project_id for lead in leads}) == 3  # both sample projects and general
    assert all(lead.lost_reason for lead in leads if lead.status == "lost")
    assert sum(1 for lead in leads if lead.duplicate_of_id) == 1
    visits = db.scalars(select(SiteVisit)).all()
    assert len(visits) == 4 and all(v.is_sample for v in visits)
    assert {v.status for v in visits} == {"requested", "confirmed", "completed"}
    consented = set(db.scalars(select(LeadConsent.lead_id).where(LeadConsent.kind == "lead_form")))
    assert consented == {lead.id for lead in leads}  # INVARIANT: every lead has consent
    assert (
        db.scalar(
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.type.like("lead.%"))
        )
        == 0
    )
    again = runner.invoke(app, ["seed", "--sample"])
    assert "Sample leads: 0 added, 12 already there" in again.output
    assert db.scalar(select(func.count()).select_from(Lead)) == 12


def test_sample_leads_read_back_through_the_api(client: TestClient) -> None:
    assert runner.invoke(app, ["seed", "--sample"]).exit_code == 0
    signed = sign_in(client, make_user("admin"))
    page = signed.client.get("/api/v1/admin/leads", params={"per_page": 100}).json()
    assert page["meta"]["total"] == 12
    assert {item["is_sample"] for item in page["items"]} == {True}
    with_text = [i for i in page["items"] if i["consent"]["text_version"] is not None]
    noted = [i for i in page["items"] if i["consent"]["consent_note"]]
    assert with_text and noted  # forms show the draft text; phone/manual leads carry a note
    assert signed.client.get("/api/v1/admin/site-visits").status_code == 200
    assert signed.client.get("/api/v1/admin/dashboard").status_code == 200
    hidden = signed.client.get("/api/v1/admin/leads", params={"include_sample": "false"}).json()
    assert hidden["meta"]["total"] == 0


def test_sample_leads_are_refused_in_production(
    monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    monkeypatch.setattr(get_settings(), "app_env", "production")
    result = runner.invoke(app, ["seed", "--sample"])
    assert result.exit_code == 1
    with pytest.raises(SampleLeadsRefusedError):
        seed_sample_leads(db)
    assert db.scalar(select(func.count()).select_from(Lead)) == 0


def test_without_the_sample_projects_no_leads_are_added(db: Session) -> None:
    result = seed_sample_leads(db)
    assert (result.added, result.visits) == (0, 0)
