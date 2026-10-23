"""Who gets a new lead (leads/routing.py, D-016) and the 24-hour duplicate rule
(leads/creation.py): single, round robin (fair under concurrency) and manual; duplicates linked to
the original, owned by its owner, and not alerted again."""

from __future__ import annotations

import concurrent.futures
import uuid
from collections import Counter
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user
from empire_api.db import get_sessionmaker
from empire_api.leads import intake, routing
from empire_api.leads.models import Lead, LeadActivity
from empire_api.leads.schemas_public import LeadCreate
from empire_api.site_settings.models import Setting
from empire_api.users.models import User
from leads_support import LEADS, enquiry, lead_by_reference, published_project, submit_ok
from projects_support import events, ok

Texts = dict[str, dict[str, Any]]


def set_routing(db: Session, **value: Any) -> None:
    value.setdefault("round_robin_user_ids", [])
    row = db.get(Setting, "lead_routing")
    if row is None:
        db.add(Setting(key="lead_routing", value=value))
    else:
        row.value = value
    db.commit()


def owners_of(db: Session, refs: list[str]) -> list[uuid.UUID | None]:
    return [lead_by_reference(db, ref).owner_user_id for ref in refs]


# --- Assignment ---------------------------------------------------------------------------------


def test_by_default_new_leads_wait_in_the_sales_inbox(
    client: TestClient, texts: Texts, db: Session
) -> None:
    make_user("sales")
    lead = lead_by_reference(db, submit_ok(client, enquiry(texts)))
    assert lead.owner_user_id is None and lead.assigned_at is None


def test_single_mode_gives_every_lead_to_the_named_person(
    client: TestClient, texts: Texts, db: Session, intake_unlimited: None
) -> None:
    person = make_user("sales", email="one@example.com")
    set_routing(db, mode="single", single_owner_user_id=str(person.id))
    lead = lead_by_reference(db, submit_ok(client, enquiry(texts, 1)))
    assert lead.owner_user_id == person.id and lead.assigned_at is not None
    assert events(db, "lead.created")[0].payload["owner_user_id"] == str(person.id)
    db.execute(update(User).where(User.id == person.id).values(is_active=False))
    db.commit()
    assert lead_by_reference(db, submit_ok(client, enquiry(texts, 2))).owner_user_id is None


def test_single_mode_ignores_someone_who_cannot_open_leads(
    client: TestClient, texts: Texts, db: Session
) -> None:
    marketer = make_user("marketing")
    set_routing(db, mode="single", single_owner_user_id=str(marketer.id))
    assert lead_by_reference(db, submit_ok(client, enquiry(texts))).owner_user_id is None


def test_manual_mode_leaves_leads_unassigned(client: TestClient, texts: Texts, db: Session) -> None:
    person = make_user("sales")
    set_routing(db, mode="manual", single_owner_user_id=str(person.id))
    assert lead_by_reference(db, submit_ok(client, enquiry(texts))).owner_user_id is None


def test_round_robin_takes_turns_in_order_and_skips_inactive_people(
    client: TestClient, texts: Texts, db: Session, intake_unlimited: None
) -> None:
    a, b, c = (make_user("sales", email=f"{n}@example.com") for n in "abc")
    set_routing(db, mode="round_robin", round_robin_user_ids=[str(u.id) for u in (a, b, c)])
    refs = [submit_ok(client, enquiry(texts, n)) for n in range(4)]
    assert owners_of(db, refs) == [a.id, b.id, c.id, a.id]
    db.execute(update(User).where(User.id == b.id).values(is_active=False))
    db.commit()
    later = [submit_ok(client, enquiry(texts, n)) for n in range(10, 13)]
    assert owners_of(db, later) == [c.id, a.id, c.id]


def test_round_robin_with_no_list_uses_every_active_sales_user(
    client: TestClient, texts: Texts, db: Session, intake_unlimited: None
) -> None:
    first = make_user("sales", email="first@example.com")
    second = make_user("sales", email="second@example.com")
    make_user("admin", email="admin@example.com")
    set_routing(db, mode="round_robin")
    refs = [submit_ok(client, enquiry(texts, n)) for n in range(3)]
    assert owners_of(db, refs) == [first.id, second.id, first.id]


def test_round_robin_is_fair_under_concurrency(
    texts: Texts, db: Session, intake_unlimited: None
) -> None:
    """Twelve enquiries at the same moment, three people: exactly four each (routing.py)."""
    people = [make_user("sales", email=f"rr{n}@example.com") for n in range(3)]
    set_routing(db, mode="round_robin", round_robin_user_ids=[str(p.id) for p in people])

    def one(n: int) -> str:
        body = LeadCreate.model_validate(enquiry(texts, 100 + n))
        with get_sessionmaker()() as session:
            return intake.submit(session, body, f"10.0.0.{n}", "enquiry").reference

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        refs = list(pool.map(one, range(12)))
    tally = Counter(owners_of(db, refs))
    assert tally == {p.id: 4 for p in people}
    db.expire_all()
    turn = db.get(Setting, routing.ROUND_ROBIN_TURN)
    assert turn is not None and turn.value["last_user_id"] in {str(p.id) for p in people}


