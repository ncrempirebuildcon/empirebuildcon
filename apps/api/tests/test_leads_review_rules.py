"""Fixes from the independent review of Phase 4 part 3 (rules findings): IPv6 networks share one
rate limit (5), editing a confirmed visit doesn't move its lead again (6), every dashboard count
matches the list its link opens (7), BHK in half steps (8), and (10, as changed by the review)
"fancy" phone numbers stay accepted."""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Annotated, Any
from urllib.parse import parse_qsl, urlsplit

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import update
from sqlalchemy.orm import Session

from conftest import GOOD_PASSWORD, SignedIn, make_user
from empire_api.config import Settings, get_settings
from empire_api.leads.filters import LeadFilters
from empire_api.leads.models import Lead
from empire_api.leads.phone import PhoneError, normalise_phone
from empire_api.leads.routes import lead_filters
from empire_api.main import create_app
from empire_api.timeutil import today_ist
from leads_support import (
    LEADS,
    VISITS,
    assign,
    enquiry,
    lead_by_reference,
    published_project,
    staff_client,
    submit,
    submit_ok,
)
from projects_support import create_project, ok

Texts = dict[str, dict[str, Any]]
EDGE_KEY = "test-edge-key-0123456789-abcdefghijklmnopqrstuvwxyz"


def edge_client(ip: str) -> TestClient:
    settings = Settings(**{**get_settings().model_dump(), "edge_proxy_key": SecretStr(EDGE_KEY)})
    client = TestClient(create_app(settings), base_url="https://testserver")
    client.headers.update({"X-Empire-Edge-Key": EDGE_KEY, "X-Empire-Client-IP": ip})
    return client


# --- 5. IPv6: one network, one limit -----------------------------------------------------------


@pytest.mark.parametrize(
    ("ip", "key"),
    [
        ("203.0.113.42", "203.0.113.42"),
        ("2001:db8:abcd:12:1:2:3:4", "2001:db8:abcd:12::/64"),
        ("2001:db8:abcd:12:ffff::9", "2001:db8:abcd:12::/64"),
        ("::ffff:198.51.100.7", "198.51.100.7"),
        ("not an ip", "not an ip"),
    ],
)
def test_network_key_keeps_ipv4_and_cuts_ipv6_to_its_64(ip: str, key: str) -> None:
    from empire_api.platform.crypto import network_key  # noqa: PLC0415 — added by the fix

    assert network_key(ip) == key


def test_addresses_in_one_ipv6_64_share_the_intake_limit(texts: Texts) -> None:
    for n in range(5):
        with edge_client(f"2001:db8:1:2::{n + 1:x}") as client:
            assert submit(client, enquiry(texts, n)).status_code == 201
    with edge_client("2001:db8:1:2:ffff:ffff:ffff:ffff") as client:
        assert submit(client, enquiry(texts, 9)).status_code == 429
    with edge_client("2001:db8:1:3::1") as client:  # the next /64 is another network
        assert submit(client, enquiry(texts, 8)).status_code == 201


def test_addresses_in_one_ipv6_64_share_the_sign_in_limits() -> None:
    user = make_user("admin", email="v6@example.com")
    for n in range(5):
        with edge_client(f"2001:db8:5:6::{n + 1:x}") as client:
            r = client.post(
                "/api/v1/auth/login", json={"email": user.email, "password": "nope-nope-nope"}
            )
            assert r.status_code == 401
    with edge_client("2001:db8:5:6:aaaa::1") as client:  # the 6th try from the same /64
        r = client.post("/api/v1/auth/login", json={"email": user.email, "password": GOOD_PASSWORD})
        assert r.status_code == 429
    with edge_client("2001:db8:5:7::1") as client:  # another network may still sign in
        r = client.post("/api/v1/auth/login", json={"email": user.email, "password": GOOD_PASSWORD})
        assert r.status_code == 200


