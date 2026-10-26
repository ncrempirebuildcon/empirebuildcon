"""The fixed word lists and limits of the media module, in one place.

Tables use the lists for CHECK constraints and the schemas use them as `Literal` types, so the
database, the API and the generated web client always agree (same pattern as projects/vocab.py).

Implements: ARCHITECTURE §6 (media links), §12 (media), SECURITY.md §6 (uploads), D-007
(Cloudinary Free limits: 10 MB images and raw files, 100 MB video, 25 megapixels; re-checked on
cloudinary.com/documentation/pricing on 23 Oct 2026).

DO NOT CHANGE a stored value without a migration: rows already hold these strings, and the
CHECK constraints in migrations/versions/0003_media.py list them.
"""

from __future__ import annotations

from typing import Final, Literal, get_args

MediaKind = Literal["image", "video", "document"]
StoreName = Literal["cloudinary", "fake"]
ResourceType = Literal["image", "video", "raw"]
DirectKind = Literal["video", "document"]
OwnerType = Literal["project", "configuration", "construction_update", "page", "post"]
MediaRole = Literal[
    "gallery", "floor_plan", "brochure", "rera_qr", "video", "document", "hero", "og_image"
]
# Phase 4 part 4: pages and posts hold library items too (the exclusive arc's `page_id` and
# `post_id`). Their links mirror the page's blocks (`block`) and the post's cover (`cover`);
# only media/content_links.py writes them, and the media-links endpoints refuse them, so these
# roles never appear in the API's MediaRole.
ContentRole = Literal["block", "cover"]
CONTENT_OWNER_TYPES: Final = frozenset({"page", "post"})
# COMPLIANCE: honest labels (AGENTS.md "Honest content"): an artist's impression must never pass
# for a photo of the real building, and a progress photo always says which month it shows.
MediaLabel = Literal["artist_impression", "actual_photo", "progress_photo"]

MEDIA_KINDS: Final = get_args(MediaKind)
STORE_NAMES: Final = get_args(StoreName)
RESOURCE_TYPES: Final = get_args(ResourceType)
OWNER_TYPES: Final = get_args(OwnerType)
MEDIA_ROLES: Final = get_args(MediaRole)
LINK_ROLES: Final = (*MEDIA_ROLES, *get_args(ContentRole))
MEDIA_LABELS: Final = get_args(MediaLabel)
# Labels that may carry a month (an impression isn't of any particular month).
DATED_LABELS: Final = frozenset({"actual_photo", "progress_photo"})

MB: Final = 1024 * 1024
# The Cloudinary Free plan's per-file limits (D-007). Photos are also capped here by the API.
MAX_IMAGE_BYTES: Final = 10 * MB
MAX_VIDEO_BYTES: Final = 100 * MB
MAX_DOCUMENT_BYTES: Final = 10 * MB
MAX_IMAGE_PIXELS: Final = 25_000_000

# Photo formats accepted through POST /admin/media/images (SECURITY.md §6). Detected from the
# file's first bytes, never from its name or the browser's type (media/sniff.py).
IMAGE_FORMATS: Final = ("jpg", "png", "webp", "avif")

# Direct uploads: extension → (accepted browser types, resource type at the store).
# WHY PDFs are `image` at Cloudinary and Office files `raw`: Cloudinary stores PDFs as images by
# default (so a first-page thumbnail can be made and the original opens in the browser), while
# Office files can't be transformed at all and keep their extension in the public id.
# WHY Office types also accept "" and application/octet-stream: browsers on computers without
# Office installed often can't name these types, and the extension is checked as well.
_OFFICE_FALLBACK: Final = ("", "application/octet-stream")
VIDEO_TYPES: Final[dict[str, tuple[tuple[str, ...], ResourceType]]] = {
    "mp4": (("video/mp4",), "video"),
    "mov": (("video/quicktime",), "video"),
    "webm": (("video/webm",), "video"),
}
DOCUMENT_TYPES: Final[dict[str, tuple[tuple[str, ...], ResourceType]]] = {
    "pdf": (("application/pdf",), "image"),
    "doc": (("application/msword", *_OFFICE_FALLBACK), "raw"),
    "docx": (
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            *_OFFICE_FALLBACK,
        ),
        "raw",
    ),
    "ppt": (("application/vnd.ms-powerpoint", *_OFFICE_FALLBACK), "raw"),
    "pptx": (
        (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            *_OFFICE_FALLBACK,
        ),
        "raw",
    ),
}
DIRECT_TYPES: Final = {"video": VIDEO_TYPES, "document": DOCUMENT_TYPES}
DIRECT_MAX_BYTES: Final = {"video": MAX_VIDEO_BYTES, "document": MAX_DOCUMENT_BYTES}

# What each owner may hold: role → accepted (kind, format) pairs; format None = any format.
Accepts = frozenset[tuple[MediaKind, str | None]]
_IMAGE: Final[Accepts] = frozenset({("image", None)})
_PDF: Final[Accepts] = frozenset({("document", "pdf")})
ROLES_BY_OWNER: Final[dict[str, dict[str, Accepts]]] = {
    "project": {
        "gallery": _IMAGE,
        "video": frozenset({("video", None)}),
        "document": frozenset({("document", None)}),
        "brochure": _PDF,
        "rera_qr": _IMAGE,
        "hero": _IMAGE,
        "og_image": _IMAGE,
    },
    "configuration": {"floor_plan": _IMAGE | _PDF},
    "construction_update": {"gallery": _IMAGE},
    "page": {"block": _IMAGE | frozenset({("video", None)})},
    "post": {"cover": _IMAGE},
}
# INVARIANT: an owner holds at most one link in each of these roles (a partial unique index in
# 0003_media enforces it). Attaching a new item replaces the old link; the file stays in the
# library.
SINGLE_ROLES: Final = frozenset({"brochure", "rera_qr", "hero", "og_image", "floor_plan", "cover"})
# Only photo lists have a cover (the star on the board).
COVER_ROLES: Final = frozenset({"gallery"})
# COMPLIANCE: photos in these roles need an honest label before they can be shown (rules.py).
# `block`: every photo a page block shows is a hero, image or gallery photo (content/block_refs.py
# refuses an unlabelled one), so its label can't be removed while a page uses it. `cover`: a
# post cover often shows a render (content/posts.py refuses an unlabelled one, review L11).
LABEL_REQUIRED_ROLES: Final = frozenset({"gallery", "hero", "block", "cover"})

# Uploads and signatures per user per window (SECURITY.md §6; generous for a busy gallery day).
UPLOAD_LIMIT: Final = 120
UPLOAD_WINDOW_SECONDS: Final = 600
# How long a direct-upload intent can be confirmed: Cloudinary's own signature lifetime (one
# hour after its timestamp), so a 100 MB video on a slow uplink still makes it. One user, one
# use (UploadIntent) keeps the longer window safe.
INTENT_TTL_SECONDS: Final = 3600
# Room for clock differences between us and the store when deciding a signature is dead.
CLOCK_SKEW_SECONDS: Final = 600
