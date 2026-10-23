"""The media library (media/library.py): list and filters, rename / alt text / honest labels,
delete only when unused (with the store copy destroyed by the outbox handler), the SEO share
image check, and the daily clean-up of unconfirmed uploads."""

from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.config import get_settings
from empire_api.integrations.outbox_drain import cleanup, drain
from empire_api.media import handlers
from empire_api.media.models import Media, UploadIntent
from empire_api.media.store import StoreError
from empire_api.platform.models import OutboxEvent
from empire_api.timeutil import IST, utcnow
from media_support import (
    MEDIA,
    direct_reply,
    document,
    photo,
    signature,
    signed_as,
)
from projects_support import (
    audit_rows,
    create_project,
    events,
    get_project,
    ok,
    patch_project,
)


def patch_media(signed: SignedIn, media_id: str, **body: Any) -> Any:
    return signed.client.patch(f"{MEDIA}/{media_id}", json=body, headers=signed.headers())


def delete_media(signed: SignedIn, media_id: str) -> Any:
    return signed.client.delete(f"{MEDIA}/{media_id}", headers=signed.headers())


def files() -> set[Path]:
    return {p for p in Path(get_settings().media_dev_dir).rglob("*") if p.is_file()}


# --- List ------------------------------------------------------------------------------------


def test_list_filters_and_pages(owner: SignedIn) -> None:
    project = create_project(owner)
    used = photo(owner, title="Lobby", attach_to=f"project:{project['id']}", role="gallery")
    spare = photo(owner, title="Pool deck", alt_text="Swimming pool at noon")
    pdf = document(owner, title="Price list")

    def ids(**params: Any) -> list[str]:
        return [m["id"] for m in ok(owner.client.get(MEDIA, params=params))["items"]]

    assert ids() == [pdf["id"], spare["id"], used["id"]]  # newest first
    assert ids(kind="image") == [spare["id"], used["id"]]
    assert ids(q="POOL") == [spare["id"]]
    assert ids(q="noon") == [spare["id"]]  # alt text matches too
    assert ids(q="100%") == []
    assert ids(attached_to=f"project:{project['id']}") == [used["id"]]
    assert ids(unattached="true") == [pdf["id"], spare["id"]]
    paged = ok(owner.client.get(MEDIA, params={"per_page": 2, "page": 2}))
    assert paged["meta"] == {"page": 2, "per_page": 2, "total": 3, "pages": 2}
    listed = ok(owner.client.get(MEDIA))["items"]
    assert [m["attached_count"] for m in listed] == [0, 0, 1]


@pytest.mark.parametrize(
    "params",
    [
        {"attached_to": "project"},
        {"attached_to": "tower:00000000-0000-0000-0000-000000000000"},
        {"kind": "audio"},
        {"q": "x" * 101},
        {"per_page": 101},
    ],
)
def test_list_rejects_bad_filters(owner: SignedIn, params: dict[str, Any]) -> None:
    assert owner.client.get(MEDIA, params=params).status_code == 422


def test_sales_cannot_see_the_library(app: FastAPI) -> None:
    assert signed_as(app, "sales").client.get(MEDIA).status_code == 403


# --- Rename, alt text, labels ----------------------------------------------------------------


def test_rename_alt_text_and_label(owner: SignedIn, db: Session) -> None:
    image = photo(owner, title="IMG_2041")
    body = ok(
        patch_media(
            owner,
            image["id"],
            title="Tower A, September",
            alt_text="Tower A at the ninth floor slab",
            label="progress_photo",
            label_month="2026-09-23",
        )
    )
    assert body["title"] == "Tower A, September"
    assert (body["label"], body["label_month"]) == ("progress_photo", "2026-09-01")
    cleared = ok(patch_media(owner, image["id"], alt_text="  ", label="artist_impression"))
    assert cleared["alt_text"] is None
    assert (cleared["label"], cleared["label_month"]) == ("artist_impression", None)
    assert len(audit_rows(db, "media.updated")) == 2
    assert [e.payload["change"] for e in events(db, "media.updated")] == ["details", "details"]


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"label": "progress_photo"}, "label_month"),
        ({"label_month": "2026-09-01"}, "label_month"),
        ({"label": "artist_impression", "label_month": "2026-09-01"}, "label_month"),
        ({"label": "actual_photo", "label_month": "2999-01-01"}, "label_month"),
        ({"title": None}, "title"),
        ({"title": ""}, "title"),
        ({"alt_text": "x" * 251}, "alt_text"),
        ({"label": "real_photo"}, "label"),
        ({"is_sample": True}, "is_sample"),
    ],
)
def test_label_and_field_rules(owner: SignedIn, body: dict[str, Any], field: str) -> None:
    image = photo(owner, label="")
    response = patch_media(owner, image["id"], **body)
    assert response.status_code == 422, response.text
    assert field in {e["field"] for e in response.json()["errors"]}


def test_this_month_is_allowed_and_a_stored_month_carries_over(owner: SignedIn) -> None:
    image = photo(owner)
    this_month = datetime.now(IST).date().replace(day=1).isoformat()  # IST, like the API
    ok(patch_media(owner, image["id"], label="actual_photo", label_month=this_month))
    moved = ok(patch_media(owner, image["id"], label="progress_photo"))
    assert moved["label_month"] == this_month


def test_documents_have_no_label(owner: SignedIn) -> None:
    pdf = document(owner)
    response = patch_media(owner, pdf["id"], label="actual_photo")
    assert response.status_code == 422 and response.json()["errors"][0]["field"] == "label"


def test_unknown_media_is_404(owner: SignedIn) -> None:
    nobody = "00000000-0000-0000-0000-000000000000"
    assert patch_media(owner, nobody, title="x").status_code == 404
    assert delete_media(owner, nobody).status_code == 404


