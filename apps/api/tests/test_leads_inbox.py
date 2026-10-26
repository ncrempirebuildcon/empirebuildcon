"""Staff work on leads (leads/service.py): the inbox and its filters, the pipeline rules,
assignment, read/unread, notes, the timeline, manual leads, the people a lead can go to, and
projects with leads."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user
from empire_api.leads.models import Lead, LeadActivity, LeadConsent
from empire_api.leads.service import (
    LOST_NEEDS_REASON,
    NEEDS_ASSIGN,
    OWNER_INVALID,
    REASON_ONLY_LOST,
)
from empire_api.platform.models import AuditLog
from empire_api.projects.service import HAS_LEADS
from leads_support import (
    LEADS,
    lead_by_reference,
    staff_client,
)
from projects_support import audit_rows, create_project, events, ok, patch_project

Texts = dict[str, dict[str, Any]]


def manual(signed: SignedIn, n: int = 1, **fields: Any) -> Any:
    body = {
        "name": f"Walk-in {n}",
        "phone": f"98111 {n:05d}",
        "source": "phone",
        "consent_note": "Verbal on phone call",
        **fields,
    }
    return signed.client.post(LEADS, json=body, headers=signed.headers())


def new_lead(signed: SignedIn, n: int = 1, **fields: Any) -> dict[str, Any]:
    return dict(ok(manual(signed, n, **fields), 201))


def patch(signed: SignedIn, lead_id: str, **body: Any) -> Any:
    return signed.client.patch(f"{LEADS}/{lead_id}", json=body, headers=signed.headers())


def inbox(signed: SignedIn, **query: Any) -> dict[str, Any]:
    return dict(ok(signed.client.get(LEADS, params=query)))


def refs(page: dict[str, Any]) -> list[str]:
    return [item["name"] for item in page["items"]]


def activity_kinds(db: Session, lead_id: str) -> list[str]:
    db.expire_all()
    return list(
        db.scalars(
            select(LeadActivity.kind)
            .where(LeadActivity.lead_id == lead_id)
            .order_by(LeadActivity.created_at, LeadActivity.id)
        )
    )


# --- Inbox and filters -------------------------------------------------------------------------


def test_the_inbox_is_newest_first_and_paged(owner: SignedIn, db: Session) -> None:
    for n in range(3):
        new_lead(owner, n)
    first = inbox(owner, per_page=2)
    assert refs(first) == ["Walk-in 2", "Walk-in 1"]
    assert first["meta"] == {"page": 1, "per_page": 2, "total": 3, "pages": 2}
    assert refs(inbox(owner, per_page=2, page=2)) == ["Walk-in 0"]
    assert first["status_counts"] == {
        "new": 3,
        "contacted": 0,
        "site_visit": 0,
        "negotiation": 0,
        "booked": 0,
        "lost": 0,
    }


def test_search_finds_name_reference_and_last_digits(owner: SignedIn) -> None:
    a = new_lead(owner, 1, name="Rohit Verma", phone="98765 43210")
    new_lead(owner, 2, name="Kavya Iyer", phone="99999 11111")
    assert refs(inbox(owner, q="rohit")) == ["Rohit Verma"]
    assert refs(inbox(owner, q=a["reference"].lower())) == ["Rohit Verma"]
    assert refs(inbox(owner, q="3210")) == ["Rohit Verma"]
    assert refs(inbox(owner, q="43 210")) == ["Rohit Verma"]
    assert refs(inbox(owner, q="98765")) == []  # digits match the END of the number
    assert refs(inbox(owner, q="100%_")) == []  # LIKE wildcards are literal


def test_filters_by_stage_project_owner_read_and_source(
    owner: SignedIn, app: FastAPI, db: Session
) -> None:
    project = create_project(owner, "Filter Project")
    sales = make_user("sales", email="f@example.com", name="Sales F")
    one = new_lead(owner, 1, project_id=project["id"], source="manual")
    two = new_lead(owner, 2, owner_user_id=str(sales.id))
    three = new_lead(owner, 3, owner_user_id=None)
    ok(patch(owner, two["id"], status="contacted"))
    ok(owner.client.post(f"{LEADS}/{three['id']}/unread", headers=owner.headers()), 204)
    assert refs(inbox(owner, status="contacted")) == ["Walk-in 2"]
    assert refs(inbox(owner, project_id=project["id"])) == ["Walk-in 1"]
    assert refs(inbox(owner, project_id="none")) == ["Walk-in 3", "Walk-in 2"]
    assert refs(inbox(owner, owner_id="unassigned")) == ["Walk-in 3"]
    assert refs(inbox(owner, owner_id=str(sales.id))) == ["Walk-in 2"]
    assert refs(inbox(owner, owner_id="me")) == ["Walk-in 1"]
    assert refs(inbox(owner, read="false")) == ["Walk-in 3"]
    assert refs(inbox(owner, source="manual")) == ["Walk-in 1"]
    counts = inbox(owner, status="contacted")["status_counts"]
    assert (counts["new"], counts["contacted"]) == (2, 1)  # counts ignore `status`
    assert one["project"]["name"] == "Filter Project"


@pytest.mark.parametrize(("name", "value"), [("owner_id", "someone"), ("project_id", "x")])
def test_bad_filter_ids_are_422(owner: SignedIn, name: str, value: str) -> None:
    response = owner.client.get(LEADS, params={name: value})
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == name


def test_dates_are_ist_days_both_included(owner: SignedIn, db: Session) -> None:
    lead = new_lead(owner, 1)
    # 23:30 IST on 1 Oct = 18:00 UTC on 1 Oct; the IST day is 1 Oct.
    db.execute(
        text("UPDATE lead SET created_at = '2026-10-01 18:00:00+00' WHERE id = :id"),
        {"id": lead["id"]},
    )
    db.commit()
    assert refs(inbox(owner, **{"from": "2026-10-01", "to": "2026-10-01"})) == ["Walk-in 1"]
    assert refs(inbox(owner, **{"from": "2026-10-02"})) == []
    assert refs(inbox(owner, to="2026-09-30")) == []


def test_spam_is_hidden_unless_asked_for(owner: SignedIn) -> None:
    keep, spam = new_lead(owner, 1), new_lead(owner, 2)
    ok(patch(owner, spam["id"], is_spam=True))
    assert refs(inbox(owner)) == ["Walk-in 1"]
    assert refs(inbox(owner, include_spam="true")) == ["Walk-in 2", "Walk-in 1"]
    assert refs(inbox(owner, is_spam="true")) == ["Walk-in 2"]
    assert refs(inbox(owner, is_spam="false", include_spam="true")) == ["Walk-in 1"]
    assert keep["is_spam"] is False


def test_sample_leads_can_be_left_out(owner: SignedIn, db: Session) -> None:
    sample = new_lead(owner, 1)
    new_lead(owner, 2)
    db.execute(update(Lead).where(Lead.id == sample["id"]).values(is_sample=True))
    db.commit()
    assert len(inbox(owner)["items"]) == 2
    assert refs(inbox(owner, include_sample="false")) == ["Walk-in 2"]
    assert inbox(owner)["items"][1]["is_sample"] is True


# --- Pipeline -----------------------------------------------------------------------------------


def test_lost_needs_a_reason_and_leaving_lost_clears_it(owner: SignedIn, db: Session) -> None:
    lead = new_lead(owner)
    refused = patch(owner, lead["id"], status="lost")
    assert refused.status_code == 422
    assert refused.json()["errors"] == [{"field": "lost_reason", "message": LOST_NEEDS_REASON}]
    free_text = patch(owner, lead["id"], status="lost", lost_reason="Bought elsewhere")
    assert free_text.status_code == 422  # a code from the list (vocab.LOST_REASON_LABELS)
    lost = ok(patch(owner, lead["id"], status="lost", lost_reason="bought_elsewhere"))
    assert (lost["status"], lost["lost_reason"]) == ("lost", "bought_elsewhere")
    reason_only = ok(patch(owner, lead["id"], lost_reason="budget"))
    assert reason_only["lost_reason"] == "budget"
    back = ok(patch(owner, lead["id"], status="contacted"))
    assert (back["status"], back["lost_reason"]) == ("contacted", None)
    stray = patch(owner, lead["id"], lost_reason="location")
    assert stray.json()["errors"] == [{"field": "lost_reason", "message": REASON_ONLY_LOST}]


def test_every_stage_move_is_recorded_with_its_direction(owner: SignedIn, db: Session) -> None:
    lead = new_lead(owner)
    for stage in ("contacted", "site_visit", "negotiation", "contacted"):
        ok(patch(owner, lead["id"], status=stage))
    moves = db.scalars(
        select(LeadActivity.data)
        .where(LeadActivity.lead_id == lead["id"], LeadActivity.kind == "status_changed")
        .order_by(LeadActivity.created_at)
    ).all()
    assert [(m["from"], m["to"], m["direction"]) for m in moves] == [
        ("new", "contacted", "forward"),
        ("contacted", "site_visit", "forward"),
        ("site_visit", "negotiation", "forward"),
        ("negotiation", "contacted", "backward"),
    ]
    announced = [(e.payload["from"], e.payload["to"]) for e in events(db, "lead.status_changed")]
    assert announced[-1] == ("negotiation", "contacted") and len(announced) == 4
    audited = audit_rows(db, "lead.updated")
    assert audited[-1].changes["status"] == ["negotiation", "contacted"]


def test_nothing_changed_writes_nothing(owner: SignedIn, db: Session) -> None:
    lead = new_lead(owner)
    before = len(audit_rows(db, "lead.updated"))
    ok(patch(owner, lead["id"], status="new"))
    assert len(audit_rows(db, "lead.updated")) == before
    assert activity_kinds(db, lead["id"]) == ["created"]


@pytest.mark.parametrize("body", [{"status": None}, {"is_spam": None}, {"colour": "red"}])
def test_bad_updates_are_422(owner: SignedIn, body: dict[str, Any]) -> None:
    lead = new_lead(owner)
    assert patch(owner, lead["id"], **body).status_code == 422


def test_details_spam_and_project_changes_are_on_the_timeline(owner: SignedIn, db: Session) -> None:
    project = create_project(owner, "Moved To")
    lead = new_lead(owner)
    ok(patch(owner, lead["id"], email="new@example.com", budget_max_inr=9_000_000))
    ok(patch(owner, lead["id"], is_spam=True))
    moved = ok(patch(owner, lead["id"], project_id=project["id"]))
    assert moved["project"]["id"] == project["id"]
    assert activity_kinds(db, lead["id"]) == [
        "created",
        "details_changed",
        "spam_marked",
        "details_changed",
    ]
    unknown = patch(owner, lead["id"], project_id="01a16862-56ac-74cc-b260-0dfe5c63b4c5")
    assert unknown.status_code == 422


def test_audit_diffs_never_hold_the_email_or_phone(owner: SignedIn, db: Session) -> None:
    lead = new_lead(owner, phone="98765 43210", email="old@example.com")
    ok(patch(owner, lead["id"], email="new@example.com"))
    every = str([row.changes for row in db.scalars(select(AuditLog))])
    for secret in ("old@example.com", "new@example.com", "9876543210", "Walk-in"):
        assert secret not in every
    [updated] = audit_rows(db, "lead.updated")
    assert updated.changes == {"email": ["[hidden]", "[hidden]"]}
    [created] = audit_rows(db, "lead.created")
    assert created.changes["phone"] == [None, "+91 98xxxxxx10"]


# --- Assignment ---------------------------------------------------------------------------------


def test_changing_the_owner_needs_leads_assign(
    owner: SignedIn, sales_pair: tuple[SignedIn, SignedIn], db: Session
) -> None:
    one, two = sales_pair
    lead = new_lead(owner, owner_user_id=str(one.user.id))
    refused = patch(one, lead["id"], owner_user_id=str(two.user.id))
    assert refused.status_code == 403
    assert refused.json()["detail"] == NEEDS_ASSIGN
    moved = ok(patch(owner, lead["id"], owner_user_id=str(two.user.id)))
    assert moved["owner"] == {"id": str(two.user.id), "name": "Sales 2"}
    assert moved["assigned_at"] is not None
    moves = [
        (e.payload["from_user_id"], e.payload["to_user_id"]) for e in events(db, "lead.assigned")
    ]
    assert moves == [(None, str(one.user.id)), (str(one.user.id), str(two.user.id))]
    assert "assigned" in activity_kinds(db, lead["id"])
    unassigned = ok(patch(owner, lead["id"], owner_user_id=None))
    assert unassigned["owner"] is None and unassigned["assigned_at"] is None


def test_a_sales_user_may_send_the_same_owner_back(
    owner: SignedIn, sales_pair: tuple[SignedIn, SignedIn]
) -> None:
    one, _ = sales_pair
    lead = new_lead(owner, owner_user_id=str(one.user.id))
    assert ok(patch(one, lead["id"], owner_user_id=str(one.user.id), status="contacted"))


def test_the_new_owner_must_be_someone_who_can_open_leads(owner: SignedIn) -> None:
    lead = new_lead(owner)
    marketer = make_user("marketing", email="m@example.com")
    gone = make_user("sales", email="gone@example.com", is_active=False)
    for person in (marketer, gone):
        response = patch(owner, lead["id"], owner_user_id=str(person.id))
        assert response.json()["errors"] == [{"field": "owner_user_id", "message": OWNER_INVALID}]


def test_lead_owners_lists_people_who_can_open_leads(owner: SignedIn) -> None:
    make_user("sales", email="s@example.com", name="Sam Sales")
    make_user("admin", email="a@example.com", name="Ada Admin")
    make_user("marketing", email="m@example.com", name="Mo Marketing")
    make_user("sales", email="x@example.com", name="Xavier Gone", is_active=False)
    names = [p["name"] for p in ok(owner.client.get("/api/v1/admin/lead-owners"))]
    assert names == ["Ada Admin", "Sam Sales", "Test Person"]


# --- Read, notes, timeline ----------------------------------------------------------------------


def test_read_and_unread(owner: SignedIn, db: Session) -> None:
    lead = ok(manual(owner), 201)
    db.execute(update(Lead).where(Lead.id == lead["id"]).values(read_at=None))
    db.commit()
    for _ in range(2):
        ok(owner.client.post(f"{LEADS}/{lead['id']}/read", headers=owner.headers()), 204)
    assert ok(owner.client.get(f"{LEADS}/{lead['id']}"))["read_at"] is not None
    ok(owner.client.post(f"{LEADS}/{lead['id']}/unread", headers=owner.headers()), 204)
    assert ok(owner.client.get(f"{LEADS}/{lead['id']}"))["read_at"] is None
    assert activity_kinds(db, lead["id"]) == ["created", "read", "unread"]
    no_csrf = owner.client.post(f"{LEADS}/{lead['id']}/read")
    assert no_csrf.status_code == 403


def test_reading_is_not_work_on_the_lead(owner: SignedIn, db: Session) -> None:
    lead = new_lead(owner)
    before = lead_by_reference(db, lead["reference"]).last_activity_at
    ok(owner.client.post(f"{LEADS}/{lead['id']}/unread", headers=owner.headers()), 204)
    ok(owner.client.post(f"{LEADS}/{lead['id']}/read", headers=owner.headers()), 204)
    assert lead_by_reference(db, lead["reference"]).last_activity_at == before
    ok(
        owner.client.post(
            f"{LEADS}/{lead['id']}/notes", json={"body": "Called"}, headers=owner.headers()
        ),
        201,
    )
    assert lead_by_reference(db, lead["reference"]).last_activity_at > before


def test_notes_newest_first_with_author_and_audit_without_text(
    owner: SignedIn, db: Session
) -> None:
    lead = new_lead(owner)
    for body in ("First call", "Sent the cost sheet"):
        note = ok(
            owner.client.post(
                f"{LEADS}/{lead['id']}/notes", json={"body": body}, headers=owner.headers()
            ),
            201,
        )
        assert note["author"]["id"] == str(owner.user.id)
    notes = ok(owner.client.get(f"{LEADS}/{lead['id']}/notes"))
    assert [n["body"] for n in notes] == ["Sent the cost sheet", "First call"]
    audited = audit_rows(db, "lead.note_added")
    assert len(audited) == 2 and "cost sheet" not in str(audited[-1].changes)
    empty = owner.client.post(
        f"{LEADS}/{lead['id']}/notes", json={"body": ""}, headers=owner.headers()
    )
    assert empty.status_code == 422


def test_the_timeline_is_newest_first_and_names_the_actor(owner: SignedIn) -> None:
    lead = new_lead(owner)
    ok(patch(owner, lead["id"], status="contacted"))
    timeline = ok(owner.client.get(f"{LEADS}/{lead['id']}/activity"))
    assert [t["kind"] for t in timeline] == ["status_changed", "created"]
    assert timeline[0]["actor"]["name"] == "Test Person"
    assert timeline[1]["data"]["intent"] == "manual"


# --- Manual leads -------------------------------------------------------------------------------


def test_a_manual_lead_records_how_consent_was_given(owner: SignedIn, db: Session) -> None:
    lead = new_lead(owner, consent_note="Verbal on phone call, 23 Oct")
    assert lead["consent"]["consent_note"] == "Verbal on phone call, 23 Oct"
    assert lead["consent"]["text_version"] is None and lead["marketing_consent"] is None
    assert lead["owner"]["id"] == str(owner.user.id)
    assert lead["read_at"] is not None and lead["page_url"] is None
    rows = db.scalars(select(LeadConsent).where(LeadConsent.lead_id == lead["id"])).all()
    assert [(r.kind, r.consent_text_id) for r in rows] == [("lead_form", None)]
    [created] = events(db, "lead.created")
    assert created.payload["alert"] is False and created.payload["intent"] == "manual"


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"consent_note": None}, "consent_note"),
        ({"consent_note": "ok"}, "consent_note"),
        ({"phone": "12345"}, "phone"),
        ({"project_id": "01a16862-56ac-74cc-b260-0dfe5c63b4c5"}, "project_id"),
        ({"extra": 1}, "extra"),
    ],
)
def test_manual_leads_are_checked(owner: SignedIn, change: dict[str, Any], field: str) -> None:
    body = {
        "name": "Checked",
        "phone": "98111 00001",
        "source": "phone",
        "consent_note": "Verbal on phone call",
        **change,
    }
    body = {key: value for key, value in body.items() if value is not None}
    response = owner.client.post(LEADS, json=body, headers=owner.headers())
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


def test_only_assigners_may_give_a_manual_lead_to_someone_else(
    owner: SignedIn, sales_pair: tuple[SignedIn, SignedIn], db: Session
) -> None:
    one, two = sales_pair
    mine = new_lead(one, 1)
    assert mine["owner"]["id"] == str(one.user.id)
    assert manual(one, 2, owner_user_id=str(two.user.id)).status_code == 403
    assert manual(one, 3, owner_user_id=None).status_code == 403
    given = new_lead(owner, 4, owner_user_id=str(two.user.id))
    assert given["owner"]["id"] == str(two.user.id)
    inbox_lead = new_lead(owner, 5, owner_user_id=None)
    assert inbox_lead["owner"] is None
    [assigned] = events(db, "lead.assigned")
    assert assigned.payload["to_user_id"] == str(two.user.id)


def test_marketing_cannot_open_the_inbox(app: FastAPI) -> None:
    marketer = staff_client(app, "marketing")
    assert marketer.client.get(LEADS).status_code == 403
    assert manual(marketer).status_code == 403


# --- Projects with leads ------------------------------------------------------------------------


def test_a_project_with_leads_is_archived_not_deleted(owner: SignedIn) -> None:
    project = create_project(owner, "Has Leads")
    lead = new_lead(owner, project_id=project["id"])
    refused = owner.client.delete(
        f"/api/v1/admin/projects/{project['id']}", headers=owner.headers()
    )
    assert refused.status_code == 409
    assert refused.json()["detail"] == HAS_LEADS
    ok(patch_project(owner, project["id"], {"publish_state": "archived"}))
    assert ok(owner.client.get(f"{LEADS}/{lead['id']}"))["project"]["id"] == project["id"]
    empty = create_project(owner, "No Leads")
    assert (
        owner.client.delete(
            f"/api/v1/admin/projects/{empty['id']}", headers=owner.headers()
        ).status_code
        == 204
    )


def test_the_database_refuses_to_delete_a_project_with_leads(owner: SignedIn, db: Session) -> None:
    """The foreign key is RESTRICT: a backstop behind the 409 (leads/models.py)."""
    project = create_project(owner, "Backstop")
    new_lead(owner, project_id=project["id"])
    with pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM project WHERE id = :id"), {"id": project["id"]})
        db.commit()
    db.rollback()
