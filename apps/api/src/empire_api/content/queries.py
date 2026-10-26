"""Read-only service functions other modules call about content: what is live at a website
address (seo/redirects.py: a manual redirect must not hide it), and where content names a
project (projects/service.py: such a project can't be deleted).

Collaborators: seo/redirects.py, projects/service.py; models.py (the only tables read here).
Implements: ARCHITECTURE §2 (modules call service functions, never another module's tables);
review findings L5 and L12.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from empire_api.content.models import Faq, Offer, Page, PageBlock, Post

# How a block that names a project is described to staff ("page “X” (a map block)").
BLOCK_WORDS: Final = {
    "map": "a map block",
    "lead_form": "an enquiry form block",
    "faq_list": "an FAQ list block",
    "testimonials": "a testimonials block",
}


def live_title(db: Session, kind: str, slug: str) -> str | None:
    """The title of the published page or post with this slug, if any."""
    model = Page if kind == "page" else Post
    return db.scalar(
        select(model.title).where(model.slug == slug, model.publish_state == "published")
    )


def project_uses(db: Session, project_id: uuid.UUID) -> list[str]:
    """Where content names the project, in words for staff: page blocks that name it or pick
    one of its FAQs (which go with the project), and offers that name it. Empty = none.

    WHY the FAQ picks count: a project's FAQs are deleted with it (CASCADE), which would leave
    a block pointing at FAQs that no longer exist.
    """
    named = [PageBlock.data.contains({"project_id": str(project_id)})]
    faq_ids = db.scalars(select(Faq.id).where(Faq.project_id == project_id)).all()
    named += [PageBlock.data.contains({"faq_ids": [str(faq_id)]}) for faq_id in faq_ids]
    blocks = db.execute(
        select(Page.title, PageBlock.type)
        .join(Page, Page.id == PageBlock.page_id)
        .where(or_(*named))
        .order_by(Page.title, PageBlock.sort_order)
    )
    found = [f"page “{row.title}” ({BLOCK_WORDS.get(row.type, 'a block')})" for row in blocks]
    offers = db.scalars(
        select(Offer.title).where(Offer.project_id == project_id).order_by(Offer.title)
    )
    found += [f"offer “{title}”" for title in offers]
    return list(dict.fromkeys(found))
