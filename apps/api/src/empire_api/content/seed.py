"""Seed data for the content module: the system and legal pages every site has (`empire-api
seed`, every environment), and a sample post, offer and FAQs (`empire-api seed --sample`).

Collaborators: cli.py; models.py; projects/media_owners.py (the sample projects, for their FAQs).
Implements: D-015 (sample data), D-017 (legal text is drafted by Claude and approved by the
owner), D-018 (pages staff can edit and switch off), CODE_STYLE §7 (honest seeds).

COMPLIANCE:
  - System pages (home, about, contact, projects) and legal pages (privacy, terms, disclaimer)
    are created as drafts. Legal pages hold only the D-017 placeholder, so production refuses
    to publish them until the owner-approved wording replaces it. No legal text is written
    here: the drafting is Phase 8 (o-20).
  - All of them are required pages (`is_required`, review L8): their slug and kind can't
    change and they can't be deleted or archived, so matching them by slug on a re-run is safe
    (a renamed legal page can't leave its slug free for a second copy). The consent texts and
    the footer link to them.
  - Sample rows say SAMPLE in their titles, use `[bracketed]` placeholders for every fact, carry
    `is_sample = true`, stay drafts or switched off, and are refused in production.
  - There is no sample testimonial, ever: the website's testimonials stay hidden until a real
    one with a recorded source and consent is shown (honest empty state).
  - Seeding writes no outbox events: nothing here is a staff decision to publish.
Idempotent: rows are matched by slug (pages, posts) or title (offers, FAQs) and existing rows
are never changed, so staff edits survive a re-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content.models import Faq, Offer, Page, PageBlock, Post
from empire_api.content.vocab import LEGAL_DRAFT_MARK
from empire_api.projects.media_owners import sample_project_ids
from empire_api.timeutil import utcnow

# (slug, title, show in the main menu at this position or None).
SYSTEM_PAGES: Final = (
    ("home", "Home", None),
    ("projects", "Projects", 1),
    ("about", "About", 2),
    ("contact", "Contact", 3),
)
LEGAL_PAGES: Final = (
    ("privacy", "Privacy policy"),
    ("terms", "Terms of use"),
    ("disclaimer", "Disclaimer"),
)
SAMPLE_POST_SLUG: Final = "sample-buying-guide"
SAMPLE_OFFER_TITLE: Final = "SAMPLE — [Offer name]"
SAMPLE_FAQS: Final = (
    ("SAMPLE — [A question buyers often ask]?", "[Empire's answer. Replace it with the real one.]"),
    ("SAMPLE — [Another common question]?", "[Empire's answer. Replace it with the real one.]"),
)


class SampleContentRefusedError(RuntimeError):
    """Sample data is never added in production (D-015)."""


@dataclass(frozen=True)
class SampleContentResult:
    posts: int
    offers: int
    faqs: int


def seed_pages(db: Session) -> int:
    """The system and legal pages that don't exist yet, as drafts. Returns how many were added.
    Caller commits."""
    existing = set(db.scalars(select(Page.slug)))
    added = 0
    for slug, title, nav_order in SYSTEM_PAGES:
        if slug in existing:
            continue
        db.add(
            Page(
                slug=slug,
                title=title,
                kind="system",
                publish_state="draft",
                show_in_nav=nav_order is not None,
                nav_order=nav_order,
                is_required=True,
            )
        )
        added += 1
    for slug, title in LEGAL_PAGES:
        if slug in existing:
            continue
        page = Page(slug=slug, title=title, kind="legal", publish_state="draft", is_required=True)
        page.blocks.append(
            PageBlock(
                type="rich_text",
                data={"heading": None, "body": LEGAL_DRAFT_MARK},
                sort_order=0,
                is_visible=True,
            )
        )
        db.add(page)
        added += 1
    db.flush()
    return added


def seed_sample_content(db: Session) -> SampleContentResult:
    """A sample post (draft), offer (switched off) and FAQs, all `is_sample`. Caller commits.

    Raises:
        SampleContentRefusedError: APP_ENV is production.
    """
    if get_settings().app_env == "production":
        raise SampleContentRefusedError("Sample data is never added in production (D-015).")
    posts = offers = faqs = 0
    if db.scalar(select(Post.id).where(Post.slug == SAMPLE_POST_SLUG)) is None:
        db.add(
            Post(
                slug=SAMPLE_POST_SLUG,
                title="SAMPLE — [Buying guide title]",
                excerpt="[One-line summary of the article]",
                body="[Sample article text. Replace it with a real article before publishing.]",
                category="Buying guide",
                tags=["sample"],
                publish_state="draft",
                is_sample=True,
            )
        )
        posts += 1
    if db.scalar(select(Offer.id).where(Offer.title == SAMPLE_OFFER_TITLE)) is None:
        starts = utcnow().replace(microsecond=0) + timedelta(days=1)
        db.add(
            Offer(
                title=SAMPLE_OFFER_TITLE,
                body="[What the offer includes, who qualifies and until when]",
                placement="banner",
                starts_at=starts,
                ends_at=starts + timedelta(days=30),
                is_active=False,
                is_sample=True,
            )
        )
        offers += 1
    projects = sample_project_ids(db)
    for project_id in [None, *projects[:1]]:
        for order, (question, answer) in enumerate(SAMPLE_FAQS):
            found = db.scalar(
                select(Faq.id).where(
                    Faq.question == question,
                    Faq.project_id.is_(None)
                    if project_id is None
                    else Faq.project_id == project_id,
                )
            )
            if found is None:
                db.add(
                    Faq(
                        project_id=project_id,
                        question=question,
                        answer=answer,
                        sort_order=order,
                        is_visible=True,
                        is_sample=True,
                    )
                )
                faqs += 1
    db.flush()
    return SampleContentResult(posts=posts, offers=offers, faqs=faqs)
