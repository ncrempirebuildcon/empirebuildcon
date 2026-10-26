"""CSV export (leads/export.py) and the UTM report (leads/report.py): the documented columns,
formula injection, the cap, the audit trail, and counts with no personal data."""

from __future__ import annotations

import csv
import io
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.leads import export
from empire_api.leads.models import Lead, LeadActivity
from empire_api.timeutil import today_ist
from leads_support import LEADS, enquiry, given, lead_by_reference, published_project, submit_ok
from projects_support import audit_rows, ok

Texts = dict[str, dict[str, Any]]
REPORT = "/api/v1/admin/reports/utm"


def download(signed: SignedIn, **query: Any) -> tuple[Any, list[dict[str, str]]]:
    response = signed.client.get(f"{LEADS}/export.csv", params=query, headers=signed.headers())
    assert response.status_code == 200, response.text
    body = response.content.decode("utf-8")
    assert body.startswith("﻿")  # Excel reads the file as UTF-8 (Hindi names)
    return response, list(csv.DictReader(io.StringIO(body.removeprefix("﻿"))))


@pytest.mark.parametrize(
    ("value", "safe"),
    [
        ('=HYPERLINK("http://x")', '\'=HYPERLINK("http://x")'),
        ("+919876543210", "'+919876543210"),
        ("-2+3", "'-2+3"),
        ("@SUM(A1)", "'@SUM(A1)"),
        ("\tcmd", "'\tcmd"),
        ("\rcmd", "'\rcmd"),
        ("Plain text", "Plain text"),
        ("a=b", "a=b"),
        (42, 42),
        ("", ""),
    ],
)
def test_text_cells_cannot_start_a_formula(value: Any, safe: Any) -> None:
    assert export.safe_cell(value) == safe


