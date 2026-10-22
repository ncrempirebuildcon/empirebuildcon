"""Regression tests for the independent review of Phase 4 part 2 (media). Each test names the
finding it guards; each failed before its fix."""

from __future__ import annotations

import io
from datetime import datetime, timedelta

import pytest
from PIL import Image, PngImagePlugin
from pydantic import SecretStr
from sqlalchemy import select, text, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.config import Settings
from empire_api.db import get_sessionmaker
from empire_api.integrations.outbox_drain import drain
from empire_api.media import queries as media_queries
from empire_api.media import scrub, sniff
from empire_api.media.models import Media, UploadIntent
from empire_api.projects.seed import seed_sample
from empire_api.timeutil import IST, utcnow
from media_support import (
    MEDIA,
    MP4,
    attach,
    big_png,
    confirm,
    direct_reply,
    fake_store,
    image_bytes,
    patch_link,
    photo,
    signature,
    store_upload,
    upload_photo,
)
from projects_support import (
    add_child,
    add_configuration,
    audit_rows,
    create_project,
    events,
    get_project,
    ok,
    patch_project,
)

LABEL_FIRST = "Add an honest label"


# --- 1. Secrets in start-up errors -----------------------------------------------------------


def test_review_1_a_malformed_cloudinary_url_never_shows_its_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "Fake5ecretValueXyz0123456"
    monkeypatch.setenv("CLOUDINARY_URL", f"https://123456789:{secret}@demo")
    with pytest.raises(ValueError, match="CLOUDINARY_URL") as raised:
        Settings()
    shown = str(raised.value) + repr(raised.value)
    assert not _any_part_of(secret, shown) and "123456789" not in shown
    monkeypatch.setenv("CLOUDINARY_URL", f"cloudinary://123456789:{secret}@")
    with pytest.raises(ValueError) as again:
        Settings(app_env="production", session_secret=SecretStr("x"))
    assert not _any_part_of(secret, str(again.value) + repr(again.value))


def _any_part_of(secret: str, shown: str, size: int = 6) -> bool:
    """Whether any `size` consecutive characters of the secret appear (pydantic truncates)."""
    return any(secret[i : i + size] in shown for i in range(len(secret) - size + 1))


# --- 2. Honest labels before a photo goes on the website -------------------------------------


def test_review_2_an_unlabelled_photo_attaches_hidden(owner: SignedIn) -> None:
    project = create_project(owner)
    response = upload_photo(owner, attach_to=f"project:{project['id']}", role="gallery")
    image = ok(response, 201)
    gallery = get_project(owner, project["id"])["gallery"]
    assert [(m["id"], m["is_visible"]) for m in gallery] == [(image["id"], False)]
    assert get_project(owner, project["id"])["cover"] is None
    refused = patch_link(owner, gallery[0]["link_id"], is_visible=True)
    assert refused.status_code == 422 and LABEL_FIRST in refused.json()["detail"]
    assert refused.json()["errors"][0]["field"] == "is_visible"
    labelled = owner.client.patch(
        f"{MEDIA}/{image['id']}", json={"label": "actual_photo"}, headers=owner.headers()
    )
    ok(labelled)
    assert ok(patch_link(owner, gallery[0]["link_id"], is_visible=True))["is_visible"] is True


def test_review_2_attaching_an_unlabelled_image_hides_it(owner: SignedIn) -> None:
    project = create_project(owner)
    update_ = add_child(
        owner, project["id"], "construction-updates", {"title": "Slab", "update_date": "2026-09-30"}
    )
    for target in (f"project:{project['id']}", f"construction_update:{update_['id']}"):
        bare = photo(owner, label="")
        link = ok(attach(owner, bare["id"], target, "gallery", is_visible=True), 201)
        assert link["is_visible"] is False, target


def test_review_2_labelled_photos_and_other_roles_attach_visible(owner: SignedIn) -> None:
    project = create_project(owner)
    labelled = ok(
        upload_photo(
            owner, attach_to=f"project:{project['id']}", role="gallery", label="artist_impression"
        ),
        201,
    )
    assert get_project(owner, project["id"])["cover"]["id"] == labelled["id"]
    configuration = add_configuration(owner, project["id"])
    plan = ok(
        attach(
            owner,
            photo(owner, label="")["id"],
            f"configuration:{configuration['id']}",
            "floor_plan",
        ),
        201,
    )
    assert plan["is_visible"] is True  # a floor plan is a drawing, not a photo of the building


