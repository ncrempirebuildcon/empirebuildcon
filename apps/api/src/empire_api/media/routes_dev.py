"""Development-only routes of the fake media store (tag "Dev media"):

- `GET  /api/v1/dev-media/files/{key}`: serve a stored file.
- `POST /api/v1/dev-media/upload/{resource_type}`: a Cloudinary-shaped direct upload. Checks the
  API key, the timestamp (one hour, like Cloudinary) and the signature exactly as Cloudinary
  does, enforces the plan's size limit while the body streams in, and answers with a
  Cloudinary-shaped reply signed the way Cloudinary signs replies. Errors use Cloudinary's
  `{"error": {"message": …}}` shape too, so the browser code handles both stores the same way.

Collaborators: fake_store.py, signing.py, multipart.py, sniff.py; main.py mounts this router
only while the fake store is active (tests/test_media_store.py proves it is absent otherwise).

SECURITY: public routes (the signature is the authorisation, as at Cloudinary), but config.py
refuses the fake store in staging and production, so they never exist there.
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path as FilePath
from typing import Annotated, Any, Final

from fastapi import APIRouter, Path, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.concurrency import run_in_threadpool

from empire_api.errors import ApiProblem
from empire_api.media import signing, sniff
from empire_api.media.fake_store import FAKE_API_KEY, FAKE_API_SECRET, PUBLIC_ID, FakeStore
from empire_api.media.multipart import CappedForm, read_capped_form
from empire_api.media.store import AssetRef, StoredAsset, get_store
from empire_api.media.vocab import (
    IMAGE_FORMATS,
    MAX_DOCUMENT_BYTES,
    MAX_IMAGE_BYTES,
    MAX_VIDEO_BYTES,
)
from empire_api.users.deps import PUBLIC

router = APIRouter(prefix="/api/v1/dev-media", tags=["Dev media"])

MAX_BYTES: Final = {"image": MAX_IMAGE_BYTES, "video": MAX_VIDEO_BYTES, "raw": MAX_DOCUMENT_BYTES}
SIGNATURE_LIFETIME_SECONDS: Final = 3600
CONTENT_TYPES: Final = {
    "jpg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "avif": "image/avif",
    "pdf": "application/pdf",
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "doc": "application/msword",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "ppt": "application/vnd.ms-powerpoint",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
}


class CloudinaryError(Exception):
    """An answer in Cloudinary's error shape."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _fake_store() -> FakeStore:
    store = get_store()
    if not isinstance(store, FakeStore):  # main.py mounts these routes only for the fake store
        raise ApiProblem(404, "There is nothing at this address.")
    return store


@router.get(
    "/files/{key:path}",
    operation_id="dev_media_file",
    summary="Serve a file from the fake media store (development only)",
    response_class=FileResponse,
    **PUBLIC,
)
def dev_media_file(key: str) -> FileResponse:
    path = _fake_store().path_for_key(key)
    if path is None or not path.is_file():
        raise ApiProblem(404, "There is nothing at this address.")
    file_format = path.suffix.lstrip(".")
    # PDFs open in the browser; Office files download (as Cloudinary delivers them).
    disposition = "attachment" if file_format in ("doc", "docx", "ppt", "pptx") else "inline"
    return FileResponse(
        path,
        media_type=CONTENT_TYPES.get(file_format, "application/octet-stream"),
        content_disposition_type=disposition,
        filename=path.name,
    )


@router.post(
    "/upload/{resource_type}",
    operation_id="dev_media_upload",
    summary="Cloudinary-shaped signed direct upload to the fake media store (development only)",
    response_model=dict[str, Any],
    **PUBLIC,
)
async def dev_media_upload(
    request: Request, resource_type: Annotated[str, Path(pattern="^(image|video|raw)$")]
) -> JSONResponse:
    store = _fake_store()
    too_large = f"File size too large. Maximum is {MAX_BYTES[resource_type]}."
    try:
        form = await read_capped_form(request, MAX_BYTES[resource_type], too_large)
    except ApiProblem as exc:
        return _error(400 if exc.status == 413 else exc.status, exc.detail)
    try:
        if form.file is None:
            raise CloudinaryError(400, "Missing required parameter - file")
        params = {k: v for k, v in form.fields.items() if k != "file"}
        public_id = _check_request(params)
        head = await form.file.read(64)
        await form.file.seek(0)
        file_format = _detect(resource_type, head, public_id, params.get("allowed_formats"))
        temp = await run_in_threadpool(_spill, form)
        reply = await run_in_threadpool(
            _store_upload, store, resource_type, public_id, file_format, temp, params
        )
    except CloudinaryError as exc:
        return _error(exc.status, exc.message)
    finally:
        await form.close()
    return JSONResponse(reply)


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"error": {"message": message}}, status_code=status)


