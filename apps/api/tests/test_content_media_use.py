"""Media in use by content: a library item can't be deleted while page blocks, post covers,
page or post share images, offer images or testimonial photos use it; `attached_count` and
GET /admin/media/{id}/usage say where; content links can't be changed through the media-links
endpoints; `unattached` leaves them out."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    OFFERS,
    POSTS,
    block,
    create_offer,
    create_page,
    create_post,
    create_testimonial,
    patch_page,
    publish_page,
    put_blocks,
)
from empire_api.media.models import MediaLink
from media_support import MEDIA, patch_link, photo, reorder
from projects_support import create_project, events, ok


def delete(signed: SignedIn, media_id: str) -> Any:
    return signed.client.delete(f"{MEDIA}/{media_id}", headers=signed.headers())


def media_row(signed: SignedIn, media_id: str) -> Any:
    rows = ok(signed.client.get(MEDIA, params={"per_page": 100}))["items"]
    return next(row for row in rows if row["id"] == media_id)


def test_every_content_use_blocks_deletion_and_is_listed(owner: SignedIn) -> None:
    uses = {
        "block": photo(owner),
        "cover": photo(owner),
        "page share image": photo(owner),
        "offer image": photo(owner),
        "testimonial photo": photo(owner),
    }
    page = create_page(owner, title="Home sweet home")
    ok(put_blocks(owner, page["id"], [block("image", {"image_id": uses["block"]["id"]})]))
    create_post(owner, cover_media_id=uses["cover"]["id"])
    ok(patch_page(owner, page["id"], {"seo": {"og_image_id": uses["page share image"]["id"]}}))
    create_offer(owner, image_media_id=uses["offer image"]["id"])
    create_testimonial(owner, photo_media_id=uses["testimonial photo"]["id"])
    expected = {
        "block": ("page", "block"),
        "cover": ("post", "cover"),
        "page share image": ("page", "share_image"),
        "offer image": ("offer", "image"),
        "testimonial photo": ("testimonial", "photo"),
    }
    for what, item in uses.items():
        refused = delete(owner, item["id"])
        assert refused.status_code == 409, what
        assert "used in 1 place" in refused.json()["detail"], refused.json()["detail"]
        usage = ok(owner.client.get(f"{MEDIA}/{item['id']}/usage"))
        assert [(u["owner_type"], u["role"]) for u in usage] == [expected[what]], what
        assert media_row(owner, item["id"])["attached_count"] == 1, what
    assert (
        "page “Home sweet home” (page block)" in delete(owner, uses["block"]["id"]).json()["detail"]
    )


def test_a_freed_file_can_be_deleted(owner: SignedIn) -> None:
    item = photo(owner)
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("gallery", {"image_ids": [item["id"]]})]))
    assert delete(owner, item["id"]).status_code == 409
    ok(put_blocks(owner, page["id"], []))
    assert ok(owner.client.get(f"{MEDIA}/{item['id']}/usage")) == []
    assert delete(owner, item["id"]).status_code == 204


def test_project_uses_are_listed_too(owner: SignedIn) -> None:
    project = create_project(owner)
    item = photo(owner, attach_to=f"project:{project['id']}", role="gallery")
    usage = ok(owner.client.get(f"{MEDIA}/{item['id']}/usage"))
    assert usage == [
        {
            "owner_type": "project",
            "owner_id": project["id"],
            "project_id": project["id"],
            "name": "Aurum Heights",
            "role": "gallery",
        }
    ]


def test_unattached_filter_leaves_content_uses_out(owner: SignedIn) -> None:
    used, free = photo(owner), photo(owner)
    create_offer(owner, image_media_id=used["id"])
    rows = ok(owner.client.get(MEDIA, params={"unattached": True}))["items"]
    assert [row["id"] for row in rows] == [free["id"]]


def test_content_links_cant_be_changed_from_the_media_endpoints(
    owner: SignedIn, db: Session
) -> None:
    item = photo(owner)
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("image", {"image_id": item["id"]})]))
    link = db.scalar(select(MediaLink).where(MediaLink.page_id == page["id"]))
    assert link is not None
    hide = patch_link(owner, str(link.id), is_visible=False)
    assert hide.status_code == 409 and "page or post editor" in hide.json()["detail"]
    assert reorder(owner, [str(link.id)]).status_code == 409
    detach = owner.client.delete(f"/api/v1/admin/media-links/{link.id}", headers=owner.headers())
    assert detach.status_code == 409
    attach = owner.client.post(
        "/api/v1/admin/media-links",
        json={"media_id": item["id"], "attach_to": f"page:{page['id']}", "role": "gallery"},
        headers=owner.headers(),
    )
    assert attach.status_code == 422


def test_label_of_a_block_photo_cant_be_removed(owner: SignedIn) -> None:
    item = photo(owner)
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("image", {"image_id": item["id"]})]))
    removed = owner.client.patch(
        f"{MEDIA}/{item['id']}", json={"label": None}, headers=owner.headers()
    )
    assert removed.status_code == 409


def test_deleting_a_page_frees_its_files(owner: SignedIn) -> None:
    item = photo(owner)
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("image", {"image_id": item["id"]})]))
    assert (
        owner.client.delete(
            f"/api/v1/admin/pages/{page['id']}", headers=owner.headers()
        ).status_code
        == 204
    )
    assert delete(owner, item["id"]).status_code == 204


def relabel(signed: SignedIn, media_id: str, label: str | None) -> Any:
    return signed.client.patch(
        f"{MEDIA}/{media_id}", json={"label": label}, headers=signed.headers()
    )


def test_relabelling_a_file_revalidates_live_content_that_shows_it(
    owner: SignedIn, db: Session
) -> None:
    """L2: a relabel ("actual photo" → "artist's impression") must reach the website at once."""
    shown, cover, offer_image, person = photo(owner), photo(owner), photo(owner), photo(owner)
    live_page, draft_page = create_page(owner, title="Live"), create_page(owner, title="Draft")
    for page in (live_page, draft_page):
        ok(put_blocks(owner, page["id"], [block("image", {"image_id": shown["id"]})]))
    ok(publish_page(owner, live_page["id"]))
    post = create_post(owner, cover_media_id=cover["id"])
    ok(owner.client.post(f"{POSTS}/{post['id']}/publish", headers=owner.headers()))
    offer = create_offer(owner, image_media_id=offer_image["id"], is_active=True)
    assert offer["state"] == "live"
    testimonial = create_testimonial(
        owner, photo_media_id=person["id"], consent_date="2026-03-02", is_visible=True
    )
    expected = (
        (shown, "page.updated", live_page["id"]),
        (cover, "post.updated", post["id"]),
        (offer_image, "offer.changed", offer["id"]),
        (person, "testimonial.changed", testimonial["id"]),
    )
    for item, type_, owner_id in expected:
        before = len(events(db, type_))
        ok(relabel(owner, item["id"], "artist_impression"))
        sent = events(db, type_)[before:]
        assert [str(e.aggregate_id) for e in sent] == [owner_id], type_
        assert sent[0].payload["media_id"] == item["id"], type_
    page_events = [e.payload for e in events(db, "page.updated")]
    assert page_events[-1]["changed"] == ["media"]
    assert all(e["page_id"] != draft_page["id"] for e in page_events)  # drafts aren't live


def test_testimonial_uses_are_named_by_initials(owner: SignedIn) -> None:
    """L9: anyone with media.upload sees where a file is used; the buyer's name stays out."""
    item = photo(owner)
    create_testimonial(owner, person_name="Ravi Kumar Sharma", photo_media_id=item["id"])
    usage = ok(owner.client.get(f"{MEDIA}/{item['id']}/usage"))
    assert [u["name"] for u in usage] == ["Testimonial photo (R. K. S.)"]
    detail = delete(owner, item["id"]).json()["detail"]
    assert "Testimonial photo (R. K. S.)" in detail and "Sharma" not in detail


