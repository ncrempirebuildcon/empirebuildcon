"""Redirects (ARCHITECTURE §16, SECURITY.md §5): both ends validated, no open redirects, loops
refused, chains collapsed with a notice, and automatic 308s when a live project, page or post
changes its slug. Plus permissions, audit rows and `redirect.changed`."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    POSTS,
    REDIRECTS,
    create_page,
    create_post,
    create_redirect,
    list_redirects,
    page_by_slug,
    patch_page,
    publish_page,
    seed_site_pages,
)
from empire_api.seo.models import Redirect
from media_support import signed_as
from projects_support import audit_rows, events, make_ready, ok, patch_project, publish
from projects_support import create_project as new_project


def targets(signed: SignedIn) -> dict[str, str]:
    return {row["from_path"]: row["to_path"] for row in list_redirects(signed)}


def test_create_list_update_delete(owner: SignedIn, db: Session) -> None:
    made = ok(create_redirect(owner, "/old-offer/", "/offers"), 201)
    assert made["from_path"] == "/old-offer"  # trailing slash dropped
    assert made["status_code"] == "308" and made["origin"] == "manual"
    assert made["hits"] == 0 and made["last_hit_at"] is None and made["notices"] == []
    changed = ok(
        owner.client.patch(
            f"{REDIRECTS}/{made['id']}", json={"status_code": "301"}, headers=owner.headers()
        )
    )
    assert changed["status_code"] == "301"
    assert ok(owner.client.get(REDIRECTS, params={"q": "OLD"}))["meta"]["total"] == 1
    deleted = owner.client.delete(f"{REDIRECTS}/{made['id']}", headers=owner.headers())
    assert deleted.status_code == 204
    assert [e.payload["change"] for e in events(db, "redirect.changed")] == [
        "created",
        "updated",
        "deleted",
    ]
    for action in ("redirect.created", "redirect.updated", "redirect.deleted"):
        assert len(audit_rows(db, action)) == 1


@pytest.mark.parametrize(
    ("from_path", "to_path", "field"),
    [
        ("old", "/new", "from_path"),
        ("/old?x=1", "/new", "from_path"),
        ("/old#top", "/new", "from_path"),
        ("//evil.example", "/new", "from_path"),
        ("/", "/new", "from_path"),
        ("/admin/login", "/new", "from_path"),
        ("/api/v1/x", "/new", "from_path"),
        ("/old", "https://evil.example/x", "to_path"),
        ("/old", "http://empirebuildcon.com/x", "to_path"),
        ("/old", "//evil.example/x", "to_path"),
        ("/old", "javascript:alert(1)", "to_path"),
        ("/old", "https://empirebuildcon.com@evil.example/x", "to_path"),
        ("/old", "/admin", "to_path"),
        ("/old", "/old/", "to_path"),
        # H1: an address on our own host whose path starts with // would be stored as
        # `//evil.example`, which a browser follows to another site.
        ("/old", "https://empirebuildcon.com//evil.example", "to_path"),
        ("/old", "https://www.empirebuildcon.in///x", "to_path"),
        ("/old", "https://empirebuildcon.com//evil.example/?x=1", "to_path"),
        # L6: the reserved check ignores case.
        ("/Admin", "/new", "from_path"),
        ("/API/x", "/new", "from_path"),
        ("/_Next/static/x.js", "/new", "from_path"),
        ("/old", "/ADMIN/login", "to_path"),
    ],
)
def test_security_both_ends_are_checked(
    owner: SignedIn, from_path: str, to_path: str, field: str
) -> None:
    response = create_redirect(owner, from_path, to_path)
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["field"] == field


def test_security_an_update_cant_point_off_site_either(owner: SignedIn) -> None:
    made = ok(create_redirect(owner, "/old", "/new"), 201)
    response = owner.client.patch(
        f"{REDIRECTS}/{made['id']}",
        json={"to_path": "https://empirebuildcon.com//evil.example"},
        headers=owner.headers(),
    )
    assert response.status_code == 422 and response.json()["errors"][0]["field"] == "to_path"


def test_security_the_database_refuses_an_off_site_target(db: Session) -> None:
    """Backstop for H1: `ck_redirect_to_path_is_site_path`."""
    for target in ("//evil.example", "https://evil.example", "\\\\evil.example"):
        db.add(Redirect(from_path="/old", to_path=target))
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()


def test_paths_match_exactly_apart_from_the_reserved_check(owner: SignedIn) -> None:
    """L6: Phase 5 matches paths case-sensitively, so /A and /a are different addresses (and
    /A → /b plus /b → /a is not a loop)."""
    ok(create_redirect(owner, "/About", "/about-us"), 201)
    ok(create_redirect(owner, "/about", "/about-us"), 201)
    ok(create_redirect(owner, "/b", "/a"), 201)
    assert ok(create_redirect(owner, "/A", "/b"), 201)["to_path"] == "/a"


@pytest.mark.parametrize(
    ("to_path", "stored"),
    [
        ("https://empirebuildcon.com/projects/a", "/projects/a"),
        ("https://www.empirebuildcon.in/contact?from=ad#form", "/contact?from=ad#form"),
        ("/projects?city=noida", "/projects?city=noida"),
        ("/", "/"),
    ],
)
def test_our_domains_are_stored_as_paths(owner: SignedIn, to_path: str, stored: str) -> None:
    assert ok(create_redirect(owner, "/old", to_path), 201)["to_path"] == stored


def test_from_path_is_unique(owner: SignedIn) -> None:
    ok(create_redirect(owner, "/a", "/b"), 201)
    taken = create_redirect(owner, "/a", "/c")
    assert taken.status_code == 409 and taken.json()["errors"][0]["field"] == "from_path"


def test_invariant_loops_are_refused(owner: SignedIn) -> None:
    ok(create_redirect(owner, "/b", "/a"), 201)
    loop = create_redirect(owner, "/a", "/b")
    assert loop.status_code == 409
    assert "loop" in loop.json()["detail"] and loop.json()["errors"][0]["field"] == "to_path"


def test_invariant_a_chain_is_stored_one_hop_with_a_notice(owner: SignedIn) -> None:
    ok(create_redirect(owner, "/b", "/c"), 201)
    made = ok(create_redirect(owner, "/a", "/b"), 201)
    assert made["to_path"] == "/c"
    assert made["notices"] == ["/b already redirects to /c, so /a now goes straight to /c."]


def test_invariant_redirects_into_a_new_source_are_collapsed(owner: SignedIn, db: Session) -> None:
    ok(create_redirect(owner, "/x", "/a"), 201)
    ok(create_redirect(owner, "/y", "/a?ref=1"), 201)
    made = ok(create_redirect(owner, "/a", "/b"), 201)
    # L4: /y keeps its ?ref=1, because /b has no query string of its own.
    assert made["notices"] == [
        "2 redirects that pointed to /a now go straight to /b. Any query string or fragment "
        "they had is kept."
    ]
    assert targets(owner) == {"/x": "/b", "/y": "/b?ref=1", "/a": "/b"}


def test_a_collapsed_chain_keeps_the_query_and_fragment(owner: SignedIn) -> None:
    """L4: the onward target's own query string or fragment wins; otherwise the original's is
    carried over, and the notice says so."""
    ok(create_redirect(owner, "/b", "/c"), 201)
    made = ok(create_redirect(owner, "/a", "/b?ref=ad#form"), 201)
    assert made["to_path"] == "/c?ref=ad#form"
    assert made["notices"] == [
        "/b already redirects to /c, so /a now goes straight to /c?ref=ad#form. "
        "?ref=ad#form from the address you entered is kept."
    ]
    ok(create_redirect(owner, "/e", "/f?x=2"), 201)
    assert ok(create_redirect(owner, "/d", "/e?ref=1#top"), 201)["to_path"] == "/f?x=2#top"
    one = ok(create_redirect(owner, "/g", "/h"), 201)
    assert one["notices"] == []
    single = ok(create_redirect(owner, "/h", "/i"), 201)
    assert single["notices"] == ["1 redirect that pointed to /h now goes straight to /i."]


def test_a_slug_change_keeps_the_query_of_redirects_into_the_old_path(
    owner: SignedIn,
) -> None:
    page = create_page(owner, title="Offers")
    ok(publish_page(owner, page["id"]))
    ok(create_redirect(owner, "/deals", "/offers?from=old-site"), 201)
    ok(patch_page(owner, page["id"], {"slug": "current-offers"}))
    assert targets(owner) == {
        "/deals": "/current-offers?from=old-site",
        "/offers": "/current-offers",
    }


def test_a_manual_redirect_cant_hide_something_live(owner: SignedIn, qr_present: None) -> None:
    """L5: a redirect from the address of a live page, post or project would hide it."""
    page = create_page(owner, title="Careers")
    draft = create_redirect(owner, "/careers", "/contact")
    assert draft.status_code == 201  # a draft isn't on the website yet
    owner.client.delete(f"{REDIRECTS}/{draft.json()['id']}", headers=owner.headers())
    ok(publish_page(owner, page["id"]))
    post = create_post(owner)
    ok(owner.client.post(f"{POSTS}/{post['id']}/publish", headers=owner.headers()))
    project = new_project(owner)
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    for path, what in (
        ("/careers", "The page “Careers”"),
        ("/blog/how-to-check-a-project", "The post “How to check a project”"),
        ("/projects/aurum-heights", "The project “Aurum Heights”"),
    ):
        refused = create_redirect(owner, path, "/contact", is_active=False)
        assert refused.status_code == 409, refused.text
        assert refused.json()["errors"][0]["field"] == "from_path"
        assert what in refused.json()["detail"]
    seed_site_pages()
    ok(publish_page(owner, page_by_slug(owner, "home")["id"]))
    ok(create_redirect(owner, "/home", "/"), 201)  # the home page lives at /, not /home
    other = ok(create_redirect(owner, "/old-careers", "/contact"), 201)
    moved = owner.client.patch(
        f"{REDIRECTS}/{other['id']}", json={"from_path": "/careers"}, headers=owner.headers()
    )
    assert moved.status_code == 409


def test_inactive_redirects_take_no_part_until_switched_on(owner: SignedIn) -> None:
    off = ok(create_redirect(owner, "/b", "/a", is_active=False), 201)
    made = ok(create_redirect(owner, "/a", "/b"), 201)
    assert made["to_path"] == "/b"
    switched = owner.client.patch(
        f"{REDIRECTS}/{off['id']}", json={"is_active": True}, headers=owner.headers()
    )
    assert switched.status_code == 409  # would loop now


def test_redirects_need_seo_manage(app: FastAPI) -> None:
    for role in ("sales",):
        signed = signed_as(app, role)
        assert signed.client.get(REDIRECTS).status_code == 403
        assert create_redirect(signed, "/a", "/b").status_code == 403
    editor = signed_as(app, "content_editor")
    assert create_redirect(editor, "/a", "/b").status_code == 201


# --- Automatic redirects on slug changes -----------------------------------------------------


def test_a_live_page_slug_change_leaves_a_308(owner: SignedIn, db: Session) -> None:
    page = create_page(owner, title="Offers")
    ok(patch_page(owner, page["id"], {"slug": "offers-draft"}))
    assert list_redirects(owner) == []  # drafts aren't on the website: no redirect
    ok(publish_page(owner, page["id"]))
    ok(patch_page(owner, page["id"], {"slug": "current-offers"}))
    rows = list_redirects(owner)
    assert [(r["from_path"], r["to_path"], r["status_code"], r["origin"]) for r in rows] == [
        ("/offers-draft", "/current-offers", "308", "page")
    ]
    assert events(db, "page.updated")[-1].payload["previous_path"] == "/offers-draft"
    # Renaming again collapses the chain; renaming back removes the redirect from the live path.
    ok(patch_page(owner, page["id"], {"slug": "offers-2026"}))
    assert targets(owner) == {"/offers-draft": "/offers-2026", "/current-offers": "/offers-2026"}
    ok(patch_page(owner, page["id"], {"slug": "current-offers"}))
    assert targets(owner) == {"/offers-draft": "/current-offers", "/offers-2026": "/current-offers"}


def test_a_live_post_slug_change_leaves_a_308(owner: SignedIn) -> None:
    post = create_post(owner)
    ok(owner.client.post(f"{POSTS}/{post['id']}/publish", headers=owner.headers()))
    ok(
        owner.client.patch(
            f"{POSTS}/{post['id']}", json={"slug": "check-a-project"}, headers=owner.headers()
        )
    )
    assert targets(owner) == {"/blog/how-to-check-a-project": "/blog/check-a-project"}
    assert list_redirects(owner)[0]["origin"] == "post"


def test_a_live_project_slug_change_leaves_a_308(
    owner: SignedIn, qr_present: None, db: Session
) -> None:
    project = new_project(owner)
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    ok(patch_project(owner, project["id"], {"slug": "aurum-heights-noida"}))
    rows = list_redirects(owner)
    assert [(r["from_path"], r["to_path"], r["origin"]) for r in rows] == [
        ("/projects/aurum-heights", "/projects/aurum-heights-noida", "project")
    ]


def test_publishing_claims_the_path(owner: SignedIn, qr_present: None) -> None:
    ok(create_redirect(owner, "/projects/aurum-heights", "/projects"), 201)
    project = new_project(owner)
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    assert list_redirects(owner) == []
