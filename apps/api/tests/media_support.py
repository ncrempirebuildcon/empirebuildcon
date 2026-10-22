"""Helpers for the media tests: small generated files (no binary fixtures), uploads through the
API and the fake store's Cloudinary-shaped direct upload, and attaching.

Files are made in memory with Pillow or by hand, a few hundred bytes each.
"""

from __future__ import annotations

import io
import struct
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from PIL import Image

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.config import get_settings
from empire_api.media.fake_store import FakeStore
from empire_api.media.store import get_store
from projects_support import ok

MEDIA = "/api/v1/admin/media"
LINKS = "/api/v1/admin/media-links"


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (16, 12), color: str = "teal") -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, color).save(out, format=fmt)
    return out.getvalue()


def big_png(width: int, height: int) -> bytes:
    """A large but tiny-to-store PNG (1 bit per pixel, one colour): a few kilobytes."""
    out = io.BytesIO()
    Image.new("1", (width, height), 0).save(out, format="PNG")
    return out.getvalue()


def ftyp(major: bytes, *compatible: bytes) -> bytes:
    """An ISO-BMFF `ftyp` box (the start of AVIF, HEIC, MP4 and MOV files) plus filler."""
    body = major + b"\x00\x00\x00\x00" + b"".join(compatible)
    return struct.pack(">I", 8 + len(body)) + b"ftyp" + body + b"\x00" * 64


PDF = b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n%%EOF\n"
MP4 = ftyp(b"isom", b"isom", b"mp41") + b"\x00\x00\x00\x08free"
DOCX = b"PK\x03\x04" + b"\x00" * 200  # the start of a zip; the store doesn't inspect raw files


def signed_as(app: FastAPI, role: str) -> SignedIn:
    client = new_client(app)
    return sign_in(client, make_user(role, email=f"{role}-{uuid.uuid4().hex[:6]}@example.com"))


def upload_photo(
    signed: SignedIn,
    data: bytes | None = None,
    *,
    filename: str = "photo.png",
    content_type: str = "image/png",
    **fields: str,
) -> Any:
    return signed.client.post(
        f"{MEDIA}/images",
        files={"file": (filename, data if data is not None else image_bytes(), content_type)},
        data=fields,
        headers=signed.headers(),
    )


def photo(signed: SignedIn, **fields: str) -> Any:
    """Upload a small PNG and return the Media JSON.

    Labelled "actual_photo" unless `label` is given (pass label="" for an unlabelled photo):
    unlabelled photos attach hidden in photo lists (media/rules.needs_label).
    """
    fields.setdefault("label", "actual_photo")
    return ok(upload_photo(signed, **fields), 201)


def signature(signed: SignedIn, kind: str, filename: str, size: int, mime: str) -> Any:
    body = {"kind": kind, "filename": filename, "bytes": size, "mime_type": mime}
    return signed.client.post(f"{MEDIA}/upload-signature", json=body, headers=signed.headers())


def store_upload(signed: SignedIn, sig: dict[str, Any], data: bytes, **override: str) -> Any:
    """POST the file to the signature's upload_url exactly as the browser would (fake store)."""
    path = sig["upload_url"].split("://", 1)[1].split("/", 1)[1]
    fields = {**sig["fields"], **override}
    return signed.client.post(f"/{path}", data=fields, files={"file": ("upload", data)})


def direct_reply(
    signed: SignedIn,
    kind: str = "document",
    filename: str = "brochure.pdf",
    data: bytes = PDF,
    mime: str = "application/pdf",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Signature + fake direct upload; returns (signature, the store's reply)."""
    sig = ok(signature(signed, kind, filename, len(data), mime))
    return sig, ok(store_upload(signed, sig, data))


def confirm(signed: SignedIn, reply: dict[str, Any], **extra: Any) -> Any:
    body = {"cloudinary_response": reply, **extra}
    return signed.client.post(f"{MEDIA}/confirm", json=body, headers=signed.headers())


def document(signed: SignedIn, **extra: Any) -> Any:
    """A PDF through the whole direct flow; returns the Media JSON."""
    _, reply = direct_reply(signed)
    return ok(confirm(signed, reply, **extra), 201)


def attach(
    signed: SignedIn, media_id: str, attach_to: str, role: str, *, is_visible: bool = True
) -> Any:
    body = {"media_id": media_id, "attach_to": attach_to, "role": role, "is_visible": is_visible}
    return signed.client.post(LINKS, json=body, headers=signed.headers())


def patch_link(signed: SignedIn, link_id: str, **body: bool) -> Any:
    return signed.client.patch(f"{LINKS}/{link_id}", json=body, headers=signed.headers())


def detach(signed: SignedIn, link_id: str) -> Any:
    return signed.client.delete(f"{LINKS}/{link_id}", headers=signed.headers())


def reorder(signed: SignedIn, ids: list[str]) -> Any:
    return signed.client.put(f"{LINKS}/order", json={"ids": ids}, headers=signed.headers())


def media_files() -> list[Path]:
    """Every file the fake store holds (tests run with a temporary MEDIA_DEV_DIR)."""
    root = Path(get_settings().media_dev_dir)
    return sorted(p for p in root.rglob("*") if p.is_file())


def fake_store() -> FakeStore:
    store = get_store()
    assert isinstance(store, FakeStore)
    return store
