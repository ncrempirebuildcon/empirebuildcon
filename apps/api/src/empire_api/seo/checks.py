"""The `seo` JSON on pages and posts: the checks that need the database, and the warnings the
CMS checklist shows (ARCHITECTURE §16; design contract schema Seo).

Collaborators: content/pages.py and posts.py (validate on save), content/present.py (warnings);
media/queries.py (the share image is a library image). The shape itself (title ≤ 70,
description ≤ 170, canonical_path a site path, noindex) is projects/schemas_shared.Seo.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Final

from sqlalchemy.orm import Session

from empire_api.media import queries as media_queries
from empire_api.projects.common import FieldError
from empire_api.seo.schemas import SeoWarning

# Search engines cut titles and descriptions at about these lengths (the hard limits are 70 and
# 170, the contract's maxLength).
TITLE_SHOWN: Final = 60
DESCRIPTION_SHOWN: Final = 160
SHARE_IMAGE: Final = "Choose an image from the media library."


def check_seo(db: Session, seo: Mapping[str, Any]) -> list[FieldError]:
    """The share image must be an image in the library (read FOR SHARE, so a library delete
    can't pass this save; media/queries.is_library_image)."""
    og_image_id = seo.get("og_image_id")
    if og_image_id and not media_queries.is_library_image(db, uuid.UUID(str(og_image_id))):
        return [FieldError("seo.og_image_id", SHARE_IMAGE)]
    return []


def seo_warnings(seo: Mapping[str, Any], title: str) -> list[SeoWarning]:
    """The CMS checklist: what is missing or will be cut off in search results. Never blocks."""
    warnings: list[SeoWarning] = []
    seo_title = (seo.get("title") or "").strip()
    shown_title = seo_title or title
    if not seo_title:
        warnings.append(
            SeoWarning(
                code="title_missing",
                field="seo.title",
                message="No SEO title: search results will show the page title instead.",
            )
        )
    if len(shown_title) > TITLE_SHOWN:
        warnings.append(
            SeoWarning(
                code="title_long",
                field="seo.title" if seo_title else "title",
                message=f"The title is over {TITLE_SHOWN} characters; search engines may cut it.",
            )
        )
    description = (seo.get("description") or "").strip()
    if not description:
        warnings.append(
            SeoWarning(
                code="description_missing",
                field="seo.description",
                message="No description: search engines will pick some text from the page.",
            )
        )
    elif len(description) > DESCRIPTION_SHOWN:
        warnings.append(
            SeoWarning(
                code="description_long",
                field="seo.description",
                message=f"The description is over {DESCRIPTION_SHOWN} characters; search "
                "engines may cut it.",
            )
        )
    if seo.get("noindex"):
        warnings.append(
            SeoWarning(
                code="noindex",
                field="seo.noindex",
                message="Search engines are asked not to list this page (noindex).",
            )
        )
    return warnings