# --- Duplicates ---------------------------------------------------------------------------------


def test_same_phone_and_project_within_24_hours_is_linked_and_not_alerted_again(
    client: TestClient, owner: SignedIn, texts: Texts, db: Session, qr_present: None
) -> None:
    live = published_project(owner)
    body = enquiry(texts, project_slug=live["slug"], source="project_form")
    first = submit_ok(client, body)
    second = submit_ok(client, {**body, "name": "Same Person", "message": "Still keen"})
    original, duplicate = lead_by_reference(db, first), lead_by_reference(db, second)
    assert duplicate.duplicate_of_id == original.id
    assert duplicate.message == "Still keen"  # nothing the visitor typed is lost
    created = {e.payload["reference"]: e.payload for e in events(db, "lead.created")}
    assert created[first]["alert"] is True
    assert created[second]["alert"] is False
    assert created[second]["duplicate_of"] == str(original.id)
    linked = db.scalar(
        select(LeadActivity).where(
            LeadActivity.lead_id == original.id, LeadActivity.kind == "duplicate_linked"
        )
    )
    assert linked is not None and linked.data["reference"] == second
    view = ok(owner.client.get(f"{LEADS}/{original.id}"))
    assert [d["reference"] for d in view["duplicates"]] == [second]
    later = ok(owner.client.get(f"{LEADS}/{duplicate.id}"))
    assert later["duplicate_of"] == str(original.id)
    assert later["duplicate_of_reference"] == first


def test_general_enquiries_from_one_phone_are_duplicates_too(
    client: TestClient, texts: Texts, db: Session
) -> None:
    first = submit_ok(client, enquiry(texts, 1))
    second = submit_ok(client, enquiry(texts, 1, page_url="/nri"))
    assert lead_by_reference(db, second).duplicate_of_id == lead_by_reference(db, first).id


def test_another_project_or_a_day_later_is_a_new_lead(
    client: TestClient, owner: SignedIn, texts: Texts, db: Session, qr_present: None
) -> None:
    live = published_project(owner)
    general = submit_ok(client, enquiry(texts, 1))
    project = submit_ok(client, enquiry(texts, 1, project_slug=live["slug"]))
    assert lead_by_reference(db, project).duplicate_of_id is None
    db.execute(
        text("UPDATE lead SET created_at = now() - interval '25 hours' WHERE reference = :r"),
        {"r": general},
    )
    db.commit()
    again = submit_ok(client, enquiry(texts, 1))
    assert lead_by_reference(db, again).duplicate_of_id is None


def test_a_duplicate_of_a_duplicate_links_to_the_first_lead(
    client: TestClient, texts: Texts, db: Session
) -> None:
    refs = [submit_ok(client, enquiry(texts, 1)) for _ in range(3)]
    first = lead_by_reference(db, refs[0]).id
    assert [lead_by_reference(db, r).duplicate_of_id for r in refs] == [None, first, first]


def test_spam_or_erased_leads_are_never_the_original(
    client: TestClient, owner: SignedIn, texts: Texts, db: Session
) -> None:
    spam = submit_ok(client, enquiry(texts, 1))
    db.execute(update(Lead).where(Lead.reference == spam).values(is_spam=True))
    db.commit()
    assert lead_by_reference(db, submit_ok(client, enquiry(texts, 1))).duplicate_of_id is None
    erased = submit_ok(client, enquiry(texts, 2))
    ok(
        owner.client.delete(f"{LEADS}/{lead_by_reference(db, erased).id}", headers=owner.headers()),
        204,
    )
    assert lead_by_reference(db, submit_ok(client, enquiry(texts, 2))).duplicate_of_id is None


def test_a_duplicate_goes_to_the_original_owner_without_moving_the_turn(
    client: TestClient, texts: Texts, db: Session, intake_unlimited: None
) -> None:
    a, b = make_user("sales", email="a@example.com"), make_user("sales", email="b@example.com")
    set_routing(db, mode="round_robin", round_robin_user_ids=[str(a.id), str(b.id)])
    first = submit_ok(client, enquiry(texts, 1))  # → a
    again = submit_ok(client, enquiry(texts, 1))  # duplicate → a, turn stays
    other = submit_ok(client, enquiry(texts, 2))  # → b
    assert owners_of(db, [first, again, other]) == [a.id, a.id, b.id]
