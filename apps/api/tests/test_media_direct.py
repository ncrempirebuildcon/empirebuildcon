"""Direct uploads (videos and documents): upload signatures, the fake store's Cloudinary-shaped
upload, and confirm with its intent rules (same user, unused, unexpired) and the store's own
record of the file (type, format, version, size)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.integrations.outbox_drain import drain
from empire_api.media.fake_store import FAKE_API_SECRET
from empire_api.media.models import Media, UploadIntent
from empire_api.media.signing import reply_signature
from empire_api.timeutil import utcnow
from media_support import (
    DOCX,
    MP4,
    PDF,
    confirm,
    direct_reply,
    fake_store,
    image_bytes,
    media_files,
    signature,
    signed_as,
    store_upload,
)
from projects_support import add_configuration, create_project, events, get_project, ok

# --- Signatures ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kind", "filename", "mime", "resource_type", "suffix"),
    [
        ("video", "walkthrough.MP4", "video/mp4", "video", ""),
        ("video", "tour.mov", "video/quicktime", "video", ""),
        ("video", "clip.webm", "video/webm", "video", ""),
        ("document", "Brochure 2026.pdf", "application/pdf", "image", ""),
        ("document", "price list.docx", "", "raw", ".docx"),
        ("document", "deck.pptx", "application/octet-stream", "raw", ".pptx"),
        ("document", "old.doc", "application/msword", "raw", ".doc"),
        ("document", "old.ppt", "application/vnd.ms-powerpoint", "raw", ".ppt"),
    ],
)
def test_signature_for_each_allowed_type(
    owner: SignedIn,
    db: Session,
    kind: str,
    filename: str,
    mime: str,
    resource_type: str,
    suffix: str,
) -> None:
    body = ok(signature(owner, kind, filename, 1234, mime))
    assert body["resource_type"] == resource_type
    assert body["folder"] == f"empire/test/{kind}"
    assert body["public_id"].endswith(suffix) and "Brochure" not in body["public_id"]
    assert body["upload_url"] == f"http://localhost:3000/api/v1/dev-media/upload/{resource_type}"
    assert body["fields"]["public_id"] == body["public_id"]
    assert body["fields"]["signature"] == body["signature"]
    assert body["max_bytes"] == (100 if kind == "video" else 10) * 1024 * 1024
    intent = db.scalar(select(UploadIntent))
    assert intent is not None and intent.public_id == f"{body['folder']}/{body['public_id']}"
    assert intent.created_by == owner.user.id and intent.used_at is None
    assert timedelta(minutes=59) < intent.expires_at - utcnow() <= timedelta(minutes=60)


@pytest.mark.parametrize(
    ("kind", "filename", "size", "mime", "status"),
    [
        ("video", "clip.avi", 10, "video/x-msvideo", 415),
        ("video", "clip.mp4", 10, "video/webm", 415),
        ("video", "clip", 10, "video/mp4", 415),
        ("document", "notes.txt", 10, "text/plain", 415),
        ("document", "brochure.pdf", 10, "", 415),  # PDFs must say they are PDFs
        ("document", "page.html", 10, "text/html", 415),
        ("document", "logo.svg", 10, "image/svg+xml", 415),
        ("video", "big.mp4", 100 * 1024 * 1024 + 1, "video/mp4", 413),
        ("document", "big.pdf", 10 * 1024 * 1024 + 1, "application/pdf", 413),
        ("image", "a.png", 10, "image/png", 422),
        ("document", "a.pdf", 0, "application/pdf", 422),
    ],
)
def test_signature_refusals(
    owner: SignedIn, db: Session, kind: str, filename: str, size: int, mime: str, status: int
) -> None:
    response = signature(owner, kind, filename, size, mime)
    assert response.status_code == status, response.text
    assert db.scalar(select(UploadIntent.id)) is None


# --- Direct upload and confirm ---------------------------------------------------------------


def test_direct_upload_and_confirm(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    sig, reply = direct_reply(owner)
    assert reply["public_id"] == f"{sig['folder']}/{sig['public_id']}"
    assert reply["format"] == "pdf" and reply["resource_type"] == "image"
    body = ok(
        confirm(
            owner, reply, title="Brochure", attach_to=f"project:{project['id']}", role="brochure"
        ),
        201,
    )
    assert body["kind"] == "document" and body["format"] == "pdf" and body["bytes"] == len(PDF)
    assert body["thumbnail_url"] is None  # the fake store makes no PDF thumbnails
    assert get_project(owner, project["id"])["brochure"]["id"] == body["id"]
    intent = db.scalar(select(UploadIntent))
    assert intent is not None and intent.used_at is not None


def test_video_and_office_files_go_through_too(owner: SignedIn) -> None:
    _, video = direct_reply(owner, "video", "tour.mp4", MP4, "video/mp4")
    saved = ok(confirm(owner, video, title="Tour"), 201)
    assert (saved["kind"], saved["format"]) == ("video", "mp4")
    _, office = direct_reply(owner, "document", "price.docx", DOCX, "")
    saved = ok(confirm(owner, office), 201)
    assert (saved["kind"], saved["format"]) == ("document", "docx")
    assert saved["title"].startswith("Document ")
    assert saved["url"].endswith(".docx")


def test_confirm_trusts_the_store_not_the_reply(owner: SignedIn) -> None:
    _, reply = direct_reply(owner)
    tampered = {**reply, "bytes": 1, "format": "exe", "resource_type": "raw"}
    body = ok(confirm(owner, tampered), 201)
    assert (body["bytes"], body["format"]) == (len(PDF), "pdf")


def test_invariant_another_user_cannot_confirm_my_upload(app: FastAPI, owner: SignedIn) -> None:
    _, reply = direct_reply(owner)
    other = signed_as(app, "content_editor")
    response = confirm(other, reply)
    assert response.status_code == 422
    assert "doesn't match one you started" in response.json()["detail"]
    assert confirm(owner, reply).status_code == 201  # still mine to confirm


def test_invariant_a_reply_is_confirmed_once(owner: SignedIn, db: Session) -> None:
    _, reply = direct_reply(owner)
    assert confirm(owner, reply).status_code == 201
    again = confirm(owner, reply)
    assert again.status_code == 422 and "already been saved" in again.json()["detail"]
    assert len(list(db.scalars(select(Media.id)))) == 1


def test_an_expired_intent_is_refused_and_its_file_destroyed(owner: SignedIn, db: Session) -> None:
    _, reply = direct_reply(owner)
    db.execute(update(UploadIntent).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    before = len(media_files())
    response = confirm(owner, reply)
    assert response.status_code == 422 and "an hour" in response.json()["detail"]
    discarded = events(db, "media.upload_discarded")
    # Now, and again once the signature has died (a second upload with it is destroyed too).
    assert [e.payload["reason"] for e in discarded] == ["expired", "expired"]
    drain()
    assert len(media_files()) == before - 1
    assert confirm(owner, reply).status_code == 422  # used now


def test_a_forged_or_unsigned_reply_is_refused(owner: SignedIn) -> None:
    _, reply = direct_reply(owner)
    for broken in (
        {**reply, "signature": "0" * 40},
        {**reply, "version": reply["version"] + 1},
        {k: v for k, v in reply.items() if k != "signature"},
        {"public_id": reply["public_id"]},
        {},
    ):
        response = confirm(owner, broken)
        assert response.status_code == 422, broken
        assert response.json()["errors"][0]["field"] == "cloudinary_response"


def test_a_reply_for_a_public_id_nobody_signed_is_refused(owner: SignedIn) -> None:
    public_id = "empire/test/document/01234567-89ab-cdef-0123-456789abcdef"
    fake_store().save("image", public_id, "pdf", PDF)
    version = fake_store().lookup("image", public_id).version  # type: ignore[union-attr]
    reply = {
        "public_id": public_id,
        "version": version,
        "signature": reply_signature(public_id, version, FAKE_API_SECRET, "sha1"),
    }
    assert confirm(owner, reply).status_code == 422


def test_wrong_type_at_the_store_is_refused_and_destroyed(owner: SignedIn, db: Session) -> None:
    """The intent is for a PDF; the store holds something else under that id."""
    sig = ok(signature(owner, "document", "b.pdf", 100, "application/pdf"))
    public_id = f"{sig['folder']}/{sig['public_id']}"
    asset = fake_store().save("image", public_id, "png", image_bytes())
    reply = {
        "public_id": public_id,
        "version": asset.version,
        "signature": reply_signature(public_id, asset.version, FAKE_API_SECRET, "sha1"),
    }
    response = confirm(owner, reply)
    assert response.status_code == 422 and "isn't the type" in response.json()["detail"]
    assert {e.payload["reason"] for e in events(db, "media.upload_discarded")} == {"refused"}
    drain()
    assert fake_store().lookup("image", public_id) is None


def test_over_the_limit_at_the_store_is_refused_and_destroyed(owner: SignedIn, db: Session) -> None:
    _, reply = direct_reply(owner)
    db.execute(update(UploadIntent).values(max_bytes=10))
    db.commit()
    response = confirm(owner, reply)
    assert response.status_code == 422 and "larger than" in response.json()["detail"]
    drain()
    assert fake_store().lookup("image", reply["public_id"]) is None


def test_a_bad_attach_leaves_the_upload_confirmable(owner: SignedIn) -> None:
    project = create_project(owner)
    _, reply = direct_reply(owner, "document", "list.docx", DOCX, "")
    wrong = confirm(owner, reply, attach_to=f"project:{project['id']}", role="brochure")
    assert wrong.status_code == 422 and "PDF" in wrong.json()["detail"]
    half = confirm(owner, reply, attach_to=f"project:{project['id']}")
    assert half.status_code == 422  # attach_to without role
    body = ok(confirm(owner, reply, attach_to=f"project:{project['id']}", role="document"), 201)
    assert get_project(owner, project["id"])["documents"][0]["id"] == body["id"]


def test_floor_plan_pdf_on_a_configuration(owner: SignedIn) -> None:
    project = create_project(owner)
    configuration = add_configuration(owner, project["id"])
    _, reply = direct_reply(owner)
    ok(
        confirm(owner, reply, attach_to=f"configuration:{configuration['id']}", role="floor_plan"),
        201,
    )
    plans = get_project(owner, project["id"])["configurations"][0]["floor_plans"]
    assert [p["role"] for p in plans] == ["floor_plan"]


def test_store_upload_with_a_tampered_field_fails_like_cloudinary(owner: SignedIn) -> None:
    sig = ok(signature(owner, "document", "a.pdf", len(PDF), "application/pdf"))
    response = store_upload(owner, sig, PDF, public_id="something-else")
    assert response.status_code == 401
    assert response.json() == {"error": {"message": "Invalid Signature"}}
