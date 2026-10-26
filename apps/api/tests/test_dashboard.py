"""The CMS dashboard (dashboard/service.py): counts with links to the filtered lists, latest
leads, upcoming visits, tasks, leads by source, and what each role is shown."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.content.models import ConsentText
from empire_api.leads.models import Lead
from empire_api.leads.queries import week_bounds
from empire_api.projects.models import Project
from empire_api.timeutil import today_ist
from leads_support import enquiry, published_project, staff_client, submit_ok
from media_support import photo
from projects_support import create_project, ok

Texts = dict[str, dict[str, Any]]
DASHBOARD = "/api/v1/admin/dashboard"


def board(signed: SignedIn) -> dict[str, Any]:
    return dict(ok(signed.client.get(DASHBOARD)))


def counts(view: dict[str, Any]) -> dict[str, tuple[int, str]]:
    return {c["key"]: (c["count"], c["link"]) for c in view["counts"]}


def tasks(view: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {}
    for task in view["tasks"]:
        found.setdefault(task["key"], []).append(task)
    return found


def visit(client: TestClient, texts: Texts, slug: str, n: int, days: int) -> str:
    body = enquiry(texts, n, name=f"Visit {n}", project_slug=slug, source="site_visit")
    day = (today_ist() + timedelta(days=days)).isoformat()
    return submit_ok(
        client, {**body, "preferred_date": day, "preferred_slot": "morning"}, "site-visits"
    )


def test_counts_link_to_the_filtered_lists(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    qr_present: None,
    intake_unlimited: None,
) -> None:
    live = published_project(owner)
    create_project(owner, "A Draft")
    first = submit_ok(client, enquiry(texts, 1))
    submit_ok(client, enquiry(texts, 2))
    spam = submit_ok(client, enquiry(texts, 3))
    db.execute(update(Lead).where(Lead.reference == spam).values(is_spam=True))
    db.execute(update(Lead).where(Lead.reference == first).values(status="contacted"))
    db.commit()
    visit(client, texts, live["slug"], 4, 0)
    visit(client, texts, live["slug"], 5, 30)
    today = today_ist()
    monday, sunday = week_bounds(today)
    found = counts(board(owner))
    assert found == {
        "leads.new": (3, "/admin/leads?status=new"),
        "leads.unread": (4, "/admin/leads?read=false"),
        "leads.unassigned": (4, "/admin/leads?owner_id=unassigned&open=true"),
        "visits.today": (1, f"/admin/site-visits?from={today}&to={today}&open=true"),
        "visits.week": (1, f"/admin/site-visits?from={monday}&to={sunday}&open=true"),
        "projects.published": (1, "/admin/projects?publish_state=published"),
        "projects.draft": (1, "/admin/projects?publish_state=draft"),
        "projects.blocked": (1, "/admin/projects?publish_state=draft&blocked=true"),
    }


def test_latest_leads_upcoming_visits_and_sources(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    qr_present: None,
    intake_unlimited: None,
) -> None:
    live = published_project(owner)
    refs = [submit_ok(client, enquiry(texts, n, source="whatsapp")) for n in range(6)]
    visit(client, texts, live["slug"], 10, 2)
    past = visit(client, texts, live["slug"], 11, 0)
    db.execute(update(Lead).where(Lead.reference == refs[-1]).values(is_spam=True))
    db.commit()
    view = board(owner)
    latest = [lead["reference"] for lead in view["latest_leads"]]
    assert len(latest) == 5 and refs[-1] not in latest
    assert [v["lead_name"] for v in view["upcoming_visits"]] == ["Visit 11", "Visit 10"]
    assert {s["source"]: s["count"] for s in view["leads_by_source"]} == {
        "whatsapp": 5,
        "site_visit": 2,
    }
    assert past


def test_consent_tasks_say_the_wording_is_still_a_draft(
    owner: SignedIn, texts: Texts, db: Session
) -> None:
    found = tasks(board(owner))
    assert found["consent.lead_form_draft"][0]["label"] == (
        "The enquiry consent text is still a draft"
    )
    assert found["consent.marketing_draft"][0]["link"] == "/admin/settings?tab=consent"
    db.execute(delete(ConsentText))
    db.commit()
    closed = tasks(board(owner))["consent.lead_form_missing"][0]
    assert closed["label"] == "Enquiries are closed"


def test_project_tasks_name_the_missing_qr_hidden_photos_and_samples(
    owner: SignedIn, db: Session
) -> None:
    project = create_project(owner, "Needs Work")
    photo(owner, label="", attach_to=f"project:{project['id']}", role="gallery")
    photo(owner, label="", attach_to=f"project:{project['id']}", role="gallery")
    db.execute(update(Project).where(Project.id == project["id"]).values(is_sample=True))
    db.commit()
    found = tasks(board(owner))
    [qr] = found["project.rera_qr_missing"]
    assert qr["label"] == "Publish blocked: Needs Work"
    assert qr["link"] == f"/admin/projects/{project['id']}?tab=media"
    [photos] = found["project.photos_unlabelled"]
    assert photos["label"] == "Needs Work: 2 photos hidden until labelled"
    assert found["projects.sample_data"][0]["label"] == "1 sample project is still in the system"


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (
            "sales",
            {
                "leads.new",
                "leads.unread",
                "visits.today",
                "visits.week",
                "projects.published",
                "projects.draft",
                "projects.blocked",
            },
        ),
        ("marketing", {"projects.published", "projects.draft", "projects.blocked"}),
        ("content_editor", {"projects.published", "projects.draft", "projects.blocked"}),
    ],
)
def test_each_role_sees_only_what_it_can_open(
    app: FastAPI, texts: Texts, role: str, expected: set[str]
) -> None:
    signed = staff_client(app, role)
    view = board(signed)
    assert set(counts(view)) == expected
    assert not any(key.startswith("consent.") for key in tasks(view))  # needs legal.publish
    if role != "sales":
        assert view["latest_leads"] == [] and view["upcoming_visits"] == []
        assert view["leads_by_source"] == []


def test_an_empty_system_has_honest_zeros(owner: SignedIn) -> None:
    view = board(owner)
    assert all(count == 0 for count, _ in counts(view).values())
    assert view["latest_leads"] == [] and view["upcoming_visits"] == []
    assert [t["key"] for t in view["tasks"]] == ["consent.lead_form_missing"]


def test_the_dashboard_needs_a_session(client: TestClient) -> None:
    assert client.get(DASHBOARD).status_code == 401