def test_review_2_removing_the_label_of_a_visible_photo_is_409(owner: SignedIn) -> None:
    project = create_project(owner)
    image = photo(owner, attach_to=f"project:{project['id']}", role="gallery", label="actual_photo")
    url = f"{MEDIA}/{image['id']}"
    refused = owner.client.patch(url, json={"label": None}, headers=owner.headers())
    assert refused.status_code == 409 and LABEL_FIRST in refused.json()["detail"]
    link = get_project(owner, project["id"])["gallery"][0]
    ok(patch_link(owner, link["link_id"], is_visible=False))
    assert (
        ok(owner.client.patch(url, json={"label": None}, headers=owner.headers()))["label"] is None
    )


def test_review_2_sample_media_is_exempt(owner: SignedIn, db: Session) -> None:
    from empire_api.media.seed import seed_sample_media  # noqa: PLC0415

    seed_sample(db)
    seed_sample_media(db)
    db.commit()
    sample = db.scalar(select(Media).where(Media.is_sample.is_(True)))
    assert sample is not None and sample.label is None
    project = create_project(owner)
    link = ok(attach(owner, str(sample.id), f"project:{project['id']}", "gallery"), 201)
    assert link["is_visible"] is True


# --- 3. Decompression bombs --------------------------------------------------------------------


def test_review_3_a_decompression_bomb_is_422_not_500(owner: SignedIn) -> None:
    bomb = big_png(14000, 14000)  # ~200 megapixels declared, a few kilobytes on disk
    assert len(bomb) < 100_000
    with pytest.raises(sniff.TooManyPixelsError):
        sniff.inspect_image(bomb)
    response = upload_photo(owner, bomb)
    assert response.status_code == 422 and "megapixels" in response.json()["detail"]


# --- 4. Orphans at the store -------------------------------------------------------------------


def test_review_4_a_discard_destroys_every_resource_type(owner: SignedIn, db: Session) -> None:
    """The resource type in the upload URL isn't signed: a video signature can store raw."""
    sig = ok(signature(owner, "video", "tour.mp4", len(MP4), "video/mp4"))
    raw_sig = {**sig, "upload_url": sig["upload_url"].replace("/upload/video", "/upload/raw")}
    reply = ok(store_upload(owner, raw_sig, MP4))
    assert reply["resource_type"] == "raw"
    assert fake_store().lookup("raw", reply["public_id"]) is not None
    assert confirm(owner, reply).status_code == 422
    drain()
    assert fake_store().lookup("raw", reply["public_id"]) is None


def test_review_4_a_refused_upload_is_destroyed_again_after_the_signature_dies(
    owner: SignedIn, db: Session
) -> None:
    sig, reply = direct_reply(owner)
    db.execute(update(UploadIntent).values(max_bytes=10))  # make confirm refuse it
    db.commit()
    assert confirm(owner, reply).status_code == 422
    intent = db.scalar(select(UploadIntent))
    assert intent is not None
    later = [e for e in events(db, "media.upload_discarded") if e.available_at > utcnow()]
    assert len(later) == 1
    assert later[0].available_at >= intent.created_at + timedelta(hours=1)
    drain()
    assert fake_store().lookup("image", reply["public_id"]) is None
    ok(store_upload(owner, sig, b"%PDF-1.4\n%%EOF\n"))  # re-uploaded with the live signature
    assert fake_store().lookup("image", reply["public_id"]) is not None
    drain(now=utcnow() + timedelta(minutes=75))
    assert fake_store().lookup("image", reply["public_id"]) is None


# --- 5. Race on the share image ------------------------------------------------------------------


def test_review_5_the_share_image_check_holds_a_share_lock(owner: SignedIn) -> None:
    image = photo(owner)
    reader, writer = get_sessionmaker()(), get_sessionmaker()()
    try:
        assert media_queries.is_library_image(reader, image["id"])  # transaction stays open
        with pytest.raises(OperationalError):
            writer.execute(
                text("SELECT id FROM media WHERE id = :id FOR UPDATE NOWAIT"), {"id": image["id"]}
            )
    finally:
        writer.rollback()
        reader.rollback()
        writer.close()
        reader.close()


