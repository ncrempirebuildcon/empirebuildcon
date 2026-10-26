"""The ids page blocks name, and their checks against the database: library items (and their
kind and honest label), projects, cities, FAQs, testimonials and offers.

Collaborators: page_blocks.py (calls `collect` then `check` before saving), blocks.py and
block_types.py (the shapes); media/content_links.py and projects/queries.py (service functions
of the modules that own those rows).
Implements: the part 4 rule "media ids checked against the library (kind checked)"; COMPLIANCE
(AGENTS.md "Honest content", D-033): a photo a block shows needs an honest label, like a gallery
or hero photo; sample placeholders are exempt because they are never public (D-015).

Every problem becomes a field error at its exact place, e.g. `blocks.2.data.image_ids.4`.

INVARIANT (review L12): every row a block names is read FOR SHARE, held until the save commits.
A delete of that FAQ, testimonial, offer, project or city takes the row FOR UPDATE, so the two
can't pass each other: either the delete waits and then sees the new block (an FAQ or
testimonial delete takes its id out, an offer or project delete is refused), or this check runs
after the delete and reports the id as gone (422). Library items work the same way
(media/content_links.library_facts).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.content.block_types import AnyBlock, AnyBlockInput
from empire_api.content.blocks import (
    FaqListData,
    GalleryData,
    GridData,
    HeroData,
    ImageData,
    LeadFormData,
    MapData,
    OfferBannerData,
    TestimonialsData,
    VideoData,
)
from empire_api.content.models import Faq, Offer, Testimonial
from empire_api.media.content_links import library_facts
from empire_api.projects import queries as project_queries
from empire_api.projects.common import FieldError

NOT_IN_LIBRARY: Final = "This file is no longer in the media library. Choose another one."
LABEL_FIRST: Final = (
    "Give this photo an honest label (artist's impression, actual photo or progress photo) in "
    "the media library first; photos appear on the website only with one."
)
KIND_WORDS: Final = {"image": "an image", "video": "a video"}
MISSING: Final = {
    "project": "No project with this id.",
    "city": "No city with this id.",
    "faq": "This FAQ no longer exists. Remove it from the block.",
    "testimonial": "This testimonial no longer exists. Remove it from the block.",
    "offer": "No offer with this id.",
}

Ref = tuple[str, uuid.UUID]
_CONTENT_MODELS: Final[dict[str, type[Faq] | type[Testimonial] | type[Offer]]] = {
    "faq": Faq,
    "testimonial": Testimonial,
    "offer": Offer,
}


@dataclass(frozen=True)
class MediaRef:
    field: str
    media_id: uuid.UUID
    kind: str
    needs_label: bool


@dataclass
class Refs:
    """Everything a list of blocks points at, with the field each id came from."""

    media: list[MediaRef] = field(default_factory=list)
    others: dict[str, list[Ref]] = field(default_factory=dict)

    def add(self, what: str, place: str, value: uuid.UUID | None) -> None:
        if value is not None:
            self.others.setdefault(what, []).append((place, value))

    def media_ids(self) -> list[uuid.UUID]:
        """Library items in order of first use (the order of the page's media links)."""
        return list(dict.fromkeys(ref.media_id for ref in self.media))


def collect(blocks: Sequence[AnyBlockInput | AnyBlock]) -> Refs:
    """The ids named by blocks being saved (BlockInput) or already saved (Block)."""
    refs = Refs()
    for index, block in enumerate(blocks):
        at = f"blocks.{index}.data"
        data = block.data
        if isinstance(data, HeroData | ImageData) and data.image_id is not None:
            refs.media.append(MediaRef(f"{at}.image_id", data.image_id, "image", True))
        elif isinstance(data, GalleryData):
            for j, media_id in enumerate(data.image_ids):
                refs.media.append(MediaRef(f"{at}.image_ids.{j}", media_id, "image", True))
        elif isinstance(data, VideoData) and data.media_id is not None:
            refs.media.append(MediaRef(f"{at}.media_id", data.media_id, "video", False))
        elif isinstance(data, GridData):
            refs.add("city", f"{at}.city_id", data.city_id)
        elif isinstance(data, LeadFormData | MapData):
            refs.add("project", f"{at}.project_id", data.project_id)
        elif isinstance(data, FaqListData):
            refs.add("project", f"{at}.project_id", data.project_id)
            for j, faq_id in enumerate(data.faq_ids):
                refs.add("faq", f"{at}.faq_ids.{j}", faq_id)
        elif isinstance(data, TestimonialsData):
            refs.add("project", f"{at}.project_id", data.project_id)
            for j, item in enumerate(data.testimonial_ids):
                refs.add("testimonial", f"{at}.testimonial_ids.{j}", item)
        elif isinstance(data, OfferBannerData):
            refs.add("offer", f"{at}.offer_id", data.offer_id)
    return refs


def _existing(db: Session, what: str, ids: set[uuid.UUID]) -> set[uuid.UUID]:
    """The ids that exist, each row locked FOR SHARE until commit (module header)."""
    if what == "project":
        return set(project_queries.project_refs(db, ids, for_share=True))
    if what == "city":
        return project_queries.existing_city_ids(db, ids, for_share=True)
    model = _CONTENT_MODELS[what]
    return set(db.scalars(select(model.id).where(model.id.in_(ids)).with_for_update(read=True)))


def check(db: Session, refs: Refs) -> list[FieldError]:
    """Every id must exist; library items must be the right kind and photos labelled."""
    errors: list[FieldError] = []
    facts = library_facts(db, refs.media_ids())
    for ref in refs.media:
        found = facts.get(ref.media_id)
        if found is None:
            errors.append(FieldError(ref.field, NOT_IN_LIBRARY))
        elif found.kind != ref.kind:
            errors.append(FieldError(ref.field, f"Choose {KIND_WORDS[ref.kind]}."))
        elif ref.needs_label and not found.has_label and not found.is_sample:
            errors.append(FieldError(ref.field, LABEL_FIRST))
    for what, places in refs.others.items():
        existing = _existing(db, what, {value for _, value in places})
        errors += [
            FieldError(place, MISSING[what]) for place, value in places if value not in existing
        ]
    return errors
