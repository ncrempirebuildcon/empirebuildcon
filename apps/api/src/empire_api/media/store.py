"""Where media files live: one `MediaStore` interface, two stores (D-033).

- `CloudinaryStore` (cloudinary_store.py): the real store, configured from CLOUDINARY_URL.
- `FakeStore` (fake_store.py): development, tests and the browser suite. No network; files go to
  MEDIA_DEV_DIR and are served by the dev-media routes (routes_dev.py), which also mimic
  Cloudinary's signed direct upload, so the browser flow runs unchanged in e2e.

Collaborators: uploads.py, library.py and present.py call `get_store()`; handlers.py destroys
assets; config.py decides which store is active (`Settings.media_store_kind`).

SECURITY: the API secret never leaves the server. Only the cloud name and API key reach the
browser, inside an upload signature (SECURITY.md §7).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Protocol

from empire_api.config import get_settings
from empire_api.media.vocab import ResourceType, StoreName


class StoreError(RuntimeError):
    """The store failed or didn't answer (network, credentials, plan limit). Safe to retry."""


class InvalidReplyError(ValueError):
    """A direct-upload reply that is malformed or whose signature doesn't verify."""


@dataclass(frozen=True)
class StoredAsset:
    """What the store says about one asset (never what the browser says)."""

    public_id: str
    resource_type: ResourceType
    version: int
    format: str
    bytes: int
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None


@dataclass(frozen=True)
class SignedUpload:
    """A signed direct upload. `fields` are every form field to send with the file."""

    upload_url: str
    api_key: str
    timestamp: int
    signature: str
    fields: dict[str, str]


@dataclass(frozen=True)
class ReplyRef:
    """The two fields a store reply's signature covers (public id and version)."""

    public_id: str
    version: int


@dataclass(frozen=True)
class AssetRef:
    """Enough to build delivery URLs for a library row."""

    kind: str
    public_id: str
    resource_type: str
    version: int
    format: str


@dataclass(frozen=True)
class DeliveryUrls:
    url: str
    thumbnail_url: str | None


class MediaStore(Protocol):
    """The operations the media module needs from a store. Every method may raise StoreError."""

    name: StoreName

    def upload_image(
        self, data: bytes, *, folder: str, public_id: str, image_format: str
    ) -> StoredAsset:
        """Upload a checked photo from the server (POST /admin/media/images)."""
        ...

    def sign_upload(
        self,
        *,
        resource_type: ResourceType,
        folder: str,
        public_id: str,
        allowed_formats: tuple[str, ...],
    ) -> SignedUpload:
        """Sign one direct upload from the browser, scoped to this folder and public id."""
        ...

    def verify_reply(self, reply: Mapping[str, Any]) -> ReplyRef:
        """Check a direct-upload reply's signature. Raises InvalidReplyError."""
        ...

    def lookup(self, resource_type: ResourceType, public_id: str) -> StoredAsset | None:
        """Re-read an asset from the store itself (None when it doesn't exist)."""
        ...

    def destroy(self, resource_type: str, public_id: str) -> None:
        """Delete an asset. Deleting one that is already gone is not an error."""
        ...

    def urls(self, asset: AssetRef) -> DeliveryUrls:
        """Delivery URLs: images width-limited with f_auto,q_auto; documents and videos."""
        ...


@lru_cache(maxsize=1)
def get_store() -> MediaStore:
    """The active store for this process. Tests call `get_store.cache_clear()`."""
    settings = get_settings()
    if settings.media_store_kind == "cloudinary":
        from empire_api.media.cloudinary_store import CloudinaryStore  # noqa: PLC0415

        # WHY imported here: the Cloudinary SDK parses CLOUDINARY_URL from the environment when
        # it is imported, so it is only imported once the settings have validated that value.
        return CloudinaryStore.from_url(settings.cloudinary_url.get_secret_value())
    from empire_api.media.fake_store import FakeStore  # noqa: PLC0415

    return FakeStore.from_settings(settings)


def folder_for(kind: str) -> str:
    """`empire/<APP_ENV>/<kind>`: every public id is generated under it (SECURITY.md §6)."""
    return f"empire/{get_settings().app_env}/{kind}"
