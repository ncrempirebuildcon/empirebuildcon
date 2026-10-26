"""Public lead intake (leads/intake.py): consent (current, stale, missing; marketing optional),
validation, the honeypot, rate limits, site-visit and brochure requests, and what is stored and
announced."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.config import Settings, get_settings
from empire_api.content.models import ConsentText
from empire_api.leads import intake, reference
from empire_api.leads.models import Lead, LeadActivity, LeadConsent, SiteVisit
from empire_api.platform.models import AuditLog, RateLimitBucket
from empire_api.timeutil import today_ist
from leads_support import (
    captured_logs,
    enquiry,
    given,
    lead_by_reference,
    published_project,
    submit,
    submit_ok,
)
from media_support import attach, document
from projects_support import add_configuration, create_project, events, ok

EDGE_KEY = "test-edge-key-0123456789-abcdefghijklmnopqrstuvwxyz"
Texts = dict[str, dict[str, Any]]


def count(db: Session, model: type[Any]) -> int:
    db.expire_all()
    return int(db.scalar(select(func.count()).select_from(model)) or 0)


# --- Consent ----------------------------------------------------------------------------------


def test_an_enquiry_is_saved_with_its_consent(
    client: TestClient, texts: Texts, db: Session
) -> None:
    """INVARIANT: every lead has exactly one lead_form consent row (models.py)."""
    body = enquiry(texts, name="Priya Singh", phone="+91-98765-43210", email="p@example.com")
    accepted = ok(submit(client, body), 201)
    assert reference.looks_like_reference(accepted["reference"])
    assert "Thank you" in accepted["message"]
    lead = lead_by_reference(db, accepted["reference"])
    assert (lead.name, lead.phone_e164, lead.status, lead.source) == (
        "Priya Singh",
        "+919876543210",
        "new",
        "contact_form",
    )
    assert lead.ip_hash and "testclient" not in lead.ip_hash
    consents = db.scalars(select(LeadConsent).where(LeadConsent.lead_id == lead.id)).all()
    assert [c.kind for c in consents] == ["lead_form"]
    text = db.get(ConsentText, consents[0].consent_text_id)
    assert text is not None and text.is_current
    assert consents[0].version == text.version
    assert consents[0].checkbox_label == text.checkbox_label
    assert consents[0].page_url == body["page_url"]
    kinds = db.scalars(select(LeadActivity.kind).where(LeadActivity.lead_id == lead.id)).all()
    assert kinds == ["created"]


def test_lead_created_carries_personal_data_and_is_flagged(
    client: TestClient, texts: Texts, db: Session
) -> None:
    ref = submit_ok(client, enquiry(texts, name="Kavya Iyer"))
    [event] = events(db, "lead.created")
    assert event.contains_personal_data is True
    assert event.payload["reference"] == ref
    assert event.payload["name"] == "Kavya Iyer"
    assert event.payload["alert"] is True
    assert event.payload["marketing_consent"] is False


def test_marketing_consent_is_separate_and_never_assumed(
    client: TestClient, texts: Texts, db: Session, intake_unlimited: None
) -> None:
    without = submit_ok(client, enquiry(texts, 1))
    with_box = submit_ok(client, enquiry(texts, 2, marketing_consent=given(texts["marketing"])))
    for ref, kinds in ((without, ["lead_form"]), (with_box, ["lead_form", "marketing"])):
        lead = lead_by_reference(db, ref)
        found = db.scalars(
            select(LeadConsent.kind)
            .where(LeadConsent.lead_id == lead.id)
            .order_by(LeadConsent.kind)
        ).all()
        assert list(found) == kinds
    flags = {e.payload["reference"]: e.payload["marketing_consent"] for e in events(db)}
    assert flags == {without: False, with_box: True}


def test_a_stale_consent_version_asks_to_reload(
    client: TestClient, owner: SignedIn, texts: Texts, db: Session
) -> None:
    old = texts["lead_form"]
    new = ok(
        owner.client.post(
            "/api/v1/admin/consent-texts",
            json={"kind": "lead_form", "body": "New wording.", "checkbox_label": "I agree."},
            headers=owner.headers(),
        ),
        201,
    )
    ok(
        owner.client.post(
            f"/api/v1/admin/consent-texts/{new['id']}/publish", headers=owner.headers()
        )
    )
    stale = submit(client, enquiry(texts))
    assert stale.status_code == 409
    assert stale.json()["detail"].startswith("The consent text changed")
    assert stale.json()["errors"][0]["field"] == "consent"
    wrong_version = enquiry(texts, consent={**given(old), "version": 2})
    assert submit(client, wrong_version).status_code == 409
    assert count(db, Lead) == 0
    current = {"id": new["id"], "version": new["version"]}
    assert submit(client, enquiry(texts, consent=given(current))).status_code == 201


@pytest.mark.parametrize(
    "consent",
    [None, {"accepted": False, "consent_text_id": "x", "version": 1}, {"accepted": True}],
)
def test_missing_or_unticked_consent_is_refused(
    client: TestClient, texts: Texts, db: Session, consent: Any
) -> None:
    body = enquiry(texts)
    if consent is None:
        del body["consent"]
    else:
        body["consent"] = consent
    response = submit(client, body)
    assert response.status_code == 422
    assert any(e["field"].startswith("consent") for e in response.json()["errors"])
    assert count(db, Lead) == 0


def test_a_stale_marketing_consent_is_refused(client: TestClient, texts: Texts) -> None:
    body = enquiry(texts, marketing_consent=given(texts["lead_form"]))  # wrong text
    response = submit(client, body)
    assert response.status_code == 409
    assert response.json()["errors"][0]["field"] == "marketing_consent"


def test_enquiries_are_closed_until_a_text_is_published(client: TestClient, db: Session) -> None:
    body = enquiry({"lead_form": {"id": "01a16862-56ac-74cc-b260-0dfe5c63b4c5", "version": 1}})
    response = submit(client, body)
    assert response.status_code == 503
    assert response.json()["detail"].startswith("Enquiries aren't open yet")
    assert count(db, Lead) == 0


# --- Validation -------------------------------------------------------------------------------


def test_a_bad_phone_is_422_on_phone_with_help(client: TestClient, texts: Texts) -> None:
    response = submit(client, enquiry(texts, phone="2345678"))
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "phone",
            "message": "Add the STD code to this landline number, like 0120 456 7890.",
        }
    ]


def test_the_sample_range_is_refused_on_public_forms(client: TestClient, texts: Texts) -> None:
    response = submit(client, enquiry(texts, phone="+91 00000 00001"))
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "phone"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source", "manual"),
        ("source", "phone"),
        ("page_url", "javascript:alert(1)"),
        ("page_url", "//evil.example/x"),
        ("referrer", "data:text/html,hi"),
        ("name", "1"),
        ("name", "12345"),
        ("email", "not-an-email"),
        ("preferred_bhk", 0),
        ("budget_max_inr", -1),
    ],
)
def test_public_fields_are_checked(
    client: TestClient, texts: Texts, field: str, value: Any
) -> None:
    response = submit(client, enquiry(texts, **{field: value}))
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["field"].startswith(field)


def test_a_site_path_is_a_fine_page_url_and_unknown_fields_are_ignored(
    client: TestClient, texts: Texts, db: Session
) -> None:
    ref = submit_ok(client, enquiry(texts, page_url="/projects/x?utm_source=g", future="field"))
    assert lead_by_reference(db, ref).page_url == "/projects/x?utm_source=g"


def test_unknown_or_unpublished_projects_are_refused(
    client: TestClient, owner: SignedIn, texts: Texts
) -> None:
    draft = create_project(owner, "Draft Project")
    for slug in ("no-such-project", draft["slug"]):
        response = submit(client, enquiry(texts, project_slug=slug, source="project_form"))
        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "project_slug"


def test_a_configuration_must_belong_to_the_project(
    client: TestClient, owner: SignedIn, texts: Texts, qr_present: None, db: Session
) -> None:
    live = published_project(owner, "Live One")
    other = create_project(owner, "Other")
    foreign = add_configuration(owner, other["id"], "3 BHK")
    body = enquiry(texts, project_slug=live["slug"], configuration_id=foreign["id"])
    response = submit(client, body)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "configuration_id"
    own = ok(owner.client.get(f"/api/v1/admin/projects/{live['id']}"))["configurations"][0]
    ref = submit_ok(client, {**body, "configuration_id": own["id"]})
    assert str(lead_by_reference(db, ref).configuration_id) == own["id"]


# --- Spam: honeypot and rate limits -----------------------------------------------------------


def test_the_honeypot_answers_like_success_and_stores_nothing(
    client: TestClient, texts: Texts, db: Session
) -> None:
    real = submit(client, enquiry(texts, 1))
    caught = submit(client, enquiry(texts, 2, website="http://spam.example"))
    assert caught.status_code == real.status_code == 201
    assert caught.json().keys() == real.json().keys()
    assert caught.json()["message"] == real.json()["message"]
    assert reference.looks_like_reference(caught.json()["reference"])
    assert count(db, Lead) == 1
    assert len(events(db, "lead.created")) == 1


def test_the_honeypot_still_counts_against_the_rate_limit(client: TestClient, texts: Texts) -> None:
    for n in range(5):
        assert submit(client, enquiry(texts, n, website="bot")).status_code == 201
    assert submit(client, enquiry(texts, 9)).status_code == 429


def test_six_enquiries_from_one_ip_in_ten_minutes_get_429(
    client: TestClient, texts: Texts, db: Session
) -> None:
    for n in range(5):
        assert submit(client, enquiry(texts, n)).status_code == 201
    refused = submit(client, enquiry(texts, 6))
    assert refused.status_code == 429
    assert int(refused.headers["Retry-After"]) > 0
    assert count(db, Lead) == 5


def _edge_client(ip: str) -> TestClient:
    settings = Settings(**{**get_settings().model_dump(), "edge_proxy_key": SecretStr(EDGE_KEY)})
    from empire_api.main import create_app  # noqa: PLC0415 — a second app with the edge key

    client = TestClient(create_app(settings), base_url="https://testserver")
    client.headers.update({"X-Empire-Edge-Key": EDGE_KEY, "X-Empire-Client-IP": ip})
    return client


def test_six_enquiries_from_one_phone_get_429_even_from_new_networks(
    texts: Texts, db: Session
) -> None:
    for n in range(5):
        with _edge_client(f"203.0.113.{n + 1}") as client:
            assert submit(client, enquiry(texts, 1, name=f"Try {n}")).status_code == 201
    with _edge_client("198.51.100.7") as client:
        assert submit(client, enquiry(texts, 1)).status_code == 429
        assert submit(client, enquiry(texts, 2)).status_code == 201  # another phone is fine


def test_rate_limit_keys_hold_no_phone_number_or_ip(
    client: TestClient, texts: Texts, db: Session
) -> None:
    submit_ok(client, enquiry(texts, phone="98765 43210"))
    keys = db.scalars(select(RateLimitBucket.key)).all()
    assert any(k.startswith("lead:phone:") for k in keys)
    assert any(k.startswith("lead:ip:") for k in keys)
    assert not any("9876543210" in k or "testclient" in k for k in keys)


def test_site_visit_and_brochure_share_the_limit(
    client: TestClient, owner: SignedIn, texts: Texts, qr_present: None
) -> None:
    live = published_project(owner)
    tomorrow = (today_ist() + timedelta(days=1)).isoformat()
    for n in range(5):
        body = enquiry(texts, n, project_slug=live["slug"], preferred_date=tomorrow)
        assert (
            submit(client, {**body, "preferred_slot": "morning"}, "site-visits").status_code == 201
        )
    assert (
        submit(
            client, enquiry(texts, 7, project_slug=live["slug"]), "brochure-requests"
        ).status_code
        == 429
    )


# --- Site visits and brochures ----------------------------------------------------------------


def test_a_site_visit_request_creates_a_lead_and_a_visit(
    client: TestClient, owner: SignedIn, texts: Texts, qr_present: None, db: Session
) -> None:
    live = published_project(owner)
    day = today_ist() + timedelta(days=3)
    body = enquiry(
        texts, project_slug=live["slug"], source="site_visit", preferred_date=day.isoformat()
    )
    ref = submit_ok(client, {**body, "preferred_slot": "afternoon"}, "site-visits")
    lead = lead_by_reference(db, ref)
    visit = db.scalar(select(SiteVisit).where(SiteVisit.lead_id == lead.id))
    assert visit is not None
    assert (visit.status, visit.preferred_date, visit.preferred_slot) == (
        "requested",
        day,
        "afternoon",
    )
    assert str(visit.project_id) == live["id"]
    kinds = db.scalars(
        select(LeadActivity.kind).where(LeadActivity.lead_id == lead.id).order_by(LeadActivity.kind)
    ).all()
    assert sorted(kinds) == ["created", "visit_requested"]
    [requested] = events(db, "site_visit.requested")
    assert requested.contains_personal_data is False
    text = str(requested.payload)
    assert "Visitor" not in text and "98765" not in text  # no personal data outside lead.*
    assert events(db, "lead.created")[0].payload["intent"] == "site_visit"


@pytest.mark.parametrize(
    ("offset", "message"), [(-1, intake.VISIT_PAST), (121, intake.VISIT_TOO_FAR)]
)
def test_a_visit_day_must_be_today_to_120_days_ahead(
    client: TestClient, owner: SignedIn, texts: Texts, qr_present: None, offset: int, message: str
) -> None:
    live = published_project(owner)
    day = (today_ist() + timedelta(days=offset)).isoformat()
    body = enquiry(texts, project_slug=live["slug"], preferred_date=day, preferred_slot="morning")
    response = submit(client, body, "site-visits")
    assert response.status_code == 422
    assert response.json()["errors"] == [{"field": "preferred_date", "message": message}]


def test_a_site_visit_needs_a_project(client: TestClient, texts: Texts) -> None:
    body = enquiry(texts, preferred_date=today_ist().isoformat(), preferred_slot="evening")
    response = submit(client, body, "site-visits")
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "project_slug"


def test_a_brochure_request_returns_the_public_pdf_and_a_lead(
    client: TestClient, owner: SignedIn, texts: Texts, qr_present: None, db: Session
) -> None:
    live = published_project(owner)
    body = enquiry(texts, project_slug=live["slug"], source="brochure")
    missing = submit(client, body, "brochure-requests")
    assert missing.status_code == 404
    assert missing.json()["detail"] == intake.NO_BROCHURE
    pdf = document(owner)
    link = ok(attach(owner, pdf["id"], f"project:{live['id']}", "brochure"), 201)
    answer = ok(submit(client, body, "brochure-requests"), 201)
    assert answer["url"] == link["url"]
    assert answer["expires_at"] is None
    assert lead_by_reference(db, answer["reference"]).source == "brochure"
    owner.client.patch(
        f"/api/v1/admin/media-links/{link['link_id']}",
        json={"is_visible": False},
        headers=owner.headers(),
    )
    assert submit(client, body, "brochure-requests").status_code == 404


def test_a_brochure_of_an_unpublished_project_is_not_found(
    client: TestClient, owner: SignedIn, texts: Texts
) -> None:
    draft = create_project(owner, "Not Live")
    response = submit(client, enquiry(texts, project_slug=draft["slug"]), "brochure-requests")
    assert response.status_code == 404


# --- References, audit and logs ---------------------------------------------------------------


def test_a_reference_clash_draws_again(
    client: TestClient,
    texts: Texts,
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
    intake_unlimited: None,
) -> None:
    first = submit_ok(client, enquiry(texts, 1))
    draws = iter([first, "EMP-22222"])
    monkeypatch.setattr("empire_api.leads.creation.new_reference", lambda: next(draws))
    assert submit_ok(client, enquiry(texts, 2)) == "EMP-22222"
    assert count(db, Lead) == 2


def test_no_full_phone_number_reaches_the_logs(
    client: TestClient, texts: Texts, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    with captured_logs(monkeypatch) as entries:
        submit_ok(client, enquiry(texts, phone="98765 43210", email="secret@example.com"))
        submit(client, enquiry(texts, phone="98765 43210", website="bot"))
        submit(client, enquiry(texts, phone="2345678"))
    printed = str(entries)
    assert "lead_received" in printed and "lead_honeypot" in printed
    for secret in ("9876543210", "98765 43210", "secret@example.com", "Visitor 1"):
        assert secret not in printed
    assert count(db, AuditLog) == 0  # visitors' enquiries are on the timeline, not the audit log
