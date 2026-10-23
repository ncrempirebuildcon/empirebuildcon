"""The object-level rule (SECURITY.md §1, leads/access.py): without leads.read_all a staff member
sees only the leads they own, everywhere — inbox, detail, notes, activity, writes, visits,
export, report and dashboard — and anyone else's lead answers 404, never 403."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.leads import export
from empire_api.leads.access import Staff
from empire_api.leads.filters import LeadFilters
from empire_api.timeutil import today_ist
from leads_support import (
    LEADS,
    VISITS,
    assign,
    enquiry,
    lead_by_reference,
    published_project,
    staff_client,
    submit_ok,
)
from projects_support import ok

Texts = dict[str, dict[str, Any]]


@pytest.fixture
def world(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    sales_pair: tuple[SignedIn, SignedIn],
    qr_present: None,
    intake_unlimited: None,
) -> dict[str, Any]:
    """Three visit requests: A owned by Sales 1, B by Sales 2, C in the sales inbox."""
    one, two = sales_pair
    live = published_project(owner)
    day = (today_ist() + timedelta(days=1)).isoformat()
    leads = {}
    for n, name in enumerate(("Lead A", "Lead B", "Lead C")):
        body = enquiry(texts, n, name=name, project_slug=live["slug"], source="site_visit")
        ref = submit_ok(
            client, {**body, "preferred_date": day, "preferred_slot": "morning"}, "site-visits"
        )
        leads[name] = str(lead_by_reference(db, ref).id)
    assign(owner, leads["Lead A"], one.user.id)
    assign(owner, leads["Lead B"], two.user.id)
    visits = {v["lead_name"]: v["id"] for v in ok(owner.client.get(VISITS))}
    return {"one": one, "two": two, "leads": leads, "visits": visits, "project": live}


def names(items: list[dict[str, Any]], key: str = "name") -> list[str]:
    return sorted(item[key] for item in items)


def test_the_inbox_shows_sales_only_their_own_leads(world: dict[str, Any], owner: SignedIn) -> None:
    one = world["one"]
    assert names(ok(one.client.get(LEADS))["items"]) == ["Lead A"]
    assert names(ok(one.client.get(LEADS, params={"owner_id": "unassigned"}))["items"]) == []
    two_id = str(world["two"].user.id)
    assert names(ok(one.client.get(LEADS, params={"owner_id": two_id}))["items"]) == []
    counts = ok(one.client.get(LEADS))["status_counts"]
    assert counts["new"] == 1
    assert names(ok(owner.client.get(LEADS))["items"]) == ["Lead A", "Lead B", "Lead C"]


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("GET", "", None),
        ("PATCH", "", {"status": "contacted"}),
        ("POST", "/read", None),
        ("POST", "/unread", None),
        ("GET", "/notes", None),
        ("POST", "/notes", {"body": "Peeking"}),
        ("GET", "/activity", None),
    ],
)
def test_someone_elses_lead_is_404_like_a_missing_one(
    world: dict[str, Any], method: str, path: str, body: Any
) -> None:
    one = world["one"]
    for lead_id in (world["leads"]["Lead B"], world["leads"]["Lead C"], str(uuid.uuid4())):
        response = one.client.request(
            method, f"{LEADS}/{lead_id}{path}", json=body, headers=one.headers()
        )
        assert response.status_code == 404, (method, path, response.text)
        assert response.json()["detail"] == "No lead with this id."
    own = one.client.request(
        method, f"{LEADS}/{world['leads']['Lead A']}{path}", json=body, headers=one.headers()
    )
    assert own.status_code in (200, 201, 204), own.text


def test_site_visits_show_and_change_only_your_own_leads(world: dict[str, Any]) -> None:
    one = world["one"]
    assert names(ok(one.client.get(VISITS)), "lead_name") == ["Lead A"]
    for lead in ("Lead B", "Lead C"):
        response = one.client.patch(
            f"{VISITS}/{world['visits'][lead]}", json={"notes": "x"}, headers=one.headers()
        )
        assert response.status_code == 404
    lead_b = world["leads"]["Lead B"]
    assert ok(one.client.get(VISITS, params={"lead_id": lead_b})) == []


def test_the_export_applies_the_same_rule(world: dict[str, Any], db: Session) -> None:
    """No role holds leads.export without leads.read_all today, so the rule is tested on the
    service: a sales member's export would hold only their own leads."""
    one = world["one"]
    viewer = Staff(user_id=one.user.id, role="sales")
    assert export.prepare(db, viewer, LeadFilters()) == 1
    file = "".join(export.stream(viewer, LeadFilters()))
    assert "Lead A" in file and "Lead B" not in file and "Lead C" not in file
    assert one.client.get(f"{LEADS}/export.csv", headers=one.headers()).status_code == 403


def test_the_utm_report_counts_only_your_own_leads(
    world: dict[str, Any], app: FastAPI, owner: SignedIn
) -> None:
    def total(signed: SignedIn) -> int:
        return sum(row["leads"] for row in ok(signed.client.get("/api/v1/admin/reports/utm")))

    assert total(world["one"]) == 1
    assert total(owner) == 3
    marketer = staff_client(app, "marketing")
    assert total(marketer) == 3  # counts only; marketing holds leads.report for this


def test_the_dashboard_shows_sales_only_their_own(world: dict[str, Any], owner: SignedIn) -> None:
    mine = ok(world["one"].client.get("/api/v1/admin/dashboard"))
    assert names(mine["latest_leads"]) == ["Lead A"]
    assert names(mine["upcoming_visits"], "lead_name") == ["Lead A"]
    counts = {c["key"]: c["count"] for c in mine["counts"]}
    assert counts["leads.new"] == 1 and counts["visits.week"] in (0, 1)
    assert "leads.unassigned" not in counts
    everyone = ok(owner.client.get("/api/v1/admin/dashboard"))
    assert names(everyone["latest_leads"]) == ["Lead A", "Lead B", "Lead C"]


@pytest.mark.parametrize("role", ["admin", "sales", "marketing", "content_editor"])
def test_only_a_super_admin_can_erase(world: dict[str, Any], app: FastAPI, role: str) -> None:
    signed = staff_client(app, role)
    response = signed.client.delete(f"{LEADS}/{world['leads']['Lead C']}", headers=signed.headers())
    assert response.status_code == 403


@pytest.mark.parametrize(("role", "status"), [("admin", 200), ("sales", 403), ("marketing", 403)])
def test_only_admins_can_export(
    world: dict[str, Any], app: FastAPI, role: str, status: int
) -> None:
    signed = staff_client(app, role)
    response = signed.client.get(f"{LEADS}/export.csv", headers=signed.headers())
    assert response.status_code == status


@pytest.mark.parametrize(
    ("role", "status"), [("sales", 200), ("marketing", 403), ("content_editor", 403)]
)
def test_the_visit_calendar_needs_site_visits_manage(app: FastAPI, role: str, status: int) -> None:
    assert staff_client(app, role).client.get(VISITS).status_code == status


def test_signed_out_callers_get_401(client: TestClient) -> None:
    for path in (LEADS, VISITS, "/api/v1/admin/dashboard", "/api/v1/admin/reports/utm"):
        assert client.get(path).status_code == 401
