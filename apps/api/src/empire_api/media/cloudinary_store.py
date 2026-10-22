"""The real media store: Cloudinary, through its official Python SDK (D-033).

Collaborators: store.py (interface, `get_store`), signing.py, credentials.py.
Implements: ARCHITECTURE §12, SECURITY.md §6–7, D-007 (Cloudinary Free).

Facts this relies on (Cloudinary documentation, read 23 Oct 2026):
  - Upload API `POST https://api.cloudinary.com/v1_1/<cloud>/<resource_type>/upload`; `folder`
    is prepended to `public_id` in fixed-folder accounts and, for backward compatibility, also in
    dynamic-folder accounts (all accounts created since June 2024). `asset_folder` would not work
    in fixed-folder accounts, so `folder` is the one parameter that behaves the same in both.
  - Raw files (DOC/DOCX/PPT/PPTX) keep their extension in the public id; images and videos don't.
  - Admin API `GET /resources/<resource_type>/upload/<public_id>` returns bytes, format, size.
  - `destroy` answers {"result": "ok"} or {"result": "not found"}.
  - Delivered images: Cloudinary strips almost all embedded metadata (EXIF, including GPS)
    whenever a transformation is applied, so every image URL here carries one
    (f_auto,q_auto,c_limit). SECURITY: never build an untransformed image URL; the stored
    original keeps its metadata (D-033 notes the follow-up).
  - Video posters: an image extension on a video URL extracts a frame; `so_auto` picks it.
    The Free plan transforms videos only up to 40 MB on the fly, so the poster is also requested
    as an eager, asynchronous derivative at upload time (same transformation string).
  - fl_attachment is documented for images and videos only, so Office files are delivered
    plain; browsers download them because they can't show them.

SECURITY: credentials are passed on every call (never the SDK's global config), the secret is
never logged, and every network call has a timeout.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Any, Final

from empire_api.logs import get_logger
from empire_api.media import signing
from empire_api.media.credentials import CloudinaryCredentials, parse_cloudinary_url
from empire_api.media.store import (
    AssetRef,
    DeliveryUrls,
    ReplyRef,
    SignedUpload,
    StoredAsset,
    StoreError,
)
from empire_api.media.vocab import IMAGE_FORMATS, ResourceType, StoreName

API_HOST: Final = "https://api.cloudinary.com/v1_1"
UPLOAD_TIMEOUT_SECONDS: Final = 60
API_TIMEOUT_SECONDS: Final = 15
# Delivery transformations (one place, so URLs and eager derivatives always match).
FULL_IMAGE: Final[list[dict[str, Any]]] = [
    {"fetch_format": "auto", "quality": "auto", "crop": "limit", "width": 2560, "height": 2560}
]
THUMB_IMAGE: Final[list[dict[str, Any]]] = [
    {"fetch_format": "auto", "quality": "auto", "crop": "limit", "width": 480, "height": 480}
]
PDF_THUMB: Final[list[dict[str, Any]]] = [
    {"page": 1, "crop": "limit", "width": 480, "height": 480, "quality": "auto"}
]
VIDEO_POSTER: Final[list[dict[str, Any]]] = [
    {"start_offset": "auto"},
    {"crop": "limit", "width": 480, "height": 480},
]

log = get_logger(__name__)


class CloudinaryStore:
    """MediaStore backed by Cloudinary."""

    name: StoreName = "cloudinary"

    def __init__(self, credentials: CloudinaryCredentials) -> None:
        self._credentials = credentials

    @classmethod
    def from_url(cls, url: str) -> CloudinaryStore:
        return cls(parse_cloudinary_url(url))

    def _options(self, timeout: int = API_TIMEOUT_SECONDS) -> dict[str, Any]:
        c = self._credentials
        return {
            "cloud_name": c.cloud_name,
            "api_key": c.api_key,
            "api_secret": c.api_secret,
            "signature_algorithm": signing.REQUEST_ALGORITHM,
            "timeout": timeout,
        }

    # --- Uploads ---------------------------------------------------------------------------

    def upload_image(
        self, data: bytes, *, folder: str, public_id: str, image_format: str
    ) -> StoredAsset:
        import cloudinary.uploader  # noqa: PLC0415 — see store.get_store

        try:
            # WHY the ("upload", data) tuple: the SDK sends that name as the filename, so the
            # staff member's own filename never reaches the store (SECURITY.md §6).
            result = cloudinary.uploader.upload(
                ("upload", data),
                folder=folder,
                public_id=public_id,
                resource_type="image",
                overwrite=False,
                use_filename=False,
                allowed_formats=list(IMAGE_FORMATS),
                **self._options(UPLOAD_TIMEOUT_SECONDS),
            )
        except Exception as exc:
            raise _store_error("upload", exc) from exc
        return asset_from(result)

    def sign_upload(
        self,
        *,
        resource_type: ResourceType,
        folder: str,
        public_id: str,
        allowed_formats: tuple[str, ...],
    ) -> SignedUpload:
        """Sign a direct upload scoped to one folder and public id.

        SECURITY: `overwrite=false` stops the same signature (valid one hour at Cloudinary)
        from replacing the file after it was checked and saved.
        """
        timestamp = int(time.time())
        params: dict[str, str] = {
            "timestamp": str(timestamp),
            "folder": folder,
            "public_id": public_id,
            "overwrite": "false",
        }
        if resource_type != "raw" and allowed_formats:
            params["allowed_formats"] = ",".join(allowed_formats)
        if resource_type == "video":
            params["eager"] = _transformation_string(VIDEO_POSTER, "jpg")
            params["eager_async"] = "true"
        signature = signing.sign_params(params, self._credentials.api_secret)
        fields = {**params, "api_key": self._credentials.api_key, "signature": signature}
        return SignedUpload(
            upload_url=f"{API_HOST}/{self._credentials.cloud_name}/{resource_type}/upload",
            api_key=self._credentials.api_key,
            timestamp=timestamp,
            signature=signature,
            fields=fields,
        )

    def verify_reply(self, reply: Mapping[str, Any]) -> ReplyRef:
        return signing.verified_reply(reply, self._credentials.api_secret)

    # --- Admin --------------------------------------------------------------------------------

    def lookup(self, resource_type: ResourceType, public_id: str) -> StoredAsset | None:
        import cloudinary.api  # noqa: PLC0415
        from cloudinary.exceptions import NotFound  # noqa: PLC0415

        try:
            result = cloudinary.api.resource(
                public_id, resource_type=resource_type, type="upload", **self._options()
            )
        except NotFound:
            return None
        except Exception as exc:
            raise _store_error("lookup", exc) from exc
        return asset_from(result)

    def destroy(self, resource_type: str, public_id: str) -> None:
        import cloudinary.uploader  # noqa: PLC0415

        try:
            result = cloudinary.uploader.destroy(
                public_id,
                resource_type=resource_type,
                type="upload",
                invalidate=True,
                **self._options(),
            )
        except Exception as exc:
            raise _store_error("destroy", exc) from exc
        if result.get("result") not in ("ok", "not found"):
            raise StoreError(f"destroy answered {result.get('result')!r}")

    # --- Delivery -----------------------------------------------------------------------------

    def urls(self, asset: AssetRef) -> DeliveryUrls:
        base = {"version": asset.version, "resource_type": asset.resource_type}
        if asset.kind == "image":
            return DeliveryUrls(
                url=self._url(asset.public_id, transformation=FULL_IMAGE, **base),
                thumbnail_url=self._url(asset.public_id, transformation=THUMB_IMAGE, **base),
            )
        if asset.kind == "video":
            # SECURITY: videos are delivered as uploaded, and phone videos often carry GPS in
            # their container. Cloudinary's transformation reference says it strips "almost all
            # embedded metadata from a delivered asset when generating new transformations"
            # (fl_keep_iptc, tagged images and videos; read 23 Oct 2026), but it doesn't say a
            # video transcode drops container metadata such as GPS, and the Free plan only
            # transforms videos up to 40 MB on the fly. So the original URL stays for now.
            # TODO(phase-9): on staging, upload a phone video with GPS and inspect the delivered
            # file (exiftool). If GPS survives, deliver an eager `q_auto` derivative (like the
            # poster) or sign an incoming `fl_force_strip` transformation on upload.
            return DeliveryUrls(
                url=self._url(asset.public_id, format=asset.format, **base),
                thumbnail_url=self._url(
                    asset.public_id, format="jpg", transformation=VIDEO_POSTER, **base
                ),
            )
        if asset.resource_type == "image":  # a PDF: the original opens in the browser
            return DeliveryUrls(
                url=self._url(asset.public_id, format="pdf", **base),
                thumbnail_url=self._url(
                    asset.public_id, format="jpg", transformation=PDF_THUMB, **base
                ),
            )
        # Office files (raw): the public id already ends with the extension.
        return DeliveryUrls(url=self._url(asset.public_id, **base), thumbnail_url=None)

    def _url(self, public_id: str, **options: Any) -> str:
        from cloudinary.utils import cloudinary_url  # noqa: PLC0415

        url, _ = cloudinary_url(
            public_id, cloud_name=self._credentials.cloud_name, secure=True, **options
        )
        return str(url)


def _transformation_string(chain: list[dict[str, Any]], image_format: str) -> str:
    """`so_auto/c_limit,h_480,w_480/jpg`: the eager form of a delivery transformation."""
    from cloudinary.utils import build_eager  # noqa: PLC0415

    return str(build_eager([{"transformation": chain, "format": image_format}]))


def asset_from(result: Mapping[str, Any]) -> StoredAsset:
    """A store reply (upload or Admin API) → StoredAsset.

    Raw files have no `format` in the reply; their format is the public id's extension.
    """
    public_id = str(result["public_id"])
    resource_type = str(result["resource_type"])
    if resource_type not in ("image", "video", "raw"):
        raise StoreError("unexpected resource type")
    file_format = result.get("format") or public_id.rpartition(".")[2]
    duration = result.get("duration")
    return StoredAsset(
        public_id=public_id,
        resource_type=resource_type,  # type: ignore[arg-type]  # checked just above
        version=int(result["version"]),
        format=str(file_format).lower(),
        bytes=int(result["bytes"]),
        width=_int_or_none(result.get("width")),
        height=_int_or_none(result.get("height")),
        duration_s=float(duration) if isinstance(duration, int | float) else None,
    )


def _int_or_none(value: Any) -> int | None:
    return int(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _store_error(action: str, exc: Exception) -> StoreError:
    # SECURITY: the type only. SDK messages can echo request details; never the secret, but
    # there is no need to risk it.
    log.error("media_store_failed", store="cloudinary", action=action, error=type(exc).__name__)
    return StoreError(f"Cloudinary {action} failed ({type(exc).__name__})")