def test_the_file_has_the_documented_columns_and_the_lead(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    ref = submit_ok(
        client,
        enquiry(
            texts,
            name="Aman Gupta",
            phone="98765 43210",
            email="aman@example.com",
            utm={"source": "google", "medium": "cpc", "campaign": "festive"},
            click_ids={"gclid": "abc"},
            marketing_consent=given(texts["marketing"]),
        ),
    )
    response, rows = download(owner)
    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    disposition = response.headers["content-disposition"]
    assert disposition.startswith('attachment; filename="empire-leads-')
    assert list(rows[0]) == list(export.HEADER)
    [row] = rows
    assert row["reference"] == ref and row["name"] == "Aman Gupta"
    assert row["phone"] == "'+919876543210"  # the formula guard covers phone numbers too
    assert (row["utm_source"], row["utm_campaign"], row["gclid"]) == ("google", "festive", "abc")
    assert (row["consent_text_version"], row["marketing_consent"]) == ("1", "yes")
    assert row["created_at"].endswith("+05:30")  # IST
    assert response.headers["cache-control"] == "no-store"


def test_a_formula_in_any_text_field_is_neutralised(
    owner: SignedIn, client: TestClient, texts: Texts
) -> None:
    submit_ok(
        client,
        enquiry(texts, name="=cmd|'/C calc'!A0", message="@SUM(1+1)", utm={"campaign": "+evil"}),
    )
    _, [row] = download(owner)
    assert row["name"] == "'=cmd|'/C calc'!A0"
    assert row["message"] == "'@SUM(1+1)"
    assert row["utm_campaign"] == "'+evil"


def test_the_export_uses_the_inbox_filters(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    keep = submit_ok(client, enquiry(texts, 1, source="whatsapp"))
    submit_ok(client, enquiry(texts, 2))
    spam = submit_ok(client, enquiry(texts, 3, source="whatsapp"))
    db.execute(update(Lead).where(Lead.reference == spam).values(is_spam=True))
    db.commit()
    _, rows = download(owner, source="whatsapp")
    assert [r["reference"] for r in rows] == [keep]


def test_every_export_is_audited_with_filters_and_count_and_on_each_timeline(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    refs = [submit_ok(client, enquiry(texts, n)) for n in range(2)]
    download(owner, source="contact_form")
    [row] = audit_rows(db, "lead.exported")
    assert row.actor_user_id == owner.user.id
    assert row.changes == {"filters": [None, {"source": "contact_form"}], "rows": [None, 2]}
    for ref in refs:
        lead = lead_by_reference(db, ref)
        exported = db.scalar(
            select(LeadActivity).where(
                LeadActivity.lead_id == lead.id, LeadActivity.kind == "exported"
            )
        )
        assert exported is not None and exported.data == {"audit_id": row.id, "rows": 2}
        assert exported.actor_user_id == owner.user.id


def test_an_export_above_the_cap_is_refused_not_cut(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    for n in range(3):
        submit_ok(client, enquiry(texts, n))
    monkeypatch.setattr(export, "EXPORT_MAX_ROWS", 2)
    response = owner.client.get(f"{LEADS}/export.csv", headers=owner.headers())
    assert response.status_code == 422
    assert "at most 2" in response.json()["detail"]
    assert audit_rows(db, "lead.exported") == []


def test_an_empty_export_still_has_its_header(owner: SignedIn) -> None:
    _, rows = download(owner)
    assert rows == []


def test_exports_stream_in_batches(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    monkeypatch: pytest.MonkeyPatch,
    intake_unlimited: None,
) -> None:
    for n in range(7):
        submit_ok(client, enquiry(texts, n))
    monkeypatch.setattr(export, "BATCH", 3)
    _, rows = download(owner)
    assert len(rows) == 7 and len({r["reference"] for r in rows}) == 7


# --- UTM report ---------------------------------------------------------------------------------


def campaign_leads(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> dict[str, Any]:
    live = published_project(owner, "Report Project")
    plan = [
        (1, {"source": "google", "medium": "cpc", "campaign": "a"}, live["slug"]),
        (2, {"source": "google", "medium": "cpc", "campaign": "a"}, live["slug"]),
        (3, {"source": "facebook", "medium": "paid", "campaign": "b"}, None),
        (4, {}, None),
    ]
    refs = [
        submit_ok(client, enquiry(texts, n, name=f"Person {n}", utm=utm, project_slug=slug))
        for n, utm, slug in plan
    ]
    booked = lead_by_reference(db, refs[0])
    ok(
        owner.client.patch(
            f"{LEADS}/{booked.id}", json={"status": "booked"}, headers=owner.headers()
        )
    )
    return {"project": live, "refs": refs}


def test_the_report_counts_by_all_four_tags_with_no_personal_data(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, qr_present: None
) -> None:
    made = campaign_leads(owner, client, texts, db)
    rows = ok(owner.client.get(REPORT))
    assert rows[0] == {
        "source": "google",
        "medium": "cpc",
        "campaign": "a",
        "project": "Report Project",
        "project_id": made["project"]["id"],
        "leads": 2,
        "site_visits": 0,
        "booked": 1,
    }
    assert sum(r["leads"] for r in rows) == 4
    assert {r["source"] for r in rows} == {"google", "facebook", None}
    printed = str(rows)
    for secret in ("Person", "98765", "@", "EMP-"):
        assert secret not in printed


@pytest.mark.parametrize(
    ("group", "expected"),
    [
        ("source", {"google": 2, "facebook": 1, None: 1}),
        ("medium", {"cpc": 2, "paid": 1, None: 1}),
        ("campaign", {"a": 2, "b": 1, None: 1}),
        ("project", {"Report Project": 2, None: 2}),
    ],
)
def test_the_report_groups_by_one_tag(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    qr_present: None,
    group: str,
    expected: dict[Any, int],
) -> None:
    campaign_leads(owner, client, texts, db)
    rows = ok(owner.client.get(REPORT, params={"group_by": group}))
    assert {r[group]: r["leads"] for r in rows} == expected
    others = {"source", "medium", "campaign", "project"} - {group}
    assert all(r[key] is None for r in rows for key in others)


def test_the_report_has_a_date_range_and_ignores_spam(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    old, new, spam = (submit_ok(client, enquiry(texts, n)) for n in range(3))
    db.execute(
        text("UPDATE lead SET created_at = '2026-09-01 06:00:00+00' WHERE reference = :r"),
        {"r": old},
    )
    db.execute(update(Lead).where(Lead.reference == spam).values(is_spam=True))
    db.commit()

    def total(**query: str) -> int:
        return sum(r["leads"] for r in ok(owner.client.get(REPORT, params=query)))

    assert total() == 2
    assert total(**{"from": "2026-09-01", "to": "2026-09-01"}) == 1
    assert total(**{"from": "2026-09-02"}) == 1
    assert new


def test_site_visits_count_leads_with_a_visit(
    owner: SignedIn, client: TestClient, texts: Texts, qr_present: None
) -> None:
    live = published_project(owner)
    body = enquiry(texts, 1, project_slug=live["slug"], utm={"source": "google"})
    day = today_ist().isoformat()
    submit_ok(client, {**body, "preferred_date": day, "preferred_slot": "morning"}, "site-visits")
    submit_ok(client, enquiry(texts, 2, project_slug=live["slug"], utm={"source": "google"}))
    [row] = ok(owner.client.get(REPORT, params={"group_by": "source"}))
    assert (row["leads"], row["site_visits"]) == (2, 1)
