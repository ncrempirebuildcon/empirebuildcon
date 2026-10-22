"""Photos through the API (POST /admin/media/images): magic bytes decide, a hard 10 MB cap while
streaming, 25 megapixels, attach in the same step, checks before anything is uploaded, the
uploaded file destroyed again when saving fails, permissions and the shared rate limit."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn, new_client
from empire_api.media import routes as media_routes
from empire_api.media import uploads
from empire_api.media.models import Media
from empire_api.media.vocab import MAX_IMAGE_BYTES
from media_support import (
    PDF,
    big_png,
    image_bytes,
    media_files,
    photo,
    signature,
    signed_as,
    upload_photo,
)
from projects_support import add_configuration, audit_rows, create_project, events, get_project, ok

# --- Photos ----------------------------------------------------------------------------------


def test_photo_upload_saves_the_store_record(owner: SignedIn, db: Session) -> None:
    before = len(media_files())
    body = photo(
        owner, title="Clubhouse at dusk", alt_text="The clubhouse lit up at dusk", label=""
    )
    assert body["kind"] == "image" and body["format"] == "png"
    assert (body["width"], body["height"]) == (16, 12)
    assert body["title"] == "Clubhouse at dusk"
    assert body["label"] is None and body["attached_count"] == 0 and not body["is_sample"]
    assert body["url"].startswith("http://localhost:3000/api/v1/dev-media/files/image/empire/test/")
    row = db.get(Media, body["id"])
    assert row is not None and row.store == "fake" and row.created_by == owner.user.id
    # SECURITY: generated public id, never the filename (SECURITY.md §6).
    assert row.public_id.startswith("empire/test/image/") and "photo" not in row.public_id
    assert len(media_files()) == before + 1
    assert [e.payload["change"] for e in events(db, "media.added")] == ["uploaded"]
    assert len(audit_rows(db, "media.uploaded")) == 1


def test_the_file_decides_not_its_name_or_type(owner: SignedIn) -> None:
    response = upload_photo(
        owner, image_bytes("WEBP"), filename="holiday.jpg", content_type="image/jpeg"
    )
    assert ok(response, 201)["format"] == "webp"


@pytest.mark.parametrize(
    ("data", "words"),
    [
        (b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>", "SVG"),
        (b"\x00\x00\x00\x18ftypheic\x00\x00\x00\x00mif1heic" + b"\x00" * 40, "HEIC"),
        (b"GIF89a" + b"\x00" * 40, "GIF"),
        (b"\xff\xd8\xff<html>not really a jpeg</html>", "damaged"),
        (PDF, "isn't a JPEG"),
    ],
)
def test_refused_files_get_415_and_nothing_is_stored(
    owner: SignedIn, data: bytes, words: str
) -> None:
    before = media_files()
    response = upload_photo(owner, data, filename="photo.png", content_type="image/png")
    assert response.status_code == 415, response.text
    assert words in response.json()["detail"]
    assert response.json()["errors"][0]["field"] == "file"
    assert media_files() == before


def test_photo_over_10_mb_is_413_from_content_length(owner: SignedIn) -> None:
    response = upload_photo(owner, b"\xff\xd8\xff" + b"\x00" * (MAX_IMAGE_BYTES + 1))
    assert response.status_code == 413
    assert "10 MB" in response.json()["detail"]


def test_photo_over_10_mb_is_413_while_streaming_without_content_length(owner: SignedIn) -> None:
    boundary = "media-test-boundary"

    def body() -> Iterator[bytes]:
        yield (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n'
            "Content-Type: image/png\r\n\r\n"
        ).encode()
        chunk = b"\x00" * (1024 * 1024)
        for _ in range(12):
            yield chunk
        yield f"\r\n--{boundary}--\r\n".encode()

    response = owner.client.post(
        "/api/v1/admin/media/images",
        content=body(),
        headers={**owner.headers(), "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 413


def test_a_cut_off_body_is_400_not_a_missing_file(owner: SignedIn) -> None:
    boundary = "cut"
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + image_bytes()[:30]
    response = owner.client.post(
        "/api/v1/admin/media/images",
        content=body,
        headers={**owner.headers(), "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    assert response.status_code == 400
    assert "incomplete" in response.json()["detail"]


def test_more_than_25_megapixels_is_422(owner: SignedIn) -> None:
    response = upload_photo(owner, big_png(6000, 5000))
    assert response.status_code == 422
    assert "25 megapixels" in response.json()["detail"]


def test_upload_and_attach_in_one_step(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    body = photo(owner, attach_to=f"project:{project['id']}", role="gallery")
    view = get_project(owner, project["id"])
    assert [m["id"] for m in view["gallery"]] == [body["id"]]
    assert view["cover"]["id"] == body["id"]
    assert view["gallery"][0]["attached_count"] == 1
    assert len(audit_rows(db, "media_link.attached")) == 1


@pytest.mark.parametrize(
    ("fields", "status", "field"),
    [
        ({"role": "gallery"}, 422, "role"),
        ({"attach_to": "project:not-a-uuid", "role": "gallery"}, 422, "attach_to"),
        ({"attach_to": "tower:00000000-0000-0000-0000-000000000000", "role": "gallery"}, 422, None),
        ({"label": "progress_photo"}, 422, "label_month"),
        ({"title": "x" * 161}, 422, "title"),
        ({"label_month": "2026-13-01", "label": "actual_photo"}, 422, "label_month"),
    ],
)
def test_bad_fields_are_refused_before_uploading(
    owner: SignedIn, fields: dict[str, str], status: int, field: str | None
) -> None:
    before = media_files()
    response = upload_photo(owner, **fields)
    assert response.status_code == status, response.text
    if field:
        assert field in {e["field"] for e in response.json()["errors"]}
    assert media_files() == before


def test_wrong_owner_or_role_is_refused_before_uploading(owner: SignedIn) -> None:
    project = create_project(owner)
    configuration = add_configuration(owner, project["id"])
    before = media_files()
    missing = upload_photo(
        owner, attach_to="project:00000000-0000-0000-0000-000000000000", role="gallery"
    )
    assert missing.status_code == 404
    wrong_role = upload_photo(
        owner, attach_to=f"configuration:{configuration['id']}", role="gallery"
    )
    assert wrong_role.status_code == 422
    assert "floor_plan" in wrong_role.json()["detail"]
    brochure = upload_photo(owner, attach_to=f"project:{project['id']}", role="brochure")
    assert brochure.status_code == 422 and "PDF" in brochure.json()["detail"]
    assert media_files() == before


def test_a_failed_save_destroys_the_uploaded_file(
    owner: SignedIn, monkeypatch: pytest.MonkeyPatch, db: Session
) -> None:
    before = media_files()

    def broken(*args: object, **kwargs: object) -> None:
        raise RuntimeError("database went away")

    monkeypatch.setattr(uploads, "save_new_media", broken)
    response = upload_photo(owner)
    assert response.status_code == 500
    assert media_files() == before  # the file reached the store and was destroyed again
    assert db.scalar(select(Media.id)) is None


def test_progress_photo_labels_at_upload(owner: SignedIn) -> None:
    body = photo(owner, label="progress_photo", label_month="2026-09-17")
    assert (body["label"], body["label_month"]) == ("progress_photo", "2026-09-01")


@pytest.mark.parametrize("role", ["sales"])
def test_roles_without_media_upload_are_refused(app: FastAPI, role: str) -> None:
    other = signed_as(app, role)
    assert upload_photo(other).status_code == 403
    assert signature(other, "document", "a.pdf", 10, "application/pdf").status_code == 403


def test_marketing_and_content_editors_may_upload(app: FastAPI) -> None:
    for role in ("marketing", "content_editor"):
        assert upload_photo(signed_as(app, role)).status_code == 201


def test_signed_out_and_missing_csrf(app: FastAPI, owner: SignedIn) -> None:
    no_csrf = owner.client.post(
        "/api/v1/admin/media/images", files={"file": ("a.png", image_bytes(), "image/png")}
    )
    assert no_csrf.status_code == 403
    with new_client(app) as anonymous:
        signed_out = anonymous.post(
            "/api/v1/admin/media/images", files={"file": ("a.png", image_bytes(), "image/png")}
        )
        assert signed_out.status_code == 401


def test_uploads_and_signatures_share_one_rate_limit(
    owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(media_routes, "UPLOAD_LIMIT", 2)
    assert upload_photo(owner).status_code == 201
    assert signature(owner, "document", "a.pdf", 10, "application/pdf").status_code == 200
    limited = upload_photo(owner)
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0
    assert signature(owner, "document", "a.pdf", 10, "application/pdf").status_code == 429