def test_relabelling_a_photo_on_a_live_project_revalidates_it(
    owner: SignedIn, db: Session, qr_present: None
) -> None:
    from projects_support import make_ready, publish  # noqa: PLC0415

    project = create_project(owner)
    image = photo(owner, attach_to=f"project:{project['id']}", role="gallery")
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    ok(patch_media(owner, image["id"], label="artist_impression"))
    assert events(db, "project.updated")[-1].payload["change"] == "media_details"


# --- Delete ----------------------------------------------------------------------------------


def test_invariant_a_file_in_use_cant_be_deleted(owner: SignedIn) -> None:
    project = create_project(owner)
    image = photo(owner, attach_to=f"project:{project['id']}", role="gallery")
    response = delete_media(owner, image["id"])
    assert response.status_code == 409
    assert "used in 1 place" in response.json()["detail"]


def test_delete_removes_the_row_and_the_handler_destroys_the_file(
    owner: SignedIn, db: Session
) -> None:
    before = files()
    image = photo(owner)
    added = files() - before
    assert len(added) == 1
    assert delete_media(owner, image["id"]).status_code == 204
    assert db.get(Media, image["id"]) is None
    removed = events(db, "media.removed")
    assert removed[0].payload["store"] == "fake"
    assert removed[0].payload["public_id"].startswith("empire/test/image/")
    assert len(audit_rows(db, "media.deleted")) == 1
    drain()  # the request's own drain_soon may already have run; this makes sure
    assert files() == before
    db.expire_all()
    assert db.scalar(select(OutboxEvent.status).where(OutboxEvent.type == "media.removed")) == (
        "delivered"
    )


def test_only_media_manage_may_delete(app: FastAPI, owner: SignedIn) -> None:
    image = photo(owner)
    marketing = signed_as(app, "marketing")  # media.upload but not media.manage
    assert delete_media(marketing, image["id"]).status_code == 403
    editor = signed_as(app, "content_editor")
    assert delete_media(editor, image["id"]).status_code == 204


def test_the_destroy_handler_retries_store_errors(
    owner: SignedIn, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    image = photo(owner)

    class Down:
        name = "fake"

        def destroy(self, resource_type: str, public_id: str) -> None:
            raise StoreError("no answer")

    monkeypatch.setattr(handlers, "get_store", Down)
    assert delete_media(owner, image["id"]).status_code == 204
    drain()
    db.expire_all()
    row = db.scalar(select(OutboxEvent).where(OutboxEvent.type == "media.removed"))
    assert row is not None and row.status == "pending" and row.attempts == 1
    assert "StoreError" in (row.last_error or "")


def test_the_destroy_handler_skips_events_of_another_store(db: Session) -> None:
    from empire_api.platform import outbox  # noqa: PLC0415

    outbox.emit(
        db,
        type_="media.removed",
        aggregate_type="media",
        aggregate_id="x",
        data={"store": "cloudinary", "resource_type": "image", "public_id": "empire/x"},
    )
    db.commit()
    result = drain()
    assert (result.processed, result.failed) == (1, 0)


# --- SEO share image -------------------------------------------------------------------------


def test_share_image_must_be_a_library_image(owner: SignedIn) -> None:
    project = create_project(owner)
    image, pdf = photo(owner), document(owner)
    nobody = "00000000-0000-0000-0000-000000000000"
    for bad in (nobody, pdf["id"]):
        response = patch_project(owner, project["id"], {"seo": {"og_image_id": bad}})
        assert response.status_code == 422
        assert response.json()["errors"][0]["field"] == "seo.og_image_id"
    view = ok(patch_project(owner, project["id"], {"seo": {"og_image_id": image["id"]}}))
    assert view["seo"]["og_image_id"] == image["id"]
    assert view["og_image"]["id"] == image["id"]
    cleared = ok(patch_project(owner, project["id"], {"seo": {"og_image_id": None}}))
    assert cleared["og_image"] is None


def test_a_share_image_cant_be_deleted(owner: SignedIn) -> None:
    project = create_project(owner)
    image = photo(owner)
    ok(patch_project(owner, project["id"], {"seo": {"og_image_id": image["id"]}}))
    response = delete_media(owner, image["id"])
    assert response.status_code == 409 and "share image" in response.json()["detail"]


def test_create_with_a_share_image(owner: SignedIn) -> None:
    image = photo(owner)
    project = create_project(owner, seo={"og_image_id": image["id"]})
    assert get_project(owner, project["id"])["og_image"]["id"] == image["id"]


# --- Clean-up --------------------------------------------------------------------------------


def test_cleanup_destroys_unconfirmed_uploads_and_drops_old_intents(
    owner: SignedIn, db: Session
) -> None:
    before = files()
    _, reply = direct_reply(owner)  # uploaded, never confirmed
    ok(signature(owner, "video", "v.mp4", 10, "video/mp4"))  # signed, never uploaded
    _, saved = direct_reply(owner)
    from media_support import confirm  # noqa: PLC0415

    ok(confirm(owner, saved), 201)
    db.execute(update(UploadIntent).values(expires_at=utcnow() - timedelta(hours=2)))
    db.execute(
        update(UploadIntent)
        .where(UploadIntent.used_at.is_not(None))
        .values(used_at=utcnow() - timedelta(days=8))
    )
    db.commit()
    counts = cleanup()
    assert counts["unconfirmed_uploads"] == 2
    assert db.scalar(select(UploadIntent.id)) is None
    reasons = {e.payload["reason"] for e in events(db, "media.upload_discarded")}
    assert reasons == {"never_confirmed"}
    drain()
    remaining = files() - before
    assert len(remaining) == 1  # only the confirmed upload is left
    assert reply["public_id"].rsplit("/", 1)[1] not in str(remaining)