def _check_request(params: dict[str, str]) -> str:
    """API key, timestamp and signature, then the final public id (folder + public id)."""
    if params.get("api_key") != FAKE_API_KEY:
        raise CloudinaryError(401, "Invalid api_key")
    timestamp = params.get("timestamp", "")
    if not timestamp.isdecimal():
        raise CloudinaryError(400, "Missing required parameter - timestamp")
    if abs(time.time() - int(timestamp)) > SIGNATURE_LIFETIME_SECONDS:
        raise CloudinaryError(400, "Stale request - reported time is more than 1 hour ago")
    if not signing.params_signature_ok(params, params.get("signature", ""), FAKE_API_SECRET):
        raise CloudinaryError(401, "Invalid Signature")
    folder, short_id = params.get("folder", "").strip("/"), params.get("public_id", "")
    public_id = f"{folder}/{short_id}" if folder else short_id
    if not PUBLIC_ID.match(public_id):
        raise CloudinaryError(400, "Invalid public_id for the fake store")
    return public_id


def _detect(resource_type: str, head: bytes, public_id: str, allowed: str | None) -> str:
    if resource_type == "raw":
        return public_id.rpartition(".")[2]  # like Cloudinary: raw files are not inspected
    if resource_type == "video":
        file_format = sniff.detect_direct_format(head)
        file_format = file_format if file_format in ("mp4", "mov", "webm") else None
    else:
        file_format = sniff.detect_direct_format(head)
        if file_format != "pdf":
            try:
                file_format = sniff.detect_image_format(head)
            except sniff.NotAnImageError:
                file_format = None
        file_format = file_format if file_format in (*IMAGE_FORMATS, "pdf") else None
    if file_format is None:
        raise CloudinaryError(400, "Invalid file format or the file is damaged")
    if allowed and file_format not in allowed.split(","):
        raise CloudinaryError(400, f"{file_format} format is not allowed")
    return file_format


def _spill(form: CappedForm) -> FilePath:
    """Copy the spooled upload to a real temporary file the store can move into place."""
    import shutil  # noqa: PLC0415
    import tempfile  # noqa: PLC0415

    assert form.file is not None  # noqa: S101 — checked by the caller
    with tempfile.NamedTemporaryFile(delete=False, prefix="dev-media-") as out:
        form.file.file.seek(0)
        shutil.copyfileobj(form.file.file, out)
        return FilePath(out.name)


def _store_upload(
    store: FakeStore,
    resource_type: str,
    public_id: str,
    file_format: str,
    temp: FilePath,
    params: dict[str, str],
) -> dict[str, Any]:
    existing = store.lookup(resource_type, public_id)  # type: ignore[arg-type]
    if existing is not None and params.get("overwrite") == "false":
        temp.unlink(missing_ok=True)
        return _reply(store, existing, params, existing=True)
    asset = store.save(resource_type, public_id, file_format, temp)  # type: ignore[arg-type]
    return _reply(store, asset, params, existing=False)


def _reply(
    store: FakeStore, asset: StoredAsset, params: dict[str, str], *, existing: bool
) -> dict[str, Any]:
    """A reply shaped like Cloudinary's, signed over public_id and version (SHA-1, as
    Cloudinary's default)."""
    if asset.resource_type == "video":
        kind = "video"
    elif asset.resource_type == "image" and asset.format != "pdf":
        kind = "image"
    else:
        kind = "document"
    ref = AssetRef(kind, asset.public_id, asset.resource_type, asset.version, asset.format)
    url = store.urls(ref).url
    reply: dict[str, Any] = {
        "asset_id": uuid.uuid4().hex,
        "public_id": asset.public_id,
        "version": asset.version,
        "version_id": uuid.uuid4().hex,
        "signature": signing.reply_signature(
            asset.public_id, asset.version, FAKE_API_SECRET, "sha1"
        ),
        "width": asset.width,
        "height": asset.height,
        "resource_type": asset.resource_type,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(asset.version)),
        "tags": [],
        "bytes": asset.bytes,
        "type": "upload",
        "placeholder": False,
        "url": url,
        "secure_url": url,
        "folder": params.get("folder", ""),
        "original_filename": "file",
        "api_key": FAKE_API_KEY,
    }
    if asset.resource_type != "raw":
        reply["format"] = asset.format
    if existing:
        reply["existing"] = True
    return {k: v for k, v in reply.items() if v is not None or k in ("width", "height")}