def test_ten_sign_ins_per_ipv6_64_across_accounts() -> None:
    for n in range(10):
        with edge_client(f"2001:db8:9:9::{n + 1:x}") as client:
            r = client.post(
                "/api/v1/auth/login", json={"email": f"x{n}@example.com", "password": "nope-nope"}
            )
            assert r.status_code == 401
    with edge_client("2001:db8:9:9::ff") as client:
        r = client.post(
            "/api/v1/auth/login", json={"email": "y@example.com", "password": "nope-nope"}
        )
        assert r.status_code == 429


# --- 6. Editing a confirmed visit doesn't move the lead again ------------------------------------


def test_editing_a_confirmed_visit_does_not_move_the_lead_forward_again(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, qr_present: None
) -> None:
    live = published_project(owner)
    day = (today_ist() + timedelta(days=1)).isoformat()
    body = enquiry(texts, 3, project_slug=live["slug"], source="site_visit")
    ref = submit_ok(
        client, {**body, "preferred_date": day, "preferred_slot": "morning"}, "site-visits"
    )
    lead_id = str(lead_by_reference(db, ref).id)
    [visit] = ok(owner.client.get(VISITS))
    url = f"{VISITS}/{visit['id']}"
    ok(
        owner.client.patch(
            url,
            json={"status": "confirmed", "confirmed_for": f"{day}T11:00:00+05:30"},
            headers=owner.headers(),
        )
    )
    assert lead_by_reference(db, ref).status == "site_visit"
    ok(
        owner.client.patch(
            f"{LEADS}/{lead_id}", json={"status": "contacted"}, headers=owner.headers()
        )
    )
    ok(owner.client.patch(url, json={"notes": "Bring the brochure"}, headers=owner.headers()))
    ok(
        owner.client.patch(
            url, json={"confirmed_for": f"{day}T12:00:00+05:30"}, headers=owner.headers()
        )
    )
    assert lead_by_reference(db, ref).status == "contacted"
    ok(owner.client.patch(url, json={"status": "requested"}, headers=owner.headers()))
    ok(owner.client.patch(url, json={"status": "confirmed"}, headers=owner.headers()))
    assert lead_by_reference(db, ref).status == "site_visit"  # a new confirm moves it again


# --- 7. Every dashboard count matches the list its link opens ------------------------------------

API_FOR: dict[str, str] = {
    "/admin/leads": LEADS,
    "/admin/site-visits": VISITS,
    "/admin/projects": "/api/v1/admin/projects",
}


def linked_total(signed: SignedIn, link: str) -> int:
    parts = urlsplit(link)
    response = signed.client.get(API_FOR[parts.path], params=parse_qsl(parts.query))
    body = ok(response)
    return len(body) if isinstance(body, list) else int(body["meta"]["total"])


def busy_week(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, one: SignedIn
) -> None:
    live = published_project(owner)
    create_project(owner, "Blocked Draft")  # no RERA number: blocked
    today = today_ist()
    refs = []
    for n, days in enumerate((0, 0, 1, 3, 40)):
        body = enquiry(texts, n, name=f"Buyer {n}", project_slug=live["slug"], source="site_visit")
        day = (today + timedelta(days=days)).isoformat()
        refs.append(
            submit_ok(
                client, {**body, "preferred_date": day, "preferred_slot": "morning"}, "site-visits"
            )
        )
    for n in range(10, 16):
        refs.append(submit_ok(client, enquiry(texts, n)))
    ids = [str(lead_by_reference(db, r).id) for r in refs]
    visits = ok(owner.client.get(VISITS))
    ok(
        owner.client.patch(
            f"{VISITS}/{visits[0]['id']}", json={"status": "cancelled"}, headers=owner.headers()
        )
    )
    ok(
        owner.client.patch(
            f"{LEADS}/{ids[5]}",
            json={"status": "lost", "lost_reason": "not_reachable"},
            headers=owner.headers(),
        )
    )
    ok(owner.client.patch(f"{LEADS}/{ids[6]}", json={"status": "booked"}, headers=owner.headers()))
    ok(owner.client.delete(f"{LEADS}/{ids[7]}", headers=owner.headers()), 204)
    ok(owner.client.post(f"{LEADS}/{ids[8]}/read", headers=owner.headers()), 204)
    db.execute(update(Lead).where(Lead.id == ids[9]).values(is_spam=True))
    db.commit()
    for lead_id in (ids[0], ids[2], ids[10]):
        assign(owner, lead_id, one.user.id)


