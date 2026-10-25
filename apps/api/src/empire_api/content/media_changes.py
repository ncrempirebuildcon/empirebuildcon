"""Service function the media module calls when a library item's details change (title, alt
text, honest label): the live content that shows the item is revalidated at once (review L2).

Collaborators: media/library.py (update_media, the caller); pages.page_event, posts.post_event,
offers.offer_event, testimonials.testimonial_event (the events); offers_state.py (is the offer
live now).
Implements: ARCHITECTURE §5 (revalidation tags), §9 (`page.updated`, `post.updated`,
`offer.changed`, `testimonial.changed`).

COMPLIANCE (AGENTS.md "Honest content"): relabelling a photo from "actual photo" to "artist's
impression" must reach the website at once, not at the hourly safety revalidation. Only live
content gets an event (published pages and posts, offers live now, shown testimonials), like
every other content event. No commit: the media update commits once.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.content import offers_state
from empire_api.content.models import Offer, Page, Post, Testimonial
from empire_api.content.offers import offer_event
from empire_api.content.pages import page_event
from empire_api.content.posts import post_event
from empire_api.content.testimonials import testimonial_event
from empire_api.projects.common import Actor
from empire_api.timeutil import utcnow


def _live[Published: (Page, Post)](
    db: Session, model: type[Published], linked: Iterable[uuid.UUID], media_id: uuid.UUID
) -> list[Published]:
    """Published pages or posts that link the item (blocks, cover) or use it as share image."""
    shares = select(model.id).where(model.seo["og_image_id"].astext == str(media_id))
    ids = set(linked) | set(db.scalars(shares))
    if not ids:
        return []
    return list(
        db.scalars(
            select(model)
            .where(model.id.in_(ids), model.publish_state == "published")
            .order_by(model.id)
        )
    )


def media_details_changed(
    db: Session,
    actor: Actor,
    media_id: uuid.UUID,
    linked_pages: Iterable[uuid.UUID],
    linked_posts: Iterable[uuid.UUID],
) -> None:
    """Emit the content events for a changed library item (module header).

    `linked_pages` / `linked_posts` own the item's `media_link` rows (the media module knows
    them); share images, offer images and testimonial photos are found here.
    """
    for page in _live(db, Page, linked_pages, media_id):
        page_event(db, actor, page, "page.updated", changed=["media"], media_id=media_id)
    for post in _live(db, Post, linked_posts, media_id):
        post_event(db, actor, post, "post.updated", changed=["media"], media_id=media_id)
    now = utcnow()
    offers = db.scalars(select(Offer).where(Offer.image_media_id == media_id).order_by(Offer.id))
    for offer in offers:
        if offers_state.is_live(offer, now):
            offer_event(db, actor, offer, "offer.changed", now, media_id=media_id)
    shown = db.scalars(
        select(Testimonial)
        .where(Testimonial.photo_media_id == media_id, Testimonial.is_visible.is_(True))
        .order_by(Testimonial.id)
    )
    for testimonial in shown:
        testimonial_event(db, actor, testimonial, "photo", media_id=media_id)
