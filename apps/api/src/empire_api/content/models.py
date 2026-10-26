"""Tables of the content module (ARCHITECTURE §4, §6, §8).

Part 3: `consent_text`, the versioned wording a form shows next to its consent checkbox.
Part 4: `page` and its `block` rows, `post`, `faq`, `offer` and `testimonial`. Pages' and posts'
media (block images, post covers) are `media_link` rows (media/models.py, exclusive arc);
offers and testimonials point at the library directly.

Collaborators: migrations/versions/0004_leads.py and 0005_content.py create these tables
(tests/test_migrations.py fails on any drift); consent.py, pages.py, page_blocks.py, posts.py,
faqs.py, offers.py and testimonials.py are the only writers; leads/models.py `lead_consent`
points at the consent version a visitor accepted.

INVARIANT: at most one current text per kind (`uq_consent_text_current_kind`), a current text is
always published (`ck_consent_text_current_is_published`), and versions are unique per kind.
COMPLIANCE: a text is never edited once written; a change is a new version (DPDP: the lead's
consent record must keep pointing at the exact words the visitor saw). No code path updates
`body` or `checkbox_label`.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empire_api.content.vocab import BLOCK_TYPES, CONSENT_KINDS, OFFER_PLACEMENTS, PAGE_KINDS
from empire_api.db import Base, created_at_column, uuid_pk
from empire_api.projects.vocab import PUBLISH_STATES, check_in


class ConsentText(Base):
    """One version of one kind of consent wording (contract schema ConsentText)."""

    __tablename__ = "consent_text"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column()
    body: Mapped[str] = mapped_column(Text)
    checkbox_label: Mapped[str] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column()
    is_current: Mapped[bool] = mapped_column(server_default=sql("false"))
    # WHY no foreign key: like project.created_by, authorship outlives any staff account row.
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    # Who first published this version (with `published_at`); NULL for seeded texts (part 5).
    published_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("kind", "version"),
        Index(
            "uq_consent_text_current_kind",
            "kind",
            unique=True,
            postgresql_where=sql("is_current"),
        ),
        CheckConstraint(check_in("kind", CONSENT_KINDS), name="kind_valid"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("NOT is_current OR published_at IS NOT NULL", name="current_is_published"),
    )


# --- Part 4: pages, blocks, posts, FAQs, offers, testimonials -------------------------------


class Page(Base):
    """A CMS page (contract schema Page). Its blocks are `block` rows, in order.

    INVARIANT: `published_at` is set on the first publish and never cleared, so NULL means the
    page was never on the website (only those drafts may be deleted, pages.delete_page).
    INVARIANT: `is_required` marks the pages the website can't do without: every system page
    (home, about, contact, projects) and the seeded legal pages (privacy, terms, disclaimer).
    Only the seed sets it; such a page keeps its slug and kind and is never deleted or archived
    (pages.py, review L8), so the seed can find it by slug.
    """

    __tablename__ = "page"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(120))
    kind: Mapped[str] = mapped_column(String(10), server_default=sql("'standard'"))
    publish_state: Mapped[str] = mapped_column(String(12), server_default=sql("'draft'"))
    publish_at: Mapped[datetime | None] = mapped_column()
    unpublish_at: Mapped[datetime | None] = mapped_column()
    published_at: Mapped[datetime | None] = mapped_column()
    show_in_nav: Mapped[bool] = mapped_column(server_default=sql("false"))
    nav_order: Mapped[int | None] = mapped_column()
    # Shown on legal pages as "Version …" (NoirLegal board); staff set it when the text changes.
    legal_version: Mapped[str | None] = mapped_column(String(20))
    seo: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    translations: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    is_required: Mapped[bool] = mapped_column(server_default=sql("false"))
    # WHY no foreign keys: like project.created_by, authorship outlives any staff account row.
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    blocks: Mapped[list[PageBlock]] = relationship(
        order_by="(PageBlock.sort_order, PageBlock.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(check_in("kind", PAGE_KINDS), name="kind_valid"),
        CheckConstraint(check_in("publish_state", PUBLISH_STATES), name="publish_state_valid"),
        CheckConstraint(
            "publish_at IS NULL OR unpublish_at IS NULL OR unpublish_at > publish_at",
            name="unpublish_after_publish",
        ),
        CheckConstraint("legal_version IS NULL OR kind = 'legal'", name="legal_version_on_legal"),
        CheckConstraint("nav_order IS NULL OR nav_order >= 0", name="nav_order_not_negative"),
        CheckConstraint("kind <> 'system' OR is_required", name="system_is_required"),
        CheckConstraint(
            "NOT is_required OR kind IN ('system', 'legal')", name="required_is_system_or_legal"
        ),
    )


class PageBlock(Base):
    """One block of a page: its type, its validated `data` (content/blocks.py) and its place."""

    __tablename__ = "block"

    id: Mapped[uuid.UUID] = uuid_pk()
    page_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("page.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(16))
    data: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))
    is_visible: Mapped[bool] = mapped_column(server_default=sql("true"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_block_page_id_sort_order", "page_id", "sort_order"),
        CheckConstraint(check_in("type", BLOCK_TYPES), name="type_valid"),
    )


class Post(Base):
    """A blog or news post (contract schema Post). The cover is a `media_link` (role `cover`).

    INVARIANT: `published_at` is set on the first publish and kept (the article's date).
    """

    __tablename__ = "post"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    excerpt: Mapped[str | None] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    category: Mapped[str | None] = mapped_column(String(40))
    tags: Mapped[list[str]] = mapped_column(ARRAY(String(40)), server_default=sql("'{}'"))
    # The staff member who created it (contract `author`); no foreign key, like created_by.
    author_id: Mapped[uuid.UUID | None] = mapped_column()
    publish_state: Mapped[str] = mapped_column(String(12), server_default=sql("'draft'"))
    published_at: Mapped[datetime | None] = mapped_column()
    seo: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    translations: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index("ix_post_publish_state_published_at", "publish_state", sql("published_at DESC")),
        CheckConstraint(check_in("publish_state", PUBLISH_STATES), name="publish_state_valid"),
    )


class Faq(Base):
    """A question and answer, site-wide (`project_id` NULL) or for one project, in order."""

    __tablename__ = "faq"

    id: Mapped[uuid.UUID] = uuid_pk()
    # WHY CASCADE: only never-published drafts can be deleted (projects/service.py), so their
    # FAQs were never on the website.
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE")
    )
    question: Mapped[str] = mapped_column(String(200))
    answer: Mapped[str] = mapped_column(Text)
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))
    is_visible: Mapped[bool] = mapped_column(server_default=sql("true"))
    translations: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (Index("ix_faq_project_id_sort_order", "project_id", "sort_order"),)


class Offer(Base):
    """An offer or banner, shown only between `starts_at` and `ends_at` while active.

    COMPLIANCE (AGENTS.md "No fake urgency"): there is no countdown column, and the website
    shows the end date as plain text. `went_live_at` records that the offer has been shown:
    such an offer stays for the record (offers.delete_offer). `is_live_announced` remembers the
    last `offer.started`/`offer.ended` sent, so the schedule tick sends each exactly once.
    INVARIANT: a project-placement offer names its project (CHECK
    `ck_offer_project_placement_has_project`); a project an offer names can't be deleted
    (projects/service.delete_project, and the RESTRICT foreign key as a backstop; review L12).
    """

    __tablename__ = "offer"

    id: Mapped[uuid.UUID] = uuid_pk()
    title: Mapped[str] = mapped_column(String(120))
    body: Mapped[str | None] = mapped_column(String(500))
    # WHY RESTRICT (the default): a file an offer shows can't vanish from the library.
    image_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.id"), index=True)
    cta_label: Mapped[str | None] = mapped_column(String(40))
    cta_url: Mapped[str | None] = mapped_column(String(500))
    terms: Mapped[str | None] = mapped_column(String(250))
    terms_url: Mapped[str | None] = mapped_column(String(500))
    # WHY RESTRICT: an offer placed on a project page would otherwise lose its project and break
    # the placement rule (review L12); the project can only be deleted once no offer names it.
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"), index=True)
    placement: Mapped[str] = mapped_column(String(10))
    starts_at: Mapped[datetime | None] = mapped_column()
    ends_at: Mapped[datetime | None] = mapped_column()
    is_active: Mapped[bool] = mapped_column(server_default=sql("false"))
    priority: Mapped[int] = mapped_column(server_default=sql("0"))
    went_live_at: Mapped[datetime | None] = mapped_column()
    is_live_announced: Mapped[bool] = mapped_column(server_default=sql("false"))
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(check_in("placement", OFFER_PLACEMENTS), name="placement_valid"),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at", name="ends_after_starts"
        ),
        CheckConstraint("(cta_label IS NULL) = (cta_url IS NULL)", name="cta_label_with_url"),
        CheckConstraint("priority BETWEEN 0 AND 1000", name="priority_range"),
        CheckConstraint(
            "placement <> 'project' OR project_id IS NOT NULL",
            name="project_placement_has_project",
        ),
    )


class Testimonial(Base):
    """A real buyer's words, shown only with a recorded source and consent date.

    COMPLIANCE (AGENTS.md "Honest content"): there is no sample flag, because a sample
    testimonial must never exist; the sample seed creates none. INVARIANT: a visible
    testimonial has a source and a consent date (`ck_testimonial_visible_needs_consent`).
    """

    __tablename__ = "testimonial"

    id: Mapped[uuid.UUID] = uuid_pk()
    person_name: Mapped[str] = mapped_column(String(80))
    person_detail: Mapped[str | None] = mapped_column(String(120))
    quote: Mapped[str] = mapped_column(Text)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str] = mapped_column(String(160))
    source_url: Mapped[str | None] = mapped_column(String(500))
    consent_date: Mapped[date | None] = mapped_column()
    rating: Mapped[int | None] = mapped_column(SmallInteger)
    photo_media_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("media.id"), index=True)
    is_visible: Mapped[bool] = mapped_column(server_default=sql("false"))
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("rating IS NULL OR rating BETWEEN 1 AND 5", name="rating_range"),
        CheckConstraint(
            "NOT is_visible OR (consent_date IS NOT NULL AND length(btrim(source)) >= 3)",
            name="visible_needs_consent",
        ),
    )