def test_every_dashboard_count_matches_its_linked_list(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    sales_pair: tuple[SignedIn, SignedIn],
    qr_present: None,
    intake_unlimited: None,
) -> None:
    one, _ = sales_pair
    busy_week(owner, client, texts, db, one)
    for signed in (owner, one):
        counts = ok(signed.client.get("/api/v1/admin/dashboard"))["counts"]
        assert len(counts) >= 7
        for count in counts:
            assert count["count"] == linked_total(signed, count["link"]), count
    keys = {c["key"]: c["count"] for c in ok(owner.client.get("/api/v1/admin/dashboard"))["counts"]}
    assert keys["leads.unassigned"] > 0 and keys["projects.blocked"] == 1
    assert keys["visits.today"] == 1  # the cancelled one doesn't count, here or in the calendar


def test_the_open_and_blocked_filters(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, intake_unlimited: None
) -> None:
    refs = [submit_ok(client, enquiry(texts, n)) for n in range(3)]
    ids = [str(lead_by_reference(db, r).id) for r in refs]
    ok(owner.client.patch(f"{LEADS}/{ids[0]}", json={"status": "booked"}, headers=owner.headers()))
    ok(owner.client.delete(f"{LEADS}/{ids[1]}", headers=owner.headers()), 204)
    still_open = ok(owner.client.get(LEADS, params={"open": "true"}))["items"]
    assert [i["id"] for i in still_open] == [ids[2]]
    closed = ok(owner.client.get(LEADS, params={"open": "false"}))["items"]
    assert sorted(i["id"] for i in closed) == sorted(ids[:2])
    blocked = create_project(owner, "Needs RERA")
    projects = ok(owner.client.get("/api/v1/admin/projects", params={"blocked": "true"}))
    assert [p["id"] for p in projects["items"]] == [blocked["id"]]
    assert (
        ok(owner.client.get("/api/v1/admin/projects", params={"blocked": "false"}))["items"] == []
    )


def test_the_inbox_filters_by_every_utm_report_group(
    owner: SignedIn, client: TestClient, texts: Texts, qr_present: None, intake_unlimited: None
) -> None:
    """Each UTM report row (all four groups) opens an inbox list with the same total; a null
    tag in the row is an empty filter value (no tag)."""
    live = published_project(owner)
    plan = [
        ({"source": "google", "medium": "cpc", "campaign": "a"}, None),
        ({"source": "google", "medium": "email", "campaign": "a"}, live["slug"]),
        ({"source": "facebook", "medium": "cpc", "campaign": "b"}, None),
        ({"source": "google", "medium": "cpc"}, None),  # no campaign
        ({}, live["slug"]),  # no tags at all
    ]
    for n, (utm, slug) in enumerate(plan):
        submit_ok(client, enquiry(texts, n, utm=utm, project_slug=slug))
    rows = ok(owner.client.get("/api/v1/admin/reports/utm"))
    assert len(rows) == 5
    for row in rows:
        params = {f"utm_{k}": row[k] or "" for k in ("source", "medium", "campaign")}
        params["project_id"] = row["project_id"] or "none"
        listed = ok(owner.client.get(LEADS, params=params))
        assert listed["meta"]["total"] == row["leads"], row


def test_marketing_sees_leads_by_source_like_the_utm_report(
    app: FastAPI, client: TestClient, texts: Texts
) -> None:
    for n, source in enumerate(("whatsapp", "whatsapp", "contact_form")):
        submit_ok(client, enquiry(texts, n, source=source))
    marketing = staff_client(app, "marketing")
    view = ok(marketing.client.get("/api/v1/admin/dashboard"))
    assert {s["source"]: s["count"] for s in view["leads_by_source"]} == {
        "whatsapp": 2,
        "contact_form": 1,
    }
    assert view["latest_leads"] == []  # still no personal data for marketing
    editor = staff_client(app, "content_editor")  # no leads.report: nothing
    assert ok(editor.client.get("/api/v1/admin/dashboard"))["leads_by_source"] == []


