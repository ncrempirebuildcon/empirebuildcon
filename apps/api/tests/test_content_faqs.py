"""FAQs: site-wide or per project, ordered, shown or hidden; ProjectAdmin lists the project's
FAQs in order; showing one needs content.publish; a deleted FAQ leaves every block."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import FAQS, block, create_faq, create_page, publish_page, put_blocks
from empire_api.users import roles
from media_support import signed_as
from projects_support import audit_rows, create_project, events, get_project, ok


def patch_faq(signed: SignedIn, faq_id: str, body: dict[str, object]) -> object:
    return signed.client.patch(f"{FAQS}/{faq_id}", json=body, headers=signed.headers())


def reorder(signed: SignedIn, ids: list[str]) -> object:
    return signed.client.put(f"{FAQS}/order", json={"ids": ids}, headers=signed.headers())


def test_project_faqs_fill_project_admin_in_order(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    first = create_faq(owner, "Is parking included?", project_id=project["id"])
    second = create_faq(owner, "When is possession?", project_id=project["id"], is_visible=False)
    create_faq(owner, "How do I book a visit?")  # site-wide
    assert (first["sort_order"], second["sort_order"]) == (0, 1)
    assert first["project_name"] == "Aurum Heights"
    faqs = get_project(owner, project["id"])["faqs"]
    assert [f["id"] for f in faqs] == [first["id"], second["id"]]
    ok(reorder(owner, [second["id"], first["id"]]))
    faqs = get_project(owner, project["id"])["faqs"]
    assert [f["id"] for f in faqs] == [second["id"], first["id"]]
    assert len(audit_rows(db, "faq.reordered")) == 1


def test_list_filters(owner: SignedIn) -> None:
    project = create_project(owner)
    in_project = create_faq(owner, "Q1?", project_id=project["id"])
    site = create_faq(owner, "Q2?")
    all_rows = ok(owner.client.get(FAQS))["items"]
    assert [row["id"] for row in all_rows] == [site["id"], in_project["id"]]
    only_site = ok(owner.client.get(FAQS, params={"site_wide": True}))["items"]
    assert [row["id"] for row in only_site] == [site["id"]]
    one = ok(owner.client.get(FAQS, params={"project_id": project["id"]}))["items"]
    assert [row["id"] for row in one] == [in_project["id"]]


def test_reorder_needs_the_whole_list(owner: SignedIn) -> None:
    a, b = create_faq(owner, "A?"), create_faq(owner, "B?")
    create_faq(owner, "C?")
    assert reorder(owner, [b["id"], a["id"]]).status_code == 422


def test_moving_to_another_project_appends_there(owner: SignedIn) -> None:
    project = create_project(owner)
    create_faq(owner, "Existing?", project_id=project["id"])
    site = create_faq(owner, "Moving?")
    moved = ok(patch_faq(owner, site["id"], {"project_id": project["id"]}))
    assert moved["project_id"] == project["id"] and moved["sort_order"] == 1


def test_validation(owner: SignedIn) -> None:
    for body, field in (
        ({"question": "q" * 201, "answer": "a"}, "question"),
        ({"question": "Q?", "answer": "a" * 4001}, "answer"),
        ({"question": "Q?", "answer": "<b>a</b>"}, "answer"),
        (
            {"question": "Q?", "answer": "a", "project_id": "00000000-0000-7000-8000-000000000000"},
            "project_id",
        ),
        ({"question": "Q?", "answer": "a", "translations": {"hi": {"name": "x"}}}, "translations"),
    ):
        response = owner.client.post(FAQS, json=body, headers=owner.headers())
        assert response.status_code == 422, (body, response.text)
        assert response.json()["errors"][0]["field"].startswith(field)


def test_showing_an_faq_needs_content_publish(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    description, holders = roles.PERMISSIONS["content.publish"]
    monkeypatch.setitem(
        roles.PERMISSIONS, "content.publish", (description, holders - {"marketing"})
    )
    marketing = signed_as(app, "marketing")
    refused = marketing.client.post(
        FAQS, json={"question": "Q?", "answer": "A."}, headers=marketing.headers()
    )
    assert refused.status_code == 403 and "content.publish" in refused.json()["detail"]
    hidden = create_faq(marketing, is_visible=False)
    ok(patch_faq(marketing, hidden["id"], {"answer": "Edited while hidden."}))
    assert patch_faq(marketing, hidden["id"], {"is_visible": True}).status_code == 403


def test_events_only_when_shown(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    hidden = create_faq(owner, project_id=project["id"], is_visible=False)
    ok(patch_faq(owner, hidden["id"], {"answer": "Still hidden."}))
    assert events(db, "faq.changed") == []
    ok(patch_faq(owner, hidden["id"], {"is_visible": True}))
    changed = events(db, "faq.changed")
    assert changed[-1].payload["project_slug"] == "aurum-heights"
    assert changed[-1].payload["change"] == "updated"


def test_a_deleted_faq_leaves_every_block(owner: SignedIn, db: Session) -> None:
    keep, gone = create_faq(owner, "Keep?"), create_faq(owner, "Gone?")
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("faq_list", {"faq_ids": [keep["id"], gone["id"]]})]))
    ok(publish_page(owner, page["id"]))
    assert owner.client.delete(f"{FAQS}/{gone['id']}", headers=owner.headers()).status_code == 204
    shown = ok(owner.client.get(f"/api/v1/admin/pages/{page['id']}"))
    assert shown["blocks"][0]["data"]["faq_ids"] == [keep["id"]]
    assert events(db, "page.updated")[-1].payload["changed"] == ["blocks"]
    assert len(audit_rows(db, "page.block_reference_removed")) == 1
    assert len(audit_rows(db, "faq.deleted")) == 1


def test_a_block_whose_last_picked_faq_goes_is_hidden_not_widened(
    owner: SignedIn, db: Session
) -> None:
    """M4: an empty pick list would mean "every site-wide FAQ"; the block is hidden instead."""
    only = create_faq(owner, "Only this one?")
    page = create_page(owner)
    blocks = [
        block("faq_list", {"heading": "Parking", "faq_ids": [only["id"]]}),
        block("divider"),
    ]
    ok(put_blocks(owner, page["id"], blocks))
    ok(publish_page(owner, page["id"]))
    assert owner.client.delete(f"{FAQS}/{only['id']}", headers=owner.headers()).status_code == 204
    shown = ok(owner.client.get(f"/api/v1/admin/pages/{page['id']}"))
    faq_block = shown["blocks"][0]
    assert faq_block["data"]["faq_ids"] == [] and faq_block["is_visible"] is False
    assert shown["blocks"][1]["is_visible"] is True
    removed = audit_rows(db, "page.block_reference_removed")[0].changes
    assert removed["blocks.0.is_visible"] == [True, False]
    assert events(db, "page.updated")[-1].payload["changed"] == ["blocks"]
