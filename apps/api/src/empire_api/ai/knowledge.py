"""Live public content → text chunks for the knowledge index (task 7.1, D-059).

The text comes from the PUBLIC API's own builders (`public.service`), so the assistant can only
ever know what a visitor can already see: the same publish, off-market, sample and visibility
rules apply, with no second copy of them to drift.

TODO(phase-7): English only for now (`locale` is always "en"); index the Hindi text too once
`locale_hi` is on and the live dry run (7.4) has checked Hindi answers.

COMPLIANCE: prices, rates and RERA registration numbers are left out of the text on purpose.
The assistant never writes them; the chat shows them from the database on the cited project's
card instead (D-059). Ids, links, media and SEO fields are left out too (no meaning to a reader).
"""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from collections.abc import Iterable
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.ai.store import Chunk
from empire_api.content.models import Page, Post
from empire_api.projects.models import Project
from empire_api.public import service as public

CHUNK_CHARS: Final = 1200  # about 350 tokens, the dry run's size
_SKIP_KEYS: Final = frozenset(
    {
        "id",
        "slug",
        "seo",
        "gallery",
        "videos",
        "documents",
        "brochure",
        "brochure_gated",
        "qr",
        "rera",
        "updated_at",
        "created_at",
        "sort_order",
        "is_visible",
        "is_sample",
        "media",
        "image",
        "images",
        "cover",
        "poster",
        "map",
        "coordinates",
        "lat",
        "lng",
        "price",
        "prices",
        "price_note",
        "rate",
        "rate_unit",
        "min_inr",
        "max_inr",
        "rate_inr",
        "on_request",
        "display_unit",
        "plan_image",
        "floor_plan",
        "url",
        "href",
        "link",
        "embed",
        "video_id",
        "floor_plans",
        "photos",
        "person_name",
        "person_detail",
        "rating",
        "limit",
        "show_status_tabs",
        "is_featured",
        "pin_source",
        "source",
    }
)
# Keys that only hold names of other keys' units or flags add noise; values only are kept.
_SKIP_SUFFIXES: Final = ("_id", "_ids", "_url", "_inr", "_media")


# COMPLIANCE (D-059): free text (descriptions, FAQ answers, posts, offers) can carry a price or
# a registration number too, so every line is also scrubbed by value. Over-matching is safe:
# the widget shows the real figures from the database on the project's card.
REDACTED: Final = "[see the project page]"
_MONEY: Final = re.compile(
    r"(?:₹|\brs\.?|\binr)\s*\d[\d,.]*(?:\s*(?:lakhs?|lacs?|crores?|cr|l|k|thousand))?\b"
    r"|\b\d[\d,.]*\s*(?:lakhs?|lacs?|crores?|cr)\b"
    r"|\d[\d,.]*\s*(?:लाख|करोड़)"
    r"|\b\d[\d,.]*\s*(?:/|per|a)\s*(?:sq\.?\s*(?:ft|feet|m|mtr|metre|meter|yd|yard)s?|sqft|sqm|sqyd)\b",
    re.IGNORECASE,
)
_REGISTRATION: Final = re.compile(
    r"\b[a-z]*rera[a-z]*[\s:#-]*(?:no\.?|number)?[\s:#-]*[a-z0-9/-]*\d[a-z0-9/-]*"
    r"|\b(?:prj|agt)[a-z0-9/-]*\d[a-z0-9/-]*",
    re.IGNORECASE,
)


def estimate_tokens(text: str) -> int:
    """About 3.5 characters a token (the dry run's measure; Hinglish is pessimistic)."""
    return max(1, math.ceil(len(text) / 3.5))


def redact(line: str) -> str:
    return _REGISTRATION.sub(REDACTED, _MONEY.sub(REDACTED, line))


def _keep(key: str) -> bool:
    k = key.lower()
    return k not in _SKIP_KEYS and not k.endswith(_SKIP_SUFFIXES) and "rera" not in k


def _lines(value: Any, label: str = "") -> Iterable[str]:
    """Flatten a dumped schema into readable "label: value" lines."""
    if value is None or value in ("", [], {}):
        return
    if isinstance(value, dict):
        for key, inner in value.items():
            if _keep(str(key)):
                yield from _lines(inner, str(key).replace("_", " "))
        return
    if isinstance(value, list):
        for item in value:
            if isinstance(item, dict) and label:
                # WHY one line per item: "configurations: name: 2 BHK; carpet sqft: 650" keeps
                # an item's facts together, so a chunk never mixes one flat's area with another.
                parts = list(_lines(item))
                if parts:
                    yield f"{label}: " + "; ".join(parts)
            else:
                yield from _lines(item, label)
        return
    if isinstance(value, bool):
        if value:
            yield f"{label}: yes" if label else "yes"
        return
    text = redact(str(value).strip())
    if text:
        yield f"{label}: {text}" if label else text


def _chunks(
    source_type: str, source_id: uuid.UUID, url: str, title: str, lines: list[str]
) -> list[Chunk]:
    out: list[str] = []
    buffer = f"{title}\n"
    for line in lines:
        if len(buffer) + len(line) + 1 > CHUNK_CHARS and buffer.strip() != title:
            out.append(buffer.strip())
            buffer = f"{title} (continued)\n"
        buffer += line[: CHUNK_CHARS - len(title) - 20] + "\n"
    if buffer.strip() and buffer.strip() != title:
        out.append(buffer.strip())
    return [
        Chunk(
            source_type=source_type,
            source_id=source_id,
            url=url,
            title=title[:200],
            position=i,
            body=body,
            tokens=estimate_tokens(body),
            content_hash=hashlib.sha256(f"{url}\n{body}".encode()).hexdigest(),
        )
        for i, body in enumerate(out)
    ]


def project_chunks(db: Session, project: Project) -> list[Chunk]:
    detail = public.get_public_project(db, project.slug)
    if detail is None:
        return []  # not live (draft, off market, archived, or a sample in production)
    data = detail.model_dump(mode="json")
    data.pop("name", None)
    return _chunks(
        "project", detail.id, f"/projects/{detail.slug}", detail.name, list(_lines(data))
    )


def page_chunks(db: Session, page: Page) -> list[Chunk]:
    detail = public.get_public_page(db, page.slug)
    if detail is None or detail.kind == "legal":
        return []  # legal pages aren't something to answer from (D-059: no legal advice)
    blocks = [b.data for b in detail.blocks if b.is_visible]
    url = "/" if page.slug in ("", "home") else f"/{detail.slug}"
    return _chunks("page", detail.id, url, detail.title, list(_lines(blocks)))


def post_chunks(db: Session, post: Post) -> list[Chunk]:
    detail = public.get_public_post(db, post.slug)
    if detail is None:
        return []
    data = detail.model_dump(mode="json")
    title = str(data.pop("title", "") or post.slug)
    return _chunks("post", detail.id, f"/blog/{detail.slug}", title, list(_lines(data)))


def all_sources(db: Session) -> list[tuple[str, Any]]:
    """Every candidate item; the builders above drop what isn't live."""
    projects = [("project", p) for p in db.scalars(select(Project))]
    pages = [("page", p) for p in db.scalars(select(Page))]
    posts = [("post", p) for p in db.scalars(select(Post))]
    return projects + pages + posts


def chunks_for(db: Session, source_type: str, item: Any) -> list[Chunk]:
    if source_type == "project":
        return project_chunks(db, item)
    if source_type == "page":
        return page_chunks(db, item)
    if source_type == "post":
        return post_chunks(db, item)
    return []
