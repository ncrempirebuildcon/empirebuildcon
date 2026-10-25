"""Posts: create with a cover, author and tags; edit, archive, delete only never-published
drafts; publish keeps the first date; the cover is a media link (a cover in use can't be
deleted from the library); sample posts can't go live in production."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import POSTS, create_post
from empire_api.content import page_rules
from empire_api.content.models import Post
from empire_api.media.models import MediaLink
from media_support import document, photo, signed_as
from projects_support import audit_rows, events, ok


def patch_post(signed: SignedIn, post_id: str, body: dict[str, object]) -> object:
    return signed.client.patch(f"{POSTS}/{post_id}", json=body, headers=signed.headers())


def test_create_with_cover_author_and_tags(owner: SignedIn, db: Session) -> None:
    cover = photo(owner)
    post = create_post(
        owner, cover_media_id=cover["id"], category="RERA & legal", tags=["RERA", "Guide"]
    )
    assert (
        post["slug"] == "how-to-check-a-project" and post["path"] == "/blog/how-to-check-a-project"
    )
    assert post["cover"]["id"] == cover["id"] and post["author"]["id"] == str(owner.user.id)
    assert post["tags"] == ["RERA", "Guide"] and post["publish_state"] == "draft"
    link = db.scalar(select(MediaLink).where(MediaLink.post_id == post["id"]))
    assert link is not None and link.role == "cover"
    assert len(audit_rows(db, "post.created")) == 1
    rows = ok(owner.client.get(POSTS, params={"category": "rera & legal"}))["items"]
    assert [row["id"] for row in rows] == [post["id"]] and "body" not in rows[0]


def test_post_validation(owner: SignedIn) -> None:
    for body, field in (
        ({"title": "T", "body": "<p>x</p>"}, "body"),
        ({"title": "T", "body": "x", "tags": ["a", "A"]}, "tags"),
        ({"title": "T", "body": "x", "tags": [f"t{n}" for n in range(11)]}, "tags"),
        ({"title": "T", "body": "x", "excerpt": "e" * 301}, "excerpt"),
        ({"title": "T", "body": "x", "slug": "Not A Slug"}, "slug"),
        ({"title": "T", "body": "x", "cover_media_id": document(owner)["id"]}, "cover_media_id"),
    ):
        response = owner.client.post(POSTS, json=body, headers=owner.headers())
        assert response.status_code == 422, (body, response.text)
        assert response.json()["errors"][0]["field"].startswith(field), response.text


def test_cover_changes_follow_the_link(owner: SignedIn, db: Session) -> None:
    first, second = photo(owner), photo(owner)
    post = create_post(owner, cover_media_id=first["id"])
    changed = ok(patch_post(owner, post["id"], {"cover_media_id": second["id"]}))
    assert changed["cover"]["id"] == second["id"]
    assert audit_rows(db, "post.updated")[-1].changes["cover_media_id"] == [
        first["id"],
        second["id"],
    ]
    cleared = ok(patch_post(owner, post["id"], {"cover_media_id": None}))
    assert cleared["cover"] is None
    db.expire_all()
    assert db.scalar(select(MediaLink).where(MediaLink.post_id == post["id"])) is None


def test_publish_keeps_the_first_date_and_events(owner: SignedIn, db: Session) -> None:
    post = create_post(owner)
    first = ok(owner.client.post(f"{POSTS}/{post['id']}/publish", headers=owner.headers()))
    assert first["published_at"] is not None
    ok(owner.client.post(f"{POSTS}/{post['id']}/unpublish", headers=owner.headers()))
    again = ok(owner.client.post(f"{POSTS}/{post['id']}/publish", headers=owner.headers()))
    assert again["published_at"] == first["published_at"]
    ok(patch_post(owner, post["id"], {"title": "Checking a project on UP-RERA"}))
    types = [e.type for e in events(db) if e.type.startswith("post.")]
    assert types == ["post.published", "post.unpublished", "post.published", "post.updated"]
    assert events(db, "post.published")[0].payload["path"] == "/blog/how-to-check-a-project"


def test_delete_and_archive(owner: SignedIn) -> None:
    draft = create_post(owner, title="Scratch")
    assert owner.client.delete(f"{POSTS}/{draft['id']}", headers=owner.headers()).status_code == 204
    post = create_post(owner)
    ok(owner.client.post(f"{POSTS}/{post['id']}/publish", headers=owner.headers()))
    assert owner.client.delete(f"{POSTS}/{post['id']}", headers=owner.headers()).status_code == 409
    archived = ok(patch_post(owner, post["id"], {"publish_state": "archived"}))
    assert archived["publish_state"] == "archived"


def test_permissions(app: FastAPI, owner: SignedIn) -> None:
    post = create_post(owner)
    sales = signed_as(app, "sales")
    assert sales.client.get(POSTS).status_code == 403
    publish = sales.client.post(f"{POSTS}/{post['id']}/publish", headers=sales.headers())
    assert publish.status_code == 403
    marketing = signed_as(app, "marketing")
    assert ok(marketing.client.get(f"{POSTS}/{post['id']}"))["id"] == post["id"]


def test_sample_posts_cant_be_published_in_production(
    owner: SignedIn, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    post = create_post(owner)
    row = db.get(Post, post["id"])
    assert row is not None
    row.is_sample = True
    db.commit()
    monkeypatch.setattr(page_rules, "is_production", lambda: True)
    refused = owner.client.post(f"{POSTS}/{post['id']}/publish", headers=owner.headers())
    assert refused.status_code == 409


def test_seo_on_posts(owner: SignedIn) -> None:
    post = create_post(owner)
    assert {w["code"] for w in post["seo_warnings"]} == {"title_missing", "description_missing"}
    image = photo(owner)
    saved = ok(
        patch_post(
            owner, post["id"], {"seo": {"title": "Check a project", "og_image_id": image["id"]}}
        )
    )
    assert saved["seo"]["og_image_id"] == image["id"]
    assert saved["og_image"]["id"] == image["id"]