def test_post_covers_and_offer_images_need_an_honest_label(owner: SignedIn) -> None:
    """L11: covers and offer images often show renders, so they need a label like block photos.
    Testimonial photos are exempt: they show a person, not a property."""
    unlabelled = photo(owner, label="")
    cover = owner.client.post(
        POSTS,
        json={"title": "Guide", "body": "Text", "cover_media_id": unlabelled["id"]},
        headers=owner.headers(),
    )
    assert cover.status_code == 422 and cover.json()["errors"][0]["field"] == "cover_media_id"
    post = create_post(owner)
    changed = owner.client.patch(
        f"{POSTS}/{post['id']}", json={"cover_media_id": unlabelled["id"]}, headers=owner.headers()
    )
    assert changed.status_code == 422
    image = owner.client.post(
        OFFERS,
        json={"title": "Festive offer", "placement": "banner", "image_media_id": unlabelled["id"]},
        headers=owner.headers(),
    )
    assert image.status_code == 422 and image.json()["errors"][0]["field"] == "image_media_id"
    assert create_testimonial(owner, photo_media_id=unlabelled["id"])["photo"] is not None


def test_the_label_of_a_cover_or_offer_image_cant_be_removed(owner: SignedIn) -> None:
    cover, offer_image, person = photo(owner), photo(owner), photo(owner)
    create_post(owner, cover_media_id=cover["id"])
    create_offer(owner, image_media_id=offer_image["id"])
    create_testimonial(owner, photo_media_id=person["id"])
    assert relabel(owner, cover["id"], None).status_code == 409
    assert relabel(owner, offer_image["id"], None).status_code == 409
    assert ok(relabel(owner, person["id"], None))["label"] is None
