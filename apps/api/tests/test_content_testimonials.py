"""Testimonials: real ones only. Showing one needs a source and a consent date (API and
database); ratings 1–5; writing needs content.publish; personal words stay out of the audit log
and events; a deleted testimonial leaves every block."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    TESTIMONIALS,
    block,
    buyer_quote,
    create_page,
    create_testimonial,
    put_blocks,
)
from empire_api.timeutil import today_ist
from media_support import document, signed_as
from projects_support import audit_rows, events, ok


def test_showing_needs_source_and_consent(owner: SignedIn) -> None:
    hidden = create_testimonial(owner)
    assert hidden["is_visible"] is False and hidden["can_show"] is False
    refused = owner.client.post(
        TESTIMONIALS, json=buyer_quote(is_visible=True), headers=owner.headers()
    )
    assert refused.status_code == 422 and refused.json()["errors"][0]["field"] == "is_visible"
    switch_on = owner.client.patch(
        f"{TESTIMONIALS}/{hidden['id']}", json={"is_visible": True}, headers=owner.headers()
    )
    assert switch_on.status_code == 422
    consented = ok(
        owner.client.patch(
            f"{TESTIMONIALS}/{hidden['id']}",
            json={"consent_date": "2026-03-02"},
            headers=owner.headers(),
        )
    )
    assert consented["can_show"] is True
    shown = ok(
        owner.client.patch(
            f"{TESTIMONIALS}/{hidden['id']}", json={"is_visible": True}, headers=owner.headers()
        )
    )
    assert shown["is_visible"] is True


def test_invariant_the_database_refuses_a_visible_testimonial_without_consent(
    owner: SignedIn, db: Session
) -> None:
    row = create_testimonial(owner)
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE testimonial SET is_visible = true WHERE id = :id"), {"id": row["id"]}
        )
        db.commit()
    db.rollback()


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"source": "ok"}, "source"),
        ({"rating": 6}, "rating"),
        ({"rating": 0}, "rating"),
        ({"consent_date": (today_ist() + timedelta(days=2)).isoformat()}, "consent_date"),
        ({"quote": "<script>x</script>"}, "quote"),
        ({"source_url": "javascript:alert(1)"}, "source_url"),
        ({"is_sample": True}, "is_sample"),
    ],
)
def test_validation(owner: SignedIn, fields: dict[str, object], field: str) -> None:
    response = owner.client.post(TESTIMONIALS, json=buyer_quote(**fields), headers=owner.headers())
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["field"] == field


def test_photo_must_be_an_image(owner: SignedIn) -> None:
    response = owner.client.post(
        TESTIMONIALS,
        json=buyer_quote(photo_media_id=document(owner)["id"]),
        headers=owner.headers(),
    )
    assert response.status_code == 422


def test_writing_needs_content_publish(app: FastAPI) -> None:
    sales = signed_as(app, "sales")
    assert sales.client.get(TESTIMONIALS).status_code == 403
    response = sales.client.post(TESTIMONIALS, json=buyer_quote(), headers=sales.headers())
    assert response.status_code == 403


def test_security_personal_words_stay_out_of_audit_and_events(owner: SignedIn, db: Session) -> None:
    row = create_testimonial(owner, consent_date="2026-03-02", is_visible=True)
    ok(
        owner.client.patch(
            f"{TESTIMONIALS}/{row['id']}",
            json={"quote": "Changed words.", "rating": 5},
            headers=owner.headers(),
        )
    )
    created = audit_rows(db, "testimonial.created")[0].changes
    assert created["person_name"] == [None, "[hidden]"] and created["quote"] == [None, "[hidden]"]
    updated = audit_rows(db, "testimonial.updated")[0].changes
    assert updated["quote"] == ["[hidden]", "[hidden]"] and updated["rating"] == [None, 5]
    payloads = [e.payload for e in events(db, "testimonial.changed")]
    assert payloads and all("person_name" not in p and "quote" not in p for p in payloads)
    assert "Sharma" not in str([a.changes for a in audit_rows(db, "testimonial.updated")])


def test_a_deleted_testimonial_leaves_every_block(owner: SignedIn, db: Session) -> None:
    row = create_testimonial(owner)
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("testimonials", {"testimonial_ids": [row["id"]]})]))
    assert (
        owner.client.delete(f"{TESTIMONIALS}/{row['id']}", headers=owner.headers()).status_code
        == 204
    )
    shown = ok(owner.client.get(f"/api/v1/admin/pages/{page['id']}"))
    assert shown["blocks"][0]["data"]["testimonial_ids"] == []
    deleted = audit_rows(db, "testimonial.deleted")[0].changes
    assert deleted["person_name"] == ["[hidden]", None]


def test_a_block_whose_last_picked_testimonial_goes_is_hidden(owner: SignedIn, db: Session) -> None:
    """M4: an empty pick list would mean "the newest testimonials from any project"."""
    row = create_testimonial(owner)
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("testimonials", {"testimonial_ids": [row["id"]]})]))
    owner.client.delete(f"{TESTIMONIALS}/{row['id']}", headers=owner.headers())
    shown = ok(owner.client.get(f"/api/v1/admin/pages/{page['id']}"))
    assert shown["blocks"][0]["is_visible"] is False
    assert events(db, "page.updated") == []  # a draft page: nothing to revalidate


def test_security_the_source_is_masked_in_the_audit_log_too(owner: SignedIn, db: Session) -> None:
    """L9: staff type names into `source` ("WhatsApp from Ravi, 2 Mar")."""
    row = create_testimonial(owner, source="WhatsApp message from Ravi Sharma, 2 Mar 2026")
    ok(
        owner.client.patch(
            f"{TESTIMONIALS}/{row['id']}",
            json={"source": "Email from Ravi Sharma, 3 Mar 2026"},
            headers=owner.headers(),
        )
    )
    owner.client.delete(f"{TESTIMONIALS}/{row['id']}", headers=owner.headers())
    for action in ("testimonial.created", "testimonial.updated", "testimonial.deleted"):
        changes = audit_rows(db, action)[0].changes
        assert "Ravi" not in str(changes), action
        assert "[hidden]" in changes["source"], action
