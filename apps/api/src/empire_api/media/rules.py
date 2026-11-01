"""Who may hold what: owners (`project:<id>`, …), the roles each owner type has, the kinds each
role accepts, and the honest-label rules for a library item.

Collaborators: links.py, uploads.py and library.py apply these; vocab.py holds the lists.
Implements: the Phase 4 part 2 rules (roles per owner, PDF-only brochures, floor plans as image
or PDF), ARCHITECTURE §6 (exclusive arc).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import Final

from sqlalchemy import ColumnElement

from empire_api.errors import ApiProblem
from empire_api.media.models import Media, MediaLink
from empire_api.media.vocab import (
    CONTENT_OWNER_TYPES,
    LABEL_REQUIRED_ROLES,
    ROLES_BY_OWNER,
    OwnerType,
)
from empire_api.timeutil import today_ist

# The hero/cover image decision is recorded in D-038: the pinned cover if visible and labelled,
# otherwise the first visible labelled gallery photo. Attaching explicit hero or og_image links
# is refused; hero comes from gallery cover and og_image comes from seo.og_image_id.
REFUSED_ROLES: Final = {
    "hero": "The main image is the gallery cover: pin a photo as the cover instead.",
    "og_image": "Set the SEO share image (seo.og_image_id) instead of attaching one.",
}
# COMPLIANCE (AGENTS.md "Honest content"): what a photo shows must be labelled before it can
# appear on the website.
LABEL_FIRST: Final = (
    "Add an honest label (artist's impression, actual photo or progress photo) before showing "
    "it on the website."
)
OWNER_LABELS: Final = {
    "project": "A project",
    "configuration": "A configuration",
    "construction_update": "A construction update",
    "page": "A page",
    "post": "A post",
}
# The links of pages and posts mirror their blocks and covers (media/content_links.py).
CONTENT_LINK: Final = "This file is used by a page or a post. Change it in the page or post editor."
ROLE_LABELS: Final = {
    "gallery": "photos",
    "floor_plan": "floor plan",
    "brochure": "brochure",
    "rera_qr": "RERA QR code",
    "video": "videos",
    "document": "documents",
    "hero": "hero image",
    "og_image": "share image",
    "block": "page block",
    "cover": "cover image",
}
# The ProjectAdmin field (or collection) a role's links show up in, for `project.updated`.
CHANGED_FIELD: Final = {
    ("project", "gallery"): "gallery",
    ("project", "video"): "videos",
    ("project", "document"): "documents",
    ("project", "brochure"): "brochure",
    ("project", "rera_qr"): "rera",
    ("project", "hero"): "hero",
    ("project", "og_image"): "seo",
    ("configuration", "floor_plan"): "configurations",
    ("construction_update", "gallery"): "construction_updates",
}


@dataclass(frozen=True)
class Owner:
    """One end of the exclusive arc: what a link (or an upload's `attach_to`) belongs to."""

    type: OwnerType
    id: uuid.UUID

    @classmethod
    def parse(cls, attach_to: str) -> Owner:
        """`project:<uuid>` → Owner (the schema has already checked the shape)."""
        owner_type, _, owner_id = attach_to.partition(":")
        if owner_type not in ROLES_BY_OWNER or owner_type in CONTENT_OWNER_TYPES:
            raise ApiProblem(422, "Unknown owner type.")
        return cls(type=owner_type, id=uuid.UUID(owner_id))  # type: ignore[arg-type]

    @classmethod
    def of(cls, link: MediaLink) -> Owner:
        if link.project_id is not None:
            return cls("project", link.project_id)
        if link.configuration_id is not None:
            return cls("configuration", link.configuration_id)
        if link.page_id is not None:
            return cls("page", link.page_id)
        if link.post_id is not None:
            return cls("post", link.post_id)
        assert link.construction_update_id is not None  # noqa: S101 — ck_media_link_one_owner
        return cls("construction_update", link.construction_update_id)

    @property
    def is_content(self) -> bool:
        """A page or post: its links are managed by the content module, not the CMS media
        endpoints (CONTENT_LINK)."""
        return self.type in CONTENT_OWNER_TYPES

    @property
    def column(self) -> str:
        return f"{self.type}_id"

    def matches(self) -> ColumnElement[bool]:
        """SQL condition: a link belongs to this owner."""
        result: ColumnElement[bool] = getattr(MediaLink, self.column) == self.id
        return result

    def __str__(self) -> str:
        return f"{self.type}:{self.id}"


def check_role(owner: Owner, role: str, media: Media) -> None:
    """422 unless this owner type has `role` and the role accepts this file."""
    if role in REFUSED_ROLES:
        raise _invalid("role", REFUSED_ROLES[role])
    roles = ROLES_BY_OWNER[owner.type]
    if role not in roles:
        allowed = ", ".join(sorted(roles))
        raise _invalid("role", f"{OWNER_LABELS[owner.type]} can hold: {allowed}.")
    accepts = roles[role]
    if (media.kind, None) in accepts or (media.kind, media.format) in accepts:
        return
    raise _invalid("media_id", f"The {ROLE_LABELS[role]} must be {_describe(accepts)}.")


def _describe(accepts: frozenset[tuple[str, str | None]]) -> str:
    words = {
        ("image", None): "an image",
        ("video", None): "a video",
        ("document", None): "a document",
        ("document", "pdf"): "a PDF",
    }
    return " or ".join(sorted(words.get(item, "a file") for item in accepts))


def _invalid(field: str, message: str) -> ApiProblem:
    return ApiProblem(422, message, errors=[{"field": field, "message": message}])


def normalise_month(value: date | None) -> date | None:
    """Any day of a month → the first day. A month after the current one (IST) is refused.

    COMPLIANCE: a progress photo labelled with a month that hasn't happened would be false.
    """
    if value is None:
        return None
    month = value.replace(day=1)
    if month > today_ist().replace(day=1):
        raise _invalid("label_month", "The month can't be in the future.")
    return month


def needs_label(media: Media, role: str) -> bool:
    """COMPLIANCE: an unlabelled photo can't be visible in a photo list (gallery, hero).

    Sample placeholders are exempt: they are never shown on the live site (D-015).
    """
    return (
        role in LABEL_REQUIRED_ROLES
        and media.kind == "image"
        and media.label is None
        and not media.is_sample
    )


def check_label(kind: str, label: str | None) -> None:
    """Labels describe photos and videos; a document has none."""
    if label is not None and kind == "document":
        raise _invalid("label", "Labels are for photos and videos, not documents.")
