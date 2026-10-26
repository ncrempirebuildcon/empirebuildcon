"""Pages: create, list, edit, archive, delete and publish, with the permission rules for legal
pages and scheduling, the system-page rules, the draft-text blocker in production, SEO checks
and warnings, audit rows and `page.*` events."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    PAGES,
    block,
    create_page,
    patch_page,
    publish_page,
    put_blocks,
    soon,
    unpublish_page,
)
from empire_api.content import page_rules
from empire_api.content.seed import seed_pages
from empire_api.content.vocab import LEGAL_DRAFT_MARK
from empire_api.db import get_sessionmaker
from media_support import document, photo, signed_as
from projects_support import audit_rows, events, ok


def page_by_slug(signed: SignedIn, slug: str) -> Any:
    rows = ok(signed.client.get(PAGES, params={"q": slug, "per_page": 100}))["items"]
    return next(row for row in rows if row["slug"] == slug)


@pytest.fixture
def seeded(owner: SignedIn) -> None:
    with get_sessionmaker()() as db:
        seed_pages(db)
        db.commit()


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page_rules, "is_production", lambda: True)


# --- Create, read, list ----------------------------------------------------------------------


def test_create_makes_a_draft_with_a_slug_from_the_title(owner: SignedIn, db: Session) -> None:
    page = create_page(owner, title="NRI Corner — Buying from abroad")
    assert page["slug"] == "nri-corner-buying-from-abroad"
    assert page["path"] == "/nri-corner-buying-from-abroad"
    assert page["publish_state"] == "draft" and page["published_at"] is None
    assert page["blocks"] == [] and page["created_by"]["id"] == str(owner.user.id)
    assert len(audit_rows(db, "page.created")) == 1
    assert events(db) == []  # drafts are not on the website


def test_list_filters_and_summary_rows(owner: SignedIn, seeded: None) -> None:
    create_page(owner, title="Careers")
    rows = ok(owner.client.get(PAGES, params={"kind": "legal"}))["items"]
    assert {row["slug"] for row in rows} == {"privacy", "terms", "disclaimer"}
    assert all(row["is_draft_text"] for row in rows)
    assert "blocks" not in rows[0] and rows[0]["block_count"] == 1
    home = page_by_slug(owner, "home")
    assert home["kind"] == "system" and home["path"] == "/"
    drafts = ok(owner.client.get(PAGES, params={"publish_state": "draft", "q": "care"}))
    assert [row["slug"] for row in drafts["items"]] == ["careers"]


def test_create_refusals(owner: SignedIn) -> None:
    create_page(owner, title="Careers")
    taken = owner.client.post(
        PAGES, json={"title": "Careers", "kind": "standard"}, headers=owner.headers()
    )
    assert taken.status_code == 409 and taken.json()["errors"][0]["field"] == "slug"
    for body, field in (
        ({"title": "Home", "kind": "system"}, "kind"),
        ({"title": "Blog", "kind": "standard"}, "slug"),
        ({"title": "X", "kind": "standard", "slug": "admin"}, "slug"),
        ({"title": "<b>X</b>", "kind": "standard"}, "title"),
        ({"title": "X", "kind": "standard", "legal_version": "1.0"}, "legal_version"),
        ({"title": "X", "kind": "standard", "extra": True}, "extra"),
        ({"title": "X", "kind": "standard", "publish_at": "2026-01-01T00:00:00"}, "publish_at"),
    ):
        response = owner.client.post(PAGES, json=body, headers=owner.headers())
        assert response.status_code == 422, (body, response.text)
        assert any(e["field"].startswith(field) for e in response.json()["errors"]), response.text


def test_permissions_read_write_publish(app: FastAPI, owner: SignedIn) -> None:
    page = create_page(owner)
    sales = signed_as(app, "sales")
    assert sales.client.get(PAGES).status_code == 403
    denied = sales.client.post(
        PAGES, json={"title": "X", "kind": "standard"}, headers=sales.headers()
    )
    assert denied.status_code == 403
    assert publish_page(sales, page["id"]).status_code == 403
    editor = signed_as(app, "content_editor")
    assert ok(publish_page(editor, page["id"]))["publish_state"] == "published"


# --- Edit, archive, delete -------------------------------------------------------------------


def test_patch_changes_only_what_was_sent_and_audits(owner: SignedIn, db: Session) -> None:
    page = create_page(owner, show_in_nav=True, nav_order=4)
    updated = ok(patch_page(owner, page["id"], {"title": "About Empire"}))
    assert updated["title"] == "About Empire" and updated["show_in_nav"] is True
    assert updated["nav_order"] == 4
    assert audit_rows(db, "page.updated")[-1].changes == {"title": ["About us", "About Empire"]}
    ok(patch_page(owner, page["id"], {"title": "About Empire"}))
    assert len(audit_rows(db, "page.updated")) == 1  # nothing changed → nothing written
    null = patch_page(owner, page["id"], {"title": None})
    assert null.status_code == 422


def test_live_edits_emit_page_updated_and_archive_unpublishes(owner: SignedIn, db: Session) -> None:
    page = create_page(owner)
    ok(publish_page(owner, page["id"]))
    published = events(db, "page.published")
    assert (
        published[0].payload["path"] == "/about-us" and published[0].payload["kind"] == "standard"
    )
    ok(patch_page(owner, page["id"], {"title": "About Empire"}))
    assert events(db, "page.updated")[-1].payload["changed"] == ["title"]
    ok(put_blocks(owner, page["id"], [block("divider")]))
    assert events(db, "page.updated")[-1].payload["changed"] == ["blocks"]
    archived = ok(patch_page(owner, page["id"], {"publish_state": "archived"}))
    assert archived["publish_state"] == "archived" and archived["published_at"] is not None
    assert events(db, "page.unpublished")[-1].payload["reason"] == "archived"
    assert len(audit_rows(db, "page.archived")) == 1
    restored = ok(patch_page(owner, page["id"], {"publish_state": "draft"}))
    assert restored["publish_state"] == "draft"


def test_delete_only_never_published_drafts(owner: SignedIn, db: Session) -> None:
    draft = create_page(owner, title="Temporary")
    assert owner.client.delete(f"{PAGES}/{draft['id']}", headers=owner.headers()).status_code == 204
    assert len(audit_rows(db, "page.deleted")) == 1
    page = create_page(owner)
    ok(publish_page(owner, page["id"]))
    ok(unpublish_page(owner, page["id"]))
    refused = owner.client.delete(f"{PAGES}/{page['id']}", headers=owner.headers())
    assert refused.status_code == 409 and "Archive it instead" in refused.json()["detail"]


def test_system_pages_keep_slug_kind_and_existence(owner: SignedIn, seeded: None) -> None:
    home = page_by_slug(owner, "home")
    assert patch_page(owner, home["id"], {"slug": "start"}).status_code == 422
    assert patch_page(owner, home["id"], {"kind": "standard"}).status_code == 422
    assert patch_page(owner, home["id"], {"publish_state": "archived"}).status_code == 409
    assert owner.client.delete(f"{PAGES}/{home['id']}", headers=owner.headers()).status_code == 409
    ok(patch_page(owner, home["id"], {"title": "Welcome"}))  # other fields are editable
    ok(publish_page(owner, home["id"]))
    assert ok(unpublish_page(owner, home["id"]))["publish_state"] == "draft"


# --- Legal pages (D-017) ---------------------------------------------------------------------


def test_legal_pages_need_legal_publish(app: FastAPI, owner: SignedIn, seeded: None) -> None:
    privacy = page_by_slug(owner, "privacy")
    marketing = signed_as(app, "marketing")
    editor = signed_as(app, "content_editor")
    for signed in (marketing, editor):
        refused = publish_page(signed, privacy["id"])
        assert refused.status_code == 403 and "legal.publish" in refused.json()["detail"]
    # Drafts can be prepared with content.write …
    ok(put_blocks(editor, privacy["id"], [block("rich_text", {"body": LEGAL_DRAFT_MARK + " v2"})]))
    # … but scheduling, deleting and changing the kind need legal.publish.
    assert patch_page(editor, privacy["id"], {"publish_at": soon()}).status_code == 403
    cookies = create_page(editor, title="Cookies", kind="legal")
    assert (
        editor.client.delete(f"{PAGES}/{cookies['id']}", headers=editor.headers()).status_code
        == 403
    )
    standard = create_page(editor, title="Cookie notice")
    assert patch_page(editor, standard["id"], {"kind": "legal"}).status_code == 403
    assert patch_page(editor, privacy["id"], {"kind": "standard"}).status_code == 403
    # An admin publishes it; once live, editing it needs legal.publish too.
    admin = signed_as(app, "admin")
    assert ok(publish_page(admin, privacy["id"]))["publish_state"] == "published"
    assert patch_page(editor, privacy["id"], {"title": "Privacy"}).status_code == 403
    assert put_blocks(editor, privacy["id"], [block("divider")]).status_code == 403
    assert unpublish_page(editor, privacy["id"]).status_code == 403
    ok(patch_page(admin, privacy["id"], {"legal_version": "1.0"}))


def test_compliance_production_refuses_draft_legal_text(
    owner: SignedIn, seeded: None, production: None
) -> None:
    privacy = page_by_slug(owner, "privacy")
    assert privacy["is_draft_text"] is True
    shown = ok(owner.client.get(f"{PAGES}/{privacy['id']}"))
    assert shown["publish_blockers"] == [page_rules.LEGAL_DRAFT]
    refused = publish_page(owner, privacy["id"])
    assert refused.status_code == 409 and refused.json()["title"] == "Publish blocked"
    approved = "1. Who we are\n[Company legal name] is a real-estate developer."
    saved = ok(put_blocks(owner, privacy["id"], [block("rich_text", {"body": approved})]))
    assert saved["is_draft_text"] is False and saved["publish_blockers"] == []
    assert ok(publish_page(owner, privacy["id"]))["publish_state"] == "published"


def test_draft_marks_count_only_on_legal_pages(owner: SignedIn) -> None:
    page = create_page(owner, title="[Draft] About")
    assert page["is_draft_text"] is False


def test_sample_pages_cant_be_published_in_production(
    owner: SignedIn, db: Session, production: None
) -> None:
    from empire_api.content.models import Page  # noqa: PLC0415

    page = create_page(owner)
    row = db.get(Page, page["id"])
    assert row is not None
    row.is_sample = True
    db.commit()
    refused = publish_page(owner, page["id"])
    assert refused.status_code == 409
    assert page_rules.SAMPLE_ON_LIVE_SITE in refused.json()["detail"]


# --- Scheduling ------------------------------------------------------------------------------


def test_schedule_validation(owner: SignedIn) -> None:
    page = create_page(owner)
    past = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    assert patch_page(owner, page["id"], {"publish_at": past}).status_code == 422
    order = patch_page(owner, page["id"], {"publish_at": soon(2), "unpublish_at": soon(1)})
    assert order.status_code == 422 and order.json()["errors"][0]["field"] == "unpublish_at"
    scheduled = ok(patch_page(owner, page["id"], {"publish_at": soon(1), "unpublish_at": soon(9)}))
    assert scheduled["publish_at"] is not None and scheduled["unpublish_at"] is not None
    archived = ok(patch_page(owner, page["id"], {"publish_state": "archived"}))
    assert archived["publish_at"] is None and archived["unpublish_at"] is None
    assert patch_page(owner, page["id"], {"publish_at": soon()}).status_code == 422


def test_scheduling_needs_content_publish(
    app: FastAPI, owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    from empire_api.users import roles  # noqa: PLC0415

    description, holders = roles.PERMISSIONS["content.publish"]
    monkeypatch.setitem(
        roles.PERMISSIONS, "content.publish", (description, holders - {"marketing"})
    )
    marketing = signed_as(app, "marketing")
    page = create_page(marketing)
    refused = patch_page(marketing, page["id"], {"publish_at": soon()})
    assert refused.status_code == 403 and "content.publish" in refused.json()["detail"]
    ok(publish_page(owner, page["id"]))
    off_site = patch_page(marketing, page["id"], {"publish_state": "archived"})
    assert off_site.status_code == 403


# --- SEO -------------------------------------------------------------------------------------


def test_seo_is_validated_and_warned_about(owner: SignedIn) -> None:
    page = create_page(owner)
    codes = {w["code"] for w in page["seo_warnings"]}
    assert codes == {"title_missing", "description_missing"}
    for seo, field in (
        ({"title": "t" * 71}, "seo.title"),
        ({"description": "d" * 171}, "seo.description"),
        ({"canonical_path": "https://elsewhere.example/x"}, "seo.canonical_path"),
        ({"og_image_id": document(owner)["id"]}, "seo.og_image_id"),
    ):
        response = patch_page(owner, page["id"], {"seo": seo})
        assert response.status_code == 422, (seo, response.text)
        assert response.json()["errors"][0]["field"] == field
    image = photo(owner)
    long_title = "A title that is comfortably longer than sixty characters in all"
    saved = ok(
        patch_page(
            owner,
            page["id"],
            {
                "seo": {
                    "title": long_title,
                    "description": "d" * 165,
                    "og_image_id": image["id"],
                    "noindex": True,
                    "canonical_path": "/about-us",
                }
            },
        )
    )
    assert {w["code"] for w in saved["seo_warnings"]} == {
        "title_long",
        "description_long",
        "noindex",
    }
    assert saved["og_image"]["id"] == image["id"]
    assert [m["id"] for m in saved["media"]] == [image["id"]]  # previews: the share image too
    merged = ok(patch_page(owner, page["id"], {"seo": {"noindex": False}}))
    assert merged["seo"]["title"] == long_title and merged["seo"]["noindex"] is False


def test_seo_changes_need_seo_manage(app: FastAPI, monkeypatch: pytest.MonkeyPatch) -> None:
    from empire_api.users import roles  # noqa: PLC0415

    description, holders = roles.PERMISSIONS["seo.manage"]
    monkeypatch.setitem(roles.PERMISSIONS, "seo.manage", (description, holders - {"marketing"}))
    marketing = signed_as(app, "marketing")
    page = create_page(marketing)
    refused = patch_page(marketing, page["id"], {"seo": {"title": "Better title"}})
    assert refused.status_code == 403 and "seo.manage" in refused.json()["detail"]
    ok(patch_page(marketing, page["id"], {"title": "Still fine"}))


def test_translations_only_for_the_title(owner: SignedIn) -> None:
    page = create_page(owner)
    ok(patch_page(owner, page["id"], {"translations": {"hi": {"title": "हमारे बारे में"}}}))
    refused = patch_page(owner, page["id"], {"translations": {"hi": {"body": "x"}}})
    assert refused.status_code == 422
