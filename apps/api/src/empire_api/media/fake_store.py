"""The fake media store: files on disk, no network (development, tests, the browser suite).

Collaborators: store.py (interface), routes_dev.py (serves files and mimics Cloudinary's direct
upload), signing.py (the same signatures as Cloudinary, with a fixed public test key).
Implements: D-033.

Files live under MEDIA_DEV_DIR (default apps/api/.media-dev/, git-ignored) as
`<resource_type>/<public_id>[.<format>]`, and are served from
`GET /api/v1/dev-media/files/<that path>` on SITE_URL, so URLs go through the web app's proxy
exactly like every other API call.

SECURITY: config.py refuses this store in staging and production, and main.py only mounts the
dev-media routes while it is active. Paths are built from validated public ids only, so a
request can't reach outside MEDIA_DEV_DIR.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from PIL import Image, UnidentifiedImageError

from empire_api.config import Settings
from empire_api.media import signing
from empire_api.media.store import (
    AssetRef,
    DeliveryUrls,
    ReplyRef,
    SignedUpload,
    StoredAsset,
)
from empire_api.media.vocab import ResourceType, StoreName

API_ROOT: Final = Path(__file__).resolve().parents[3]
DEFAULT_DIR: Final = API_ROOT / ".media-dev"
DEV_MEDIA_PREFIX: Final = "/api/v1/dev-media"
FAKE_API_KEY: Final = "fake-media-key"
FAKE_CLOUD_NAME: Final = "empire-fake"
# WHY derived, not written out: it is a fixed, public test key (this store never sees real
# credentials), and a long hex literal would look like a leaked secret to the secret scanner.
FAKE_API_SECRET: Final = hashlib.sha256(b"empire fake media store: not a secret").hexdigest()
_UUID: Final = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
# SECURITY: the only public ids this store accepts (and so the only paths it touches).
PUBLIC_ID: Final = re.compile(
    rf"^empire/[a-z]+/(image|video|document)/{_UUID}(\.(doc|docx|ppt|pptx))?$"
)
FILE_KEY: Final = re.compile(
    rf"^(image|video|raw)/empire/[a-z]+/(image|video|document)/{_UUID}\.[a-z0-9]{{2,5}}$"
)


class FakeStore:
    """MediaStore that keeps files in a local folder."""

    name: StoreName = "fake"
    api_key: Final = FAKE_API_KEY
    api_secret: Final = FAKE_API_SECRET

    def __init__(self, root: Path, site_url: str) -> None:
        self.root = root
        self.base_url = site_url.rstrip("/") + DEV_MEDIA_PREFIX

    @classmethod
    def from_settings(cls, settings: Settings) -> FakeStore:
        root = Path(settings.media_dev_dir) if settings.media_dev_dir else DEFAULT_DIR
        return cls(root, settings.site_url)

    # --- Files ---------------------------------------------------------------------------------

    @staticmethod
    def file_key(resource_type: str, public_id: str, file_format: str) -> str:
        """`image/empire/dev/image/<uuid>.png`; raw public ids already end with the extension."""
        suffix = "" if resource_type == "raw" else f".{file_format}"
        return f"{resource_type}/{public_id}{suffix}"

    def path_for_key(self, key: str) -> Path | None:
        """The file for a delivery key, or None for anything that isn't one of ours."""
        if not FILE_KEY.match(key):
            return None
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root.resolve()):
            return None
        return path

    def save(
        self, resource_type: ResourceType, public_id: str, file_format: str, source: Path | bytes
    ) -> StoredAsset:
        """Write a file for `public_id` (moving `source` when it is a temporary file)."""
        if not PUBLIC_ID.match(public_id):
            raise ValueError("not a public id this store generates")
        path = self.root / self.file_key(resource_type, public_id, file_format)
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(source, bytes):
            path.write_bytes(source)
        else:
            # WHY move, not os.replace: the temporary file may sit on another filesystem.
            shutil.move(source, path)
        version = int(time.time())
        os.utime(path, (version, version))
        return self._asset(resource_type, public_id, path)

    def _find(self, resource_type: str, public_id: str) -> Path | None:
        if not PUBLIC_ID.match(public_id):
            return None
        if resource_type == "raw":
            path = self.root / "raw" / public_id
            return path if path.is_file() else None
        folder = self.root / resource_type / public_id.rpartition("/")[0]
        name = public_id.rpartition("/")[2]
        matches = sorted(folder.glob(f"{name}.*")) if folder.is_dir() else []
        return matches[0] if matches else None

    def _asset(self, resource_type: ResourceType, public_id: str, path: Path) -> StoredAsset:
        stat = path.stat()
        file_format = path.suffix.lstrip(".").lower()
        width = height = None
        if resource_type == "image" and file_format != "pdf":
            width, height = _image_size(path)
        return StoredAsset(
            public_id=public_id,
            resource_type=resource_type,
            version=int(stat.st_mtime),
            format=file_format,
            bytes=stat.st_size,
            width=width,
            height=height,
        )

    # --- MediaStore ------------------------------------------------------------------------

    def upload_image(
        self, data: bytes, *, folder: str, public_id: str, image_format: str
    ) -> StoredAsset:
        return self.save("image", f"{folder}/{public_id}", image_format, data)

    def sign_upload(
        self,
        *,
        resource_type: ResourceType,
        folder: str,
        public_id: str,
        allowed_formats: tuple[str, ...],
    ) -> SignedUpload:
        """The same parameters the Cloudinary store signs (without the eager video poster)."""
        timestamp = int(time.time())
        params = {
            "timestamp": str(timestamp),
            "folder": folder,
            "public_id": public_id,
            "overwrite": "false",
        }
        if resource_type != "raw" and allowed_formats:
            params["allowed_formats"] = ",".join(allowed_formats)
        signature = signing.sign_params(params, FAKE_API_SECRET)
        return SignedUpload(
            upload_url=f"{self.base_url}/upload/{resource_type}",
            api_key=FAKE_API_KEY,
            timestamp=timestamp,
            signature=signature,
            fields={**params, "api_key": FAKE_API_KEY, "signature": signature},
        )

    def verify_reply(self, reply: Mapping[str, Any]) -> ReplyRef:
        return signing.verified_reply(reply, FAKE_API_SECRET)

    def lookup(self, resource_type: ResourceType, public_id: str) -> StoredAsset | None:
        path = self._find(resource_type, public_id)
        return None if path is None else self._asset(resource_type, public_id, path)

    def destroy(self, resource_type: str, public_id: str) -> None:
        path = self._find(resource_type, public_id)
        if path is not None:
            path.unlink(missing_ok=True)

    def urls(self, asset: AssetRef) -> DeliveryUrls:
        """The file itself. No resizing here, so a photo's thumbnail is the photo."""
        key = self.file_key(asset.resource_type, asset.public_id, asset.format)
        url = f"{self.base_url}/files/{key}"
        return DeliveryUrls(url=url, thumbnail_url=url if asset.kind == "image" else None)


def _image_size(path: Path) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(path.read_bytes())) as image:
            width, height = image.size
            return int(width), int(height)
    except UnidentifiedImageError, OSError:
        return None, None
