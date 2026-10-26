"""Legal pages (D-017) after review fixes H2, M1 and L8: a scheduled legal page is guarded like a
live one, production never leaves DRAFT text on a live legal page (or moves it in or out of the
legal kind), and the seeded legal pages are required pages (fixed slug and kind, never deleted
or archived)."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    PAGES,
    block,
    create_page,
    get_page,
    later,
    page_by_slug,
    patch_page,
    publish_page,
    put_blocks,
    seed_site_pages,
    soon,
    unpublish_page,
)
from empire_api.content import page_rules
from empire_api.content.schedule import schedule_tick
from empire_api.content.seed import seed_pages
from empire_api.content.vocab import DRAFT_MARK, LEGAL_DRAFT_MARK
from empire_api.db import get_sessionmaker
from media_support import signed_as
from projects_support import audit_rows, ok

APPROVED = "1. Who we are\n[Company legal name] is a real-estate developer."


@pytest.fixture
def seeded(owner: SignedIn) -> None:
    seed_site_pages()


@pytest.fixture
def production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(page_rules, "is_production", lambda: True)


def approved_privacy(owner: SignedIn) -> str:
    """The seeded privacy page with owner-approved wording (no DRAFT mark)."""
    privacy = page_by_slug(owner, "privacy")
    ok(put_blocks(owner, privacy["id"], [block("rich_text", {"body": APPROVED})]))
    return str(privacy["id"])


# --- H2: a scheduled legal page needs legal.publish for any change ----------------------------


def test_compliance_a_scheduled_legal_page_is_guarded_like_a_live_one(
    app: FastAPI, owner: SignedIn, seeded: None
) -> None:
    privacy_id = approved_privacy(owner)
    admin = signed_as(app, "admin")
    ok(patch_page(admin, privacy_id, {"publish_at": soon(1)}))
    editor = signed_as(app, "content_editor")
    rewrite = put_blocks(editor, privacy_id, [block("rich_text", {"body": "My own wording."})])
    assert rewrite.status_code == 403 and "legal.publish" in rewrite.json()["detail"]
    assert patch_page(editor, privacy_id, {"title": "Privacy notice"}).status_code == 403
    assert patch_page(editor, privacy_id, {"show_in_nav": True}).status_code == 403
    # The tick publishes exactly what the admin scheduled.
    assert schedule_tick(now=later(25)).published == 1
    live = get_page(owner, privacy_id)
    assert live["publish_state"] == "published"
    assert live["blocks"][0]["data"]["body"] == APPROVED and live["title"] == "Privacy policy"


def test_a_draft_legal_page_without_a_schedule_stays_open_to_content_write(
    app: FastAPI, owner: SignedIn, seeded: None
) -> None:
    editor = signed_as(app, "content_editor")
    privacy = page_by_slug(owner, "privacy")
    ok(put_blocks(editor, privacy["id"], [block("rich_text", {"body": LEGAL_DRAFT_MARK + " v2"})]))
    ok(patch_page(editor, privacy["id"], {"title": "Privacy notice"}))


# --- M1: production keeps DRAFT text off live legal pages --------------------------------------


def test_compliance_production_refuses_draft_text_on_a_live_legal_page(
    owner: SignedIn, seeded: None, production: None, db: Session
) -> None:
    privacy_id = approved_privacy(owner)
    ok(publish_page(owner, privacy_id))
    for body in (LEGAL_DRAFT_MARK, f"Section 1\n{DRAFT_MARK}"):
        refused = put_blocks(owner, privacy_id, [block("rich_text", {"body": body})])
        assert refused.status_code == 409, refused.text
        assert refused.json()["errors"] == [{"field": "blocks", "message": page_rules.LEGAL_DRAFT}]
    titled = patch_page(owner, privacy_id, {"title": "Privacy policy [Draft v2]"})
    assert titled.status_code == 409 and titled.json()["errors"][0]["field"] == "title"
    shown = get_page(owner, privacy_id)
    assert shown["is_draft_text"] is False and shown["blocks"][0]["data"]["body"] == APPROVED
    assert len(audit_rows(db, "page.blocks_saved")) == 1  # only the approved wording
    # Taking it off the website is always possible.
    assert ok(unpublish_page(owner, privacy_id))["publish_state"] == "draft"


def test_compliance_production_refuses_moving_draft_text_in_or_out_of_legal(
    owner: SignedIn, seeded: None, production: None
) -> None:
    notice = create_page(owner, title="Cookie notice", kind="legal")
    ok(put_blocks(owner, notice["id"], [block("rich_text", {"body": LEGAL_DRAFT_MARK})]))
    out = patch_page(owner, notice["id"], {"kind": "standard"})
    assert out.status_code == 409 and out.json()["errors"][0]["field"] == "kind"
    standard = create_page(owner, title="Cookie notice draft")
    ok(put_blocks(owner, standard["id"], [block("rich_text", {"body": LEGAL_DRAFT_MARK})]))
    into = patch_page(owner, standard["id"], {"kind": "legal"})
    assert into.status_code == 409 and into.json()["errors"][0]["field"] == "kind"
    # Approved text moves freely.
    ok(put_blocks(owner, standard["id"], [block("rich_text", {"body": APPROVED})]))
    assert ok(patch_page(owner, standard["id"], {"kind": "legal"}))["kind"] == "legal"


def test_development_still_allows_draft_text_on_a_live_legal_page(
    owner: SignedIn, seeded: None
) -> None:
    """As for publishing, dev and test allow DRAFT text so the CMS can be tried out."""
    privacy_id = approved_privacy(owner)
    ok(publish_page(owner, privacy_id))
    saved = ok(put_blocks(owner, privacy_id, [block("rich_text", {"body": LEGAL_DRAFT_MARK})]))
    assert saved["is_draft_text"] is True and saved["publish_state"] == "published"


# --- L8: the seeded legal pages are required pages ---------------------------------------------


def test_seeded_system_and_legal_pages_are_required(owner: SignedIn, seeded: None) -> None:
    rows = ok(owner.client.get(PAGES, params={"per_page": 100}))["items"]
    required = {row["slug"] for row in rows if row["is_required"]}
    assert required == {"home", "projects", "about", "contact", "privacy", "terms", "disclaimer"}
    made = create_page(owner, title="Cookie notice", kind="legal")
    assert made["is_required"] is False
    assert get_page(owner, made["id"])["is_required"] is False


def test_required_legal_pages_keep_slug_kind_and_existence(
    app: FastAPI, owner: SignedIn, seeded: None
) -> None:
    privacy = page_by_slug(owner, "privacy")
    renamed = patch_page(owner, privacy["id"], {"slug": "privacy-policy"})
    assert renamed.status_code == 422 and renamed.json()["errors"][0]["field"] == "slug"
    rekinded = patch_page(owner, privacy["id"], {"kind": "standard"})
    assert rekinded.status_code == 422 and rekinded.json()["errors"][0]["field"] == "kind"
    assert patch_page(owner, privacy["id"], {"publish_state": "archived"}).status_code == 409
    deleted = owner.client.delete(f"{PAGES}/{privacy['id']}", headers=owner.headers())
    assert deleted.status_code == 409 and "comes with the website" in deleted.json()["detail"]
    ok(publish_page(owner, privacy["id"]))
    editor = signed_as(app, "content_editor")
    assert unpublish_page(editor, privacy["id"]).status_code == 403  # still legal.publish
    assert ok(unpublish_page(owner, privacy["id"]))["publish_state"] == "draft"
    # A legal page staff made themselves is an ordinary one.
    cookie = create_page(owner, title="Cookie notice", kind="legal")
    ok(patch_page(owner, cookie["id"], {"slug": "cookies"}))
    assert (
        owner.client.delete(f"{PAGES}/{cookie['id']}", headers=owner.headers()).status_code == 204
    )


def test_seed_re_run_adds_no_second_legal_page(owner: SignedIn, seeded: None) -> None:
    """L8: the slug of a required page can't change, so matching by slug is safe."""
    with get_sessionmaker()() as db:
        assert seed_pages(db) == 0
        db.commit()
    rows = ok(owner.client.get(PAGES, params={"kind": "legal"}))["items"]
    assert sorted(row["slug"] for row in rows) == ["disclaimer", "privacy", "terms"]
