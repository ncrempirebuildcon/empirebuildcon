"""Fixes from the independent review of Phase 4 part 3 (privacy findings):
duplicate links across owners (1), free text left after erasure (2), the export audit's search
text (3), erasing a person's other leads (4) and the export as a cross-site GET (9)."""

from __future__ import annotations

from typing import Any, Final

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.platform.models import OutboxEvent
from leads_support import LEADS, assign, enquiry, lead_by_reference, staff_client, submit_ok
from projects_support import audit_rows, ok

Texts = dict[str, dict[str, Any]]
REPEAT: Final = "A repeat enquiry was linked"


def manual(signed: SignedIn, phone: str, name: str, **extra: Any) -> Any:
    body = {"name": name, "phone": phone, "source": "phone", "consent_note": "Verbal on call"}
    return signed.client.post(LEADS, json={**body, **extra}, headers=signed.headers())


def detail(signed: SignedIn, lead_id: str) -> dict[str, Any]:
    return dict(ok(signed.client.get(f"{LEADS}/{lead_id}")))


def timeline(signed: SignedIn, lead_id: str) -> list[dict[str, Any]]:
    return list(ok(signed.client.get(f"{LEADS}/{lead_id}/activity")))


def database_text(db: Session) -> str:
    db.expire_all()
    tables = db.scalars(text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")).all()
    return "\n".join(
        str(db.scalars(text(f'SELECT t::text FROM "{t}" t')).all())  # noqa: S608 — catalog names
        for t in tables
    )


# --- 1. Duplicate links never reveal another owner's lead ---------------------------------------


def test_a_manual_lead_never_links_to_a_lead_its_creator_cannot_see(
    sales_pair: tuple[SignedIn, SignedIn], db: Session
) -> None:
    one, two = sales_pair
    first = ok(manual(one, "98111 22333", "Priya One"), 201)
    second = ok(manual(two, "98111 22333", "Priya Two"), 201)
    assert second["duplicate_of"] is None and second["duplicate_of_reference"] is None
    assert lead_by_reference(db, second["reference"]).duplicate_of_id is None
    assert detail(one, first["id"])["duplicates"] == []
    assert "duplicate_linked" not in [a["kind"] for a in timeline(one, first["id"])]


def test_a_manual_lead_links_to_its_creators_own_earlier_lead(
    sales_pair: tuple[SignedIn, SignedIn],
) -> None:
    one, _ = sales_pair
    first = ok(manual(one, "98111 22334", "Same Person"), 201)
    second = ok(manual(one, "98111 22334", "Same Person"), 201)
    assert second["duplicate_of"] == first["id"]
    assert second["duplicate_of_reference"] == first["reference"]
    [linked] = [a for a in timeline(one, first["id"]) if a["kind"] == "duplicate_linked"]
    assert linked["data"]["reference"] == second["reference"]
    assert linked["actor"]["id"] == str(one.user.id)


def test_after_reassignment_duplicate_links_are_hidden_from_the_other_owner(
    owner: SignedIn,
    client: TestClient,
    texts: Texts,
    db: Session,
    sales_pair: tuple[SignedIn, SignedIn],
) -> None:
    one, two = sales_pair
    ref1 = submit_ok(client, enquiry(texts, 1))
    lead1 = str(lead_by_reference(db, ref1).id)
    assign(owner, lead1, one.user.id)
    ref2 = submit_ok(client, enquiry(texts, 1, name="Visitor again"))
    lead2 = str(lead_by_reference(db, ref2).id)
    assert lead_by_reference(db, ref2).owner_user_id == one.user.id  # follows the original
    assign(owner, lead2, two.user.id)

    seen = detail(two, lead2)
    assert seen["duplicate_of"] is None and seen["duplicate_of_reference"] is None
    [listed] = ok(two.client.get(LEADS))["items"]
    assert listed["duplicate_of"] is None and listed["duplicate_of_reference"] is None
    created = next(a for a in timeline(two, lead2) if a["kind"] == "created")
    assert created["data"]["duplicate_of"] is None
    assert ref1 not in str(timeline(two, lead2)) and lead1 not in str(timeline(two, lead2))

    original = detail(one, lead1)
    assert original["duplicates"] == []
    [generic] = [a for a in timeline(one, lead1) if a["kind"] == "duplicate_linked"]
    assert generic["data"] == {"summary": REPEAT} and generic["actor"] is None
    assert ref2 not in str(timeline(one, lead1))

    full = detail(owner, lead1)  # leads.read_all sees the link
    assert [d["reference"] for d in full["duplicates"]] == [ref2]
    [linked] = [a for a in timeline(owner, lead1) if a["kind"] == "duplicate_linked"]
    assert linked["data"]["reference"] == ref2


# --- 2. Erasure leaves no free text -------------------------------------------------------------


def lose(signed: SignedIn, lead_id: str, reason: str, note: str | None = None) -> Any:
    body: dict[str, Any] = {"status": "lost", "lost_reason": reason}
    if note is not None:
        body["lost_reason_note"] = note
    return signed.client.patch(f"{LEADS}/{lead_id}", json=body, headers=signed.headers())


def test_lost_reasons_are_codes_with_an_optional_note(owner: SignedIn, db: Session) -> None:
    lead = ok(manual(owner, "98111 40001", "Coded Reason"), 201)
    assert lose(owner, lead["id"], "Bought elsewhere").status_code == 422  # free text refused
    other = lose(owner, lead["id"], "other")
    assert other.status_code == 422
    assert other.json()["errors"][0]["field"] == "lost_reason_note"
    lost = ok(lose(owner, lead["id"], "bought_elsewhere", "Went with a resale flat"))
    assert (lost["lost_reason"], lost["lost_reason_note"]) == (
        "bought_elsewhere",
        "Went with a resale flat",
    )
    back = ok(
        owner.client.patch(
            f"{LEADS}/{lead['id']}", json={"status": "contacted"}, headers=owner.headers()
        )
    )
    assert back["lost_reason"] is None and back["lost_reason_note"] is None
    stray = owner.client.patch(
        f"{LEADS}/{lead['id']}", json={"lost_reason_note": "x"}, headers=owner.headers()
    )
    assert stray.status_code == 422
    audited = next(r for r in audit_rows(db, "lead.updated") if "lost_reason_note" in r.changes)
    assert audited.changes["lost_reason_note"] == [None, "[hidden]"]


def test_erasure_removes_every_free_text_the_person_or_staff_typed(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    ref = submit_ok(
        client,
        enquiry(
            texts,
            9,
            name="Rahul Verma",
            preferred_contact_time="After 7pm, ask for Rahul",
            utm={
                "source": "google",
                "medium": "cpc",
                "campaign": "festive",
                "term": "rahul.verma@example.com",
                "content": "banner-for-rahul",
            },
        ),
    )
    lead_id = str(lead_by_reference(db, ref).id)
    ok(lose(owner, lead_id, "other", "Rahul bought via cousin 98111 00000"))
    ok(lose(owner, lead_id, "other", "Cousin of Rahul again"))
    secrets = (
        "Rahul",
        "98111 00000",
        "rahul.verma@example.com",
        "banner-for-rahul",
        "After 7pm",
        "Cousin of",
    )
    before = database_text(db)
    assert all(secret in before for secret in secrets)
    ok(owner.client.delete(f"{LEADS}/{lead_id}", headers=owner.headers()), 204)
    after = database_text(db)
    for secret in secrets:
        assert secret not in after, secret
    view = detail(owner, lead_id)
    assert view["preferred_contact_time"] is None
    assert view["utm"] == {
        "source": "google",
        "medium": "cpc",
        "campaign": "festive",
        "term": None,
        "content": None,
    }
    assert (view["lost_reason"], view["lost_reason_note"]) == ("other", "[erased]")
    moves = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "lead.status_changed")).all()
    assert moves and all(e.contains_personal_data for e in moves)
    assert len(audit_rows(db, "lead.erased")) == 1  # the erasure itself stays audited