def test_review_5_a_dangling_share_image_is_cleared_not_fatal(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    image = photo(owner)
    ok(patch_project(owner, project["id"], {"seo": {"og_image_id": image["id"]}}))
    db.execute(text("DELETE FROM media WHERE id = :id"), {"id": image["id"]})  # the race's result
    db.commit()
    view = ok(patch_project(owner, project["id"], {"tagline": "Still editable"}))
    assert view["seo"]["og_image_id"] is None and view["og_image"] is None
    note = audit_rows(db, "project.updated")[-1].changes
    assert note["seo.og_image_id"][0] == image["id"]
    assert "deleted from the library" in note["note"][1]


# --- 6. Trailing bytes after the image ---------------------------------------------------------


TRAILER = b"<html><script>alert(1)</script></html>PK\x03\x04" + b"\x00" * 30


@pytest.mark.parametrize("fmt", ["JPEG", "PNG", "WEBP"])
def test_review_6_bytes_after_the_image_are_cut_off(fmt: str) -> None:
    clean_bytes = image_bytes(fmt)
    result = scrub.strip_metadata(clean_bytes + TRAILER, sniff.inspect_image(clean_bytes))
    assert result.data == clean_bytes and result.changed


def test_review_6_progressive_jpegs_keep_every_scan() -> None:
    out = io.BytesIO()
    Image.new("RGB", (64, 48), "teal").save(out, format="JPEG", progressive=True)
    data = out.getvalue()
    assert scrub.strip_metadata(data, sniff.inspect_image(data)).data is data


def test_review_6_unknown_png_chunks_and_avif_are_re_encoded() -> None:
    info = PngImagePlugin.PngInfo()
    info.add(b"prVt", b"hidden payload")
    out = io.BytesIO()
    Image.new("RGB", (8, 8), "red").save(out, format="PNG", pnginfo=info)
    result = scrub.strip_metadata(out.getvalue(), sniff.inspect_image(out.getvalue()))
    assert result.changed and b"hidden payload" not in result.data
    avif = image_bytes("AVIF")
    assert scrub.strip_metadata(avif, sniff.inspect_image(avif)).changed


def test_review_6_the_store_never_gets_the_trailer(owner: SignedIn) -> None:
    body = ok(upload_photo(owner, image_bytes("JPEG") + TRAILER, content_type="image/jpeg"), 201)
    path = fake_store().path_for_key(body["url"].split("/dev-media/files/", 1)[1])
    assert path is not None and b"<script>" not in path.read_bytes()


# --- 7. Intent lifetime --------------------------------------------------------------------------


def test_review_7_an_upload_can_be_confirmed_for_an_hour(owner: SignedIn, db: Session) -> None:
    ok(signature(owner, "video", "long.mp4", 90 * 1024 * 1024, "video/mp4"))
    intent = db.scalar(select(UploadIntent))
    assert intent is not None
    assert timedelta(minutes=59) < intent.expires_at - utcnow() <= timedelta(minutes=60)


# --- 8. Roles nobody can see ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("role", "words"), [("hero", "gallery cover"), ("og_image", "share image")]
)
def test_review_8_hero_and_share_image_links_are_refused(
    owner: SignedIn, role: str, words: str
) -> None:
    project = create_project(owner)
    response = attach(owner, photo(owner)["id"], f"project:{project['id']}", role)
    assert response.status_code == 422 and words in response.json()["detail"]
    upload = upload_photo(owner, attach_to=f"project:{project['id']}", role=role)
    assert upload.status_code == 422


# --- 9. unattached=true and share images ---------------------------------------------------------


def test_review_9_a_share_image_is_not_unattached(owner: SignedIn) -> None:
    project = create_project(owner)
    image = photo(owner)
    ok(patch_project(owner, project["id"], {"seo": {"og_image_id": image["id"]}}))
    unattached = ok(owner.client.get(MEDIA, params={"unattached": "true"}))["items"]
    assert image["id"] not in [m["id"] for m in unattached]
    listed = ok(owner.client.get(MEDIA))["items"]
    assert [m["attached_count"] for m in listed if m["id"] == image["id"]] == [1]


# --- 10. Future dates ----------------------------------------------------------------------------


def test_review_10_construction_updates_report_the_past(owner: SignedIn) -> None:
    project = create_project(owner)
    today = datetime.now(IST).date()
    url = f"/api/v1/admin/projects/{project['id']}/construction-updates"
    future = {"title": "Next month", "update_date": (today + timedelta(days=1)).isoformat()}
    refused = owner.client.post(url, json=future, headers=owner.headers())
    assert refused.status_code == 422
    assert refused.json()["errors"][0]["field"] == "update_date"
    same_day = {"title": "Today", "update_date": today.isoformat()}
    assert owner.client.post(url, json=same_day, headers=owner.headers()).status_code == 201
