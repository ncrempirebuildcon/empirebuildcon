"""Contract shapes `Media` and `LinkedMedia` (handbook/api/openapi-v1.yaml).

Defined now so project responses already carry their final types (`cover`, `gallery`,
`floor_plans`, `rera.qr`, …) and the generated web client doesn't change when media arrives.
TODO(phase-4): part 2 adds the media tables, upload routes and the service that fills these.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from empire_api.projects.fields import OutModel

MediaKind = Literal["image", "video", "document"]
MediaRole = Literal[
    "gallery", "floor_plan", "brochure", "rera_qr", "video", "document", "hero", "og_image"
]


class Media(OutModel):
    id: uuid.UUID
    kind: MediaKind
    url: str
    thumbnail_url: str | None
    title: str
    alt_text: str | None
    format: str
    bytes: int
    width: int | None
    height: int | None
    duration_s: float | None
    created_at: datetime


class LinkedMedia(Media):
    """A media item as attached to an owner (project, configuration, construction update)."""

    link_id: uuid.UUID
    role: MediaRole
    sort_order: int
    is_cover: bool
    is_visible: bool