# --- 3. The export audit never keeps the search text ---------------------------------------------


def test_the_export_audit_records_only_that_a_search_was_used(owner: SignedIn, db: Session) -> None:
    for q in ("Priya Sharma", "9876500007"):
        response = owner.client.get(f"{LEADS}/export.csv", params={"q": q}, headers=owner.headers())
        assert response.status_code == 200
    rows = audit_rows(db, "lead.exported")
    assert [r.changes["filters"][1]["q"] for r in rows] == [
        "[search: 12 chars]",
        "[search: 10 chars]",
    ]
    assert "Priya" not in str([r.changes for r in rows])
    assert "9876500007" not in str([r.changes for r in rows])


# --- 4. Erasure covers the person, not one row ----------------------------------------------------


def test_erasing_one_lead_erases_its_whole_duplicate_group(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    first = submit_ok(client, enquiry(texts, 1))
    second = submit_ok(client, enquiry(texts, 1))
    other = submit_ok(client, enquiry(texts, 2))
    target = lead_by_reference(db, second).id  # the duplicate: the group is found both ways
    ok(owner.client.delete(f"{LEADS}/{target}", headers=owner.headers()), 204)
    assert lead_by_reference(db, first).erased_at is not None
    assert lead_by_reference(db, second).erased_at is not None
    assert lead_by_reference(db, other).erased_at is None
    rows = audit_rows(db, "lead.erased")
    assert len(rows) == 2
    assert {r.changes["scope"][1] for r in rows} == {"group"}
    assert {r.changes["leads_in_request"][1] for r in rows} == {2}
    assert {r.changes["requested_for"][1] for r in rows} == {str(target)}


def test_scope_person_also_erases_older_leads_from_the_same_phone(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    old = submit_ok(client, enquiry(texts, 1))
    db.execute(
        text("UPDATE lead SET created_at = now() - interval '30 days' WHERE reference = :r"),
        {"r": old},
    )
    db.commit()
    recent = submit_ok(client, enquiry(texts, 1))
    assert lead_by_reference(db, recent).duplicate_of_id is None  # older than 24 h: no link
    stranger = submit_ok(client, enquiry(texts, 2))
    view = detail(owner, str(lead_by_reference(db, recent).id))
    assert view["same_phone_count"] == 2
    recent_id = lead_by_reference(db, recent).id
    ok(owner.client.delete(f"{LEADS}/{recent_id}", headers=owner.headers()), 204)
    assert lead_by_reference(db, old).erased_at is None  # default scope: the group only
    ok(
        owner.client.delete(
            f"{LEADS}/{lead_by_reference(db, old).id}",
            params={"scope": "person"},
            headers=owner.headers(),
        ),
        204,
    )
    assert lead_by_reference(db, old).erased_at is not None
    assert lead_by_reference(db, stranger).erased_at is None
    person = audit_rows(db, "lead.erased")[-1]
    assert person.changes["scope"] == [None, "person"]


def test_same_phone_count_is_only_for_erasers(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session, app: FastAPI
) -> None:
    ref = submit_ok(client, enquiry(texts, 1))
    lead_id = str(lead_by_reference(db, ref).id)
    assert detail(owner, lead_id)["same_phone_count"] == 1
    admin = staff_client(app, "admin")
    assert detail(admin, lead_id)["same_phone_count"] is None
    assert ok(admin.client.get(LEADS))["items"][0]["same_phone_count"] is None
    ok(owner.client.delete(f"{LEADS}/{lead_id}", headers=owner.headers()), 204)
    assert detail(owner, lead_id)["same_phone_count"] is None  # nothing left to match


def test_an_unknown_erase_scope_is_422(
    owner: SignedIn, client: TestClient, texts: Texts, db: Session
) -> None:
    ref = submit_ok(client, enquiry(texts, 1))
    lead_id = lead_by_reference(db, ref).id
    response = owner.client.delete(
        f"{LEADS}/{lead_id}", params={"scope": "everyone"}, headers=owner.headers()
    )
    assert response.status_code == 422


# --- 9. The export is not a cross-site GET --------------------------------------------------------


def test_the_export_needs_the_session_token_and_a_same_origin_request(owner: SignedIn) -> None:
    url = f"{LEADS}/export.csv"
    assert owner.client.get(url).status_code == 403  # a plain navigation can't send the token
    assert owner.client.get(url, headers={"X-CSRF-Token": "wrong"}).status_code == 403
    assert owner.client.get(url, headers=owner.headers()).status_code == 200
    cross = {**owner.headers(), "Sec-Fetch-Site": "cross-site"}
    assert owner.client.get(url, headers=cross).status_code == 403
    same_site = {**owner.headers(), "Sec-Fetch-Site": "same-site"}
    assert owner.client.get(url, headers=same_site).status_code == 403
    same = {**owner.headers(), "Sec-Fetch-Site": "same-origin"}
    assert owner.client.get(url, headers=same).status_code == 200


def test_the_export_spec_says_it_needs_the_token(app: FastAPI) -> None:
    operation = app.openapi()["paths"][f"{LEADS}/export.csv"]["get"]
    assert operation["security"] == [{"cookieAuth": [], "csrfHeader": []}]
    assert "X-CSRF-Token" in operation["description"]
