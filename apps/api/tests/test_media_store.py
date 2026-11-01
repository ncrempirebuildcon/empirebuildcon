"""The two media stores (media/store.py): which one runs (config refusals in staging and
production), the dev-media routes existing only with the fake store, the Cloudinary store's
SDK calls and delivery URLs (no network: the SDK functions are replaced), the fake store's
Cloudinary-shaped direct upload, and the SAMPLE seed."""

from __future__ import annotations

from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.config import Settings, get_settings
from empire_api.main import create_app
from empire_api.media import cloudinary_store
from empire_api.media.cloudinary_store import CloudinaryStore
from empire_api.media.credentials import CloudinaryCredentials
from empire_api.media.models import Media, MediaLink
from empire_api.media.seed import seed_sample_media
from empire_api.media.store import AssetRef, StoreError
from empire_api.media.vocab import MAX_DOCUMENT_BYTES
from empire_api.projects.seed import seed_sample
from media_support import DOCX, MP4, PDF, image_bytes, signature, store_upload
from projects_support import get_project, ok

URL = "cloudinary://key-123:not-a-real-secret@demo"


def production(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "production",
        "session_secret": SecretStr("s" * 48),
        "internal_api_key": SecretStr("i" * 48),
        "ip_hash_salt": SecretStr("p" * 48),
        "data_encryption_key": SecretStr(Fernet.generate_key().decode()),
        "edge_proxy_key": SecretStr("e" * 48),
        "revalidate_secret": SecretStr("r" * 48),
        "web_revalidate_url": "https://example.com/_internal/revalidate",
        "cloudinary_url": SecretStr(URL),
        "email_api_key": SecretStr("not-a-real-resend-key"),
        "email_from": "alerts@example.com",
    }
    return Settings(**{**values, **overrides})


# --- Choosing the store ----------------------------------------------------------------------


def test_default_store_follows_cloudinary_url() -> None:
    assert Settings(app_env="development").media_store_kind == "fake"
    assert (
        Settings(app_env="development", media_store="").media_store_kind == "fake"
    )  # .env.example
    assert Settings(app_env="test", cloudinary_url=SecretStr(URL)).media_store_kind == "cloudinary"
    forced = Settings(app_env="development", cloudinary_url=SecretStr(URL), media_store="fake")
    assert forced.media_store_kind == "fake"
    assert production().media_store_kind == "cloudinary"


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_live_environments_refuse_to_start_without_cloudinary(app_env: str) -> None:
    with pytest.raises(ValueError, match="CLOUDINARY_URL must be set"):
        production(app_env=app_env, cloudinary_url=SecretStr(""))
    with pytest.raises(ValueError, match="MEDIA_STORE=fake is for development"):
        production(app_env=app_env, media_store="fake")


def test_bad_cloudinary_settings_are_refused_everywhere() -> None:
    with pytest.raises(ValueError, match="cloudinary://") as raised:
        Settings(app_env="development", cloudinary_url=SecretStr("https://k:secret-value@demo"))
    assert "secret-value" not in str(raised.value)  # SECURITY: names, never values
    with pytest.raises(ValueError, match="MEDIA_STORE=cloudinary needs CLOUDINARY_URL"):
        Settings(app_env="development", media_store="cloudinary")


def test_dev_media_routes_exist_only_with_the_fake_store() -> None:
    live = create_app(production())
    with TestClient(live, base_url="https://testserver") as client:
        client.headers.update({"X-Empire-Edge-Key": "e" * 48})
        assert client.get("/api/v1/dev-media/files/image/x.png").status_code == 404
        assert client.post("/api/v1/dev-media/upload/raw").status_code == 404
    test_cloud = create_app(Settings(app_env="test", cloudinary_url=SecretStr(URL)))
    assert not [p for p in test_cloud.openapi()["paths"] if "dev-media" in p]


def test_dev_media_routes_declare_themselves_public() -> None:
    spec = create_app(get_settings()).openapi()["paths"]
    assert spec["/api/v1/dev-media/files/{key}"]["get"]["x-public"] is True
    assert spec["/api/v1/dev-media/upload/{resource_type}"]["post"]["x-public"] is True


# --- Cloudinary store (SDK replaced) ---------------------------------------------------------


@pytest.fixture
def cloud() -> CloudinaryStore:
    return CloudinaryStore(CloudinaryCredentials("demo", "key-123", "not-a-real-secret"))