# --- 8. BHK in half steps -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bhk", "status"),
    [
        (0.04, 422),
        (0.25, 422),
        (3.3, 422),
        (20.5, 422),
        (0, 422),
        (0.5, 201),
        (2.5, 201),
        (20, 201),
    ],
)
def test_bhk_is_whole_or_half_from_half_to_twenty(
    client: TestClient, texts: Texts, db: Session, bhk: float, status: int
) -> None:
    response = submit(client, enquiry(texts, 4, preferred_bhk=bhk))
    assert response.status_code == status, response.text
    if status == 422:
        assert response.json()["errors"][0]["field"] == "preferred_bhk"
        caught = submit(client, enquiry(texts, 5, preferred_bhk=bhk, website="bot"))
        assert caught.status_code == 422  # the honeypot answers exactly like a person


def test_staff_bhk_follows_the_same_rule(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    lead_id = str(lead_by_reference(db, submit_ok(client, enquiry(texts, 1))).id)
    url = f"{LEADS}/{lead_id}"
    assert (
        owner.client.patch(url, json={"preferred_bhk": 0.04}, headers=owner.headers()).status_code
        == 422
    )
    assert (
        ok(owner.client.patch(url, json={"preferred_bhk": 1.5}, headers=owner.headers()))[
            "preferred_bhk"
        ]
        == 1.5
    )


# --- 10. "Fancy" numbers are real numbers -----------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "e164"),
    [
        ("9999999999", "+919999999999"),
        ("9876543210", "+919876543210"),
        ("98765 43210", "+919876543210"),
        ("88888 88888", "+918888888888"),
        ("6789012345", "+916789012345"),
        ("2222222222", "+912222222222"),  # a landline shape that passes the numbering rule
        ("1234567890", "+911234567890"),
    ],
)
def test_fancy_numbers_operators_sell_are_accepted(raw: str, e164: str) -> None:
    """COMPLIANCE/WHY (leads/phone.py): operators sell repeated-digit and run numbers, so they
    can belong to real buyers; only the numbering rule decides."""
    assert normalise_phone(raw).e164 == e164


@pytest.mark.parametrize("raw", ["0987654321", "0000000000", "11111 11111", "0120 000 0000"])
def test_numbers_the_numbering_plan_rules_out_are_still_refused(raw: str) -> None:
    with pytest.raises(PhoneError):
        normalise_phone(raw)


def test_a_fancy_number_can_send_an_enquiry(client: TestClient, texts: Texts, db: Session) -> None:
    ref = submit_ok(client, enquiry(texts, phone="99999 99999"))
    assert lead_by_reference(db, ref).phone_e164 == "+919999999999"


def test_dashboard_link_queries_read_back_into_the_same_filters() -> None:
    """INVARIANT (filters.LeadFilters.query_params): a link's query string, parsed by the inbox
    route, gives back exactly the filters the dashboard counted with."""
    probe = FastAPI()

    @probe.get("/probe", openapi_extra={"x-public": True})
    def echo(filters: Annotated[LeadFilters, Depends(lead_filters)]) -> dict[str, Any]:
        return {key: str(value) for key, value in asdict(filters).items()}

    every = LeadFilters(
        q="Priya",
        status="new",
        project_id="none",
        owner_id="me",
        read=False,
        source="phone",
        utm_source="google",
        utm_medium="cpc",
        utm_campaign="festive",
        date_from=date(2026, 10, 1),
        date_to=date(2026, 10, 7),
        include_spam=True,
        is_spam=False,
        include_sample=False,
        open=True,
    )
    with TestClient(probe) as client:
        for filters in (every, LeadFilters(owner_id="unassigned", open=True), LeadFilters()):
            echoed = client.get("/probe", params=filters.query_params()).json()
            assert echoed == {key: str(value) for key, value in asdict(filters).items()}
