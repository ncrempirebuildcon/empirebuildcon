"""Service functions the media module calls about content that uses library items: page and
post share images (`seo.og_image_id`), offer images and testimonial photos, plus the names of
the pages and posts whose blocks and covers link to a file.

Collaborators: media/present.py (`attached_count`), media/library.py (delete refused while used,
the `unattached` filter, GET /admin/media/{id}/usage).
Implements: ARCHITECTURE §2 (modules call service functions, never another module's tables),
the part 4 rule "a library delete is refused while blocks, post covers, offer images or
testimonial photos use the item", and §16 (share images).

WHY not `media_link` for offers and testimonials: they hold one file in one fixed place, so a
plain RESTRICT foreign key says the same with less machinery; share images are a JSON field,
like projects' (projects/media_owners.py).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import Select, String, cast, select, union_all
from sqlalchemy.orm import Session

from empire_api.content.models import Offer, Page, Post, Testimonial


@dataclass(frozen=True)
class MediaUse:
    """One place a library item is used: what (`owner_type`, `owner_id`, `name`) and how."""

    owner_type: str
    owner_id: uuid.UUID
    name: str
    role: str


def _share(model: Any) -> Any:
    return model.seo["og_image_id"].astext


def used_media_ids() -> Select[Any]:
    """Ids (as text) of library items content uses outside `media_link`, for library filters."""
    return union_all(
        select(_share(Page)).where(_share(Page).is_not(None)),
        select(_share(Post)).where(_share(Post).is_not(None)),
        select(cast(Offer.image_media_id, String)).where(Offer.image_media_id.is_not(None)),
        select(cast(Testimonial.photo_media_id, String)).where(
            Testimonial.photo_media_id.is_not(None)
        ),
    )  # type: ignore[return-value]  # a CompoundSelect works wherever this is used (IN)


def use_counts(db: Session, media_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    """media id → uses outside `media_link` (share images, offer images, testimonial photos)."""
    if not media_ids:
        return {}
    texts = [str(media_id) for media_id in media_ids]
    counts: dict[uuid.UUID, int] = defaultdict(int)
    for model in (Page, Post):
        for value in db.scalars(select(_share(model)).where(_share(model).in_(texts))):
            counts[uuid.UUID(value)] += 1
    for column in (Offer.image_media_id, Testimonial.photo_media_id):
        for value in db.scalars(select(column).where(column.in_(media_ids))):
            if value is not None:
                counts[value] += 1
    return dict(counts)


def is_offer_image(db: Session, media_id: uuid.UUID) -> bool:
    """Whether an offer shows the item (its label can't be removed then; review L11)."""
    return db.scalar(select(Offer.id).where(Offer.image_media_id == media_id).limit(1)) is not None


def initials(name: str) -> str:
    """'Ravi Kumar Sharma' → 'R. K. S.' (the first letter or digit of each word)."""
    letters = [next((ch for ch in word if ch.isalnum()), "") for word in name.split()]
    return " ".join(f"{letter.upper()}." for letter in letters if letter)


def testimonial_use_name(person_name: str) -> str:
    """SECURITY.md §8 (review L9): anyone with `media.upload` sees where a file is used, so a
    testimonial is named by the person's initials, never their name."""
    letters = initials(person_name)
    return f"Testimonial photo ({letters})" if letters else "Testimonial photo"


def uses(
    db: Session, media_id: uuid.UUID, linked_pages: list[uuid.UUID], linked_posts: list[uuid.UUID]
) -> list[MediaUse]:
    """Every content use of one library item, with names (for the CMS and the 409 message).

    `linked_pages` / `linked_posts` are the owners of its `media_link` rows (media module).
    Testimonials are named by initials (`testimonial_use_name`).
    """
    text = str(media_id)
    found: list[MediaUse] = []
    for row in db.execute(select(Page.id, Page.title).where(Page.id.in_(linked_pages))):
        found.append(MediaUse("page", row.id, row.title, "block"))
    for row in db.execute(select(Post.id, Post.title).where(Post.id.in_(linked_posts))):
        found.append(MediaUse("post", row.id, row.title, "cover"))
    for model, kind in ((Page, "page"), (Post, "post")):
        for row in db.execute(select(model.id, model.title).where(_share(model) == text)):
            found.append(MediaUse(kind, row.id, row.title, "share_image"))
    for row in db.execute(select(Offer.id, Offer.title).where(Offer.image_media_id == media_id)):
        found.append(MediaUse("offer", row.id, row.title, "image"))
    testimonials = select(Testimonial.id, Testimonial.person_name).where(
        Testimonial.photo_media_id == media_id
    )
    for row in db.execute(testimonials):
        found.append(
            MediaUse("testimonial", row.id, testimonial_use_name(row.person_name), "photo")
        )
    return found