def test_upload_image_calls_the_sdk_without_the_filename(
    cloud: CloudinaryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cloudinary.uploader  # noqa: PLC0415

    seen: dict[str, Any] = {}

    def fake_upload(file: Any, **options: Any) -> dict[str, Any]:
        seen.update(file=file, **options)
        return {
            "public_id": "empire/test/image/abc",
            "version": 1712,
            "resource_type": "image",
            "format": "jpg",
            "bytes": 2048,
            "width": 800,
            "height": 600,
        }

    monkeypatch.setattr(cloudinary.uploader, "upload", fake_upload)
    asset = cloud.upload_image(
        b"data", folder="empire/test/image", public_id="abc", image_format="jpg"
    )
    assert (asset.public_id, asset.version, asset.width, asset.bytes) == (
        "empire/test/image/abc",
        1712,
        800,
        2048,
    )
    assert seen["file"] == ("upload", b"data")
    assert (seen["folder"], seen["public_id"], seen["overwrite"]) == (
        "empire/test/image",
        "abc",
        False,
    )
    assert (seen["cloud_name"], seen["api_key"], seen["api_secret"]) == (
        "demo",
        "key-123",
        "not-a-real-secret",
    )
    assert seen["timeout"] > 0 and seen["allowed_formats"] == ["jpg", "png", "webp", "avif"]


def test_sdk_failures_become_store_errors(
    cloud: CloudinaryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cloudinary.api  # noqa: PLC0415
    import cloudinary.uploader  # noqa: PLC0415
    from cloudinary.exceptions import GeneralError, NotFound  # noqa: PLC0415

    def boom(*args: Any, **kwargs: Any) -> None:
        raise GeneralError("upstream said no")

    def missing(*args: Any, **kwargs: Any) -> None:
        raise NotFound("Resource not found")

    monkeypatch.setattr(cloudinary.uploader, "upload", boom)
    with pytest.raises(StoreError):
        cloud.upload_image(b"x", folder="f", public_id="p", image_format="png")
    monkeypatch.setattr(cloudinary.api, "resource", missing)
    assert cloud.lookup("video", "empire/test/video/x") is None
    monkeypatch.setattr(cloudinary.api, "resource", boom)
    with pytest.raises(StoreError):
        cloud.lookup("video", "empire/test/video/x")


def test_lookup_reads_the_admin_api_record(
    cloud: CloudinaryStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    import cloudinary.api  # noqa: PLC0415

    def resource(public_id: str, **options: Any) -> dict[str, Any]:
        assert (options["resource_type"], options["type"]) == ("raw", "upload")
        return {"public_id": public_id, "version": 9, "resource_type": "raw", "bytes": 512}

    monkeypatch.setattr(cloudinary.api, "resource", resource)
    asset = cloud.lookup("raw", "empire/test/document/x.docx")
    assert asset is not None and (asset.format, asset.bytes) == ("docx", 512)


@pytest.mark.parametrize(
    ("answer", "fails"), [("ok", False), ("not found", False), ("error", True)]
)
def test_destroy_is_idempotent(
    cloud: CloudinaryStore, monkeypatch: pytest.MonkeyPatch, answer: str, fails: bool
) -> None:
    import cloudinary.uploader  # noqa: PLC0415

    calls: list[dict[str, Any]] = []

    def destroy(public_id: str, **options: Any) -> dict[str, str]:
        calls.append({"public_id": public_id, **options})
        return {"result": answer}

    monkeypatch.setattr(cloudinary.uploader, "destroy", destroy)
    if fails:
        with pytest.raises(StoreError):
            cloud.destroy("video", "empire/test/video/x")
    else:
        cloud.destroy("video", "empire/test/video/x")
    assert calls[0]["resource_type"] == "video" and calls[0]["invalidate"] is True


def test_delivery_urls(cloud: CloudinaryStore) -> None:
    """SECURITY: every image URL carries a transformation, so Cloudinary strips EXIF/GPS."""
    image = cloud.urls(AssetRef("image", "empire/p/image/a", "image", 17, "jpg"))
    assert image.url == (
        "https://res.cloudinary.com/demo/image/upload/c_limit,f_auto,h_2560,q_auto,w_2560/v17/"
        "empire/p/image/a"
    )
    assert (
        image.thumbnail_url is not None
        and "c_limit,f_auto,h_480,q_auto,w_480" in image.thumbnail_url
    )
    pdf = cloud.urls(AssetRef("document", "empire/p/document/b", "image", 17, "pdf"))
    assert pdf.url == "https://res.cloudinary.com/demo/image/upload/v17/empire/p/document/b.pdf"
    assert pdf.thumbnail_url is not None and "pg_1" in pdf.thumbnail_url
    assert pdf.thumbnail_url.endswith(".jpg")
    office = cloud.urls(AssetRef("document", "empire/p/document/c.docx", "raw", 17, "docx"))
    assert office.url == "https://res.cloudinary.com/demo/raw/upload/v17/empire/p/document/c.docx"
    assert office.thumbnail_url is None
    video = cloud.urls(AssetRef("video", "empire/p/video/d", "video", 17, "mp4"))
    assert video.url == "https://res.cloudinary.com/demo/video/upload/v17/empire/p/video/d.mp4"
    assert video.thumbnail_url == (
        "https://res.cloudinary.com/demo/video/upload/so_auto/c_limit,h_480,w_480/v17/"
        "empire/p/video/d.jpg"
    )


def test_asset_from_rejects_unknown_resource_types() -> None:
    with pytest.raises(StoreError):
        cloudinary_store.asset_from(
            {"public_id": "x", "resource_type": "zip", "version": 1, "bytes": 1}
        )


# --- The fake store's direct upload ----------------------------------------------------------


def test_fake_upload_checks_like_cloudinary(owner: SignedIn) -> None:
    sig = ok(signature(owner, "document", "a.pdf", len(PDF), "application/pdf"))
    assert store_upload(owner, sig, PDF, api_key="wrong").json() == {
        "error": {"message": "Invalid api_key"}
    }
    stale = store_upload(owner, sig, PDF, timestamp=str(int(sig["timestamp"]) - 7200))
    assert stale.status_code == 400 and "Stale request" in stale.json()["error"]["message"]
    assert store_upload(owner, sig, PDF, overwrite="true").status_code == 401  # signed field
    assert store_upload(owner, sig, image_bytes()).status_code == 400  # not a PDF: allowed_formats
    reply = ok(store_upload(owner, sig, PDF))
    assert {"public_id", "version", "signature", "bytes", "format", "secure_url"} <= set(reply)
    again = ok(store_upload(owner, sig, PDF))
    assert again["existing"] is True and again["version"] == reply["version"]  # overwrite=false


def test_fake_upload_enforces_the_plan_limit(owner: SignedIn) -> None:
    sig = ok(signature(owner, "document", "a.docx", 10, ""))
    too_big = store_upload(owner, sig, DOCX + b"\x00" * MAX_DOCUMENT_BYTES)
    assert too_big.status_code == 400
    assert "File size too large" in too_big.json()["error"]["message"]


def test_fake_upload_detects_videos(owner: SignedIn) -> None:
    sig = ok(signature(owner, "video", "a.mp4", len(MP4), "video/mp4"))
    assert store_upload(owner, sig, PDF).status_code == 400
    assert ok(store_upload(owner, sig, MP4))["format"] == "mp4"


def test_dev_files_are_served_and_nothing_else(owner: SignedIn) -> None:
    from media_support import photo  # noqa: PLC0415

    image = photo(owner)
    path = image["url"].split("localhost:3000", 1)[1]
    served = owner.client.get(path)
    assert served.status_code == 200 and served.headers["content-type"] == "image/png"
    assert served.content == image_bytes()
    for bad in (
        "/api/v1/dev-media/files/image/../../../../etc/passwd",
        "/api/v1/dev-media/files/image/empire/test/image/%2e%2e/x.png",
        "/api/v1/dev-media/files/raw/empire/test/document/00000000-0000-0000-0000-000000000000.docx",
        "/api/v1/dev-media/files/anything",
    ):
        assert owner.client.get(bad).status_code == 404, bad


def test_office_files_download_and_pdfs_open(owner: SignedIn) -> None:
    from media_support import confirm, direct_reply  # noqa: PLC0415

    _, reply = direct_reply(owner, "document", "list.docx", DOCX, "")
    docx = ok(confirm(owner, reply), 201)
    served = owner.client.get(docx["url"].split("localhost:3000", 1)[1])
    assert served.headers["content-disposition"].startswith("attachment")
    _, reply = direct_reply(owner)
    pdf = ok(confirm(owner, reply), 201)
    served = owner.client.get(pdf["url"].split("localhost:3000", 1)[1])
    assert served.headers["content-type"] == "application/pdf"
    assert served.headers["content-disposition"].startswith("inline")


# --- Seed ------------------------------------------------------------------------------------


def test_sample_seed_adds_marked_placeholder_tiles_once(owner: SignedIn, db: Session) -> None:
    seed_sample(db)
    db.commit()
    first = seed_sample_media(db)
    db.commit()
    assert (first.added, first.store) == (6, "fake")
    again = seed_sample_media(db)
    db.commit()
    assert (again.added, again.skipped_projects) == (0, 2)
    rows = db.scalars(select(Media)).all()
    assert all(row.is_sample and row.label is None for row in rows)
    assert all(row.title.startswith("SAMPLE") for row in rows)
    roles = set(db.scalars(select(MediaLink.role)))
    assert roles == {"gallery"}  # COMPLIANCE: never a RERA QR
    project_id = db.scalar(select(MediaLink.project_id))
    view = get_project(owner, str(project_id))
    assert len(view["gallery"]) == 3 and view["cover"]["is_sample"] is True
    assert "RERA QR code missing" in view["publish_blockers"]


def test_sample_tile_text_only_uses_glyphs_the_font_has() -> None:
    from PIL import ImageFont  # noqa: PLC0415

    from empire_api.media import seed as media_seed  # noqa: PLC0415

    font = ImageFont.load_default(size=40)
    missing = font.getmask("\uffff").getbbox()  # the box drawn for an unknown character
    for text in (media_seed.HEADLINE, media_seed.CAPTION.format(number=1)):
        assert all(ch == " " or font.getmask(ch).getbbox() != missing for ch in text), text
    assert font.getmask("\u2014").getbbox() == missing  # the em dash this test guards against


def test_sample_seed_never_uses_cloudinary(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    from empire_api.media import seed as media_seed  # noqa: PLC0415

    class Cloud:
        name = "cloudinary"

    monkeypatch.setattr(media_seed, "get_store", Cloud)
    seed_sample(db)
    result = media_seed.seed_sample_media(db)
    assert (result.added, result.store) == (0, "cloudinary")
