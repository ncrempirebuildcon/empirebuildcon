"""Content rows → the API shapes: pages (with blocks, the media they use, SEO warnings and
publish blockers), posts, FAQs, offers and testimonials.

Collaborators: routes_pages.py, routes_marketing.py; page_rules.py (blockers, draft text),
seo/checks.py (warnings), seo/paths.py (addresses), media/content_links.py (library items),
users/directory.py (names), projects/queries.py (project names). Nothing here writes.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from empire_api.content import block_refs, page_rules
from empire_api.content.block_types import Block
from empire_api.content.blocks import video_watch_url
from empire_api.content.models import Faq as FaqRow
from empire_api.content.models import Offer as OfferRow
from empire_api.content.models import Page as PageRow
from empire_api.content.models import PageBlock
from empire_api.content.models import Post as PostRow
from empire_api.content.models import Testimonial as TestimonialRow
from empire_api.content.offers_state import state_of
from empire_api.content.schemas_marketing import Faq, Offer, Testimonial
from empire_api.content.schemas_pages import Page, PageSummary, Post, PostSummary
from empire_api.media import content_links
from empire_api.media.schemas import Media
from empire_api.projects import queries as project_queries
from empire_api.projects.schemas_shared import Seo, Translations
from empire_api.seo.checks import seo_warnings
from empire_api.seo.paths import page_path, post_path
from empire_api.users.directory import user_refs
from empire_api.users.schemas import UserRef


def _names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, UserRef]:
    return user_refs(db, ids)


def project_names(db: Session, ids: Iterable[uuid.UUID | None]) -> dict[uuid.UUID, str]:
    return {key: ref.name for key, ref in project_queries.project_refs(db, ids).items()}


# --- Pages -----------------------------------------------------------------------------------


def _share_image_id(seo: dict[str, Any]) -> uuid.UUID | None:
    value = seo.get("og_image_id")
    return uuid.UUID(str(value)) if value else None


def block_out(row: PageBlock) -> Block:
    data: dict[str, Any] = dict(row.data)
    if row.type == "video" and data.get("provider") and data.get("video_id"):
        data["url"] = video_watch_url(str(data["provider"]), str(data["video_id"]))
    return Block.model_validate(
        {
            "id": row.id,
            "type": row.type,
            "data": data,
            "sort_order": row.sort_order,
            "is_visible": row.is_visible,
        }
    )


def page_summary(row: PageRow, users: dict[uuid.UUID, UserRef]) -> PageSummary:
    return PageSummary(
        id=row.id,
        slug=row.slug,
        path=page_path(row.slug),
        title=row.title,
        kind=row.kind,
        publish_state=row.publish_state,
        publish_at=row.publish_at,
        unpublish_at=row.unpublish_at,
        published_at=row.published_at,
        show_in_nav=row.show_in_nav,
        nav_order=row.nav_order,
        legal_version=row.legal_version,
        is_draft_text=page_rules.is_draft_text(row),
        is_sample=row.is_sample,
        is_required=row.is_required,
        block_count=len(row.blocks),
        updated_at=row.updated_at,
        updated_by=users.get(row.updated_by) if row.updated_by else None,
    )


def page_summaries(db: Session, rows: Sequence[PageRow]) -> list[PageSummary]:
    users = _names(db, (row.updated_by for row in rows))
    return [page_summary(row, users) for row in rows]


def page_out(db: Session, row: PageRow) -> Page:
    users = _names(db, (row.created_by, row.updated_by))
    blocks = [block_out(block) for block in row.blocks]
    used = block_refs.collect([block.root for block in blocks]).media_ids()
    share = _share_image_id(row.seo)
    if share is not None and share not in used:
        used.append(share)
    items = content_links.library_items(db, used)
    return Page(
        **page_summary(row, users).model_dump(),
        blocks=blocks,
        media=[items[media_id] for media_id in used if media_id in items],
        seo=Seo.model_validate(row.seo),
        og_image=items.get(share) if share else None,
        seo_warnings=seo_warnings(row.seo, row.title),
        translations=Translations(row.translations),
        publish_blockers=page_rules.page_blockers(row),
        created_at=row.created_at,
        created_by=users.get(row.created_by) if row.created_by else None,
    )


# --- Posts -----------------------------------------------------------------------------------


def _post_fields(
    row: PostRow, cover: Media | None, users: dict[uuid.UUID, UserRef]
) -> dict[str, Any]:
    return {
        "id": row.id,
        "slug": row.slug,
        "path": post_path(row.slug),
        "title": row.title,
        "excerpt": row.excerpt,
        "category": row.category,
        "tags": list(row.tags),
        "cover": cover,
        "author": users.get(row.author_id) if row.author_id else None,
        "publish_state": row.publish_state,
        "published_at": row.published_at,
        "is_sample": row.is_sample,
        "updated_at": row.updated_at,
    }


def post_summaries(db: Session, rows: Sequence[PostRow]) -> list[PostSummary]:
    covers = content_links.post_covers(db, (row.id for row in rows))
    users = _names(db, (row.author_id for row in rows))
    return [PostSummary(**_post_fields(row, covers.get(row.id), users)) for row in rows]


def post_out(db: Session, row: PostRow) -> Post:
    cover = content_links.post_covers(db, [row.id]).get(row.id)
    users = _names(db, (row.author_id, row.updated_by))
    share = _share_image_id(row.seo)
    return Post(
        **_post_fields(row, cover, users),
        body=row.body,
        seo=Seo.model_validate(row.seo),
        og_image=content_links.library_items(db, [share]).get(share) if share else None,
        seo_warnings=seo_warnings(row.seo, row.title),
        translations=Translations(row.translations),
        publish_blockers=page_rules.post_blockers(row),
        created_at=row.created_at,
        updated_by=users.get(row.updated_by) if row.updated_by else None,
    )


# --- FAQs, offers, testimonials ----------------------------------------------------------------


def faqs_out(db: Session, rows: Sequence[FaqRow]) -> list[Faq]:
    names = project_names(db, (row.project_id for row in rows))
    return [
        Faq(
            id=row.id,
            project_id=row.project_id,
            project_name=names.get(row.project_id) if row.project_id else None,
            question=row.question,
            answer=row.answer,
            sort_order=row.sort_order,
            is_visible=row.is_visible,
            translations=Translations(row.translations),
            is_sample=row.is_sample,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def offers_out(db: Session, rows: Sequence[OfferRow], now: datetime) -> list[Offer]:
    names = project_names(db, (row.project_id for row in rows))
    images = content_links.library_items(db, (row.image_media_id for row in rows))
    return [
        Offer(
            id=row.id,
            title=row.title,
            body=row.body,
            image=images.get(row.image_media_id) if row.image_media_id else None,
            cta_label=row.cta_label,
            cta_url=row.cta_url,
            terms=row.terms,
            terms_url=row.terms_url,
            project_id=row.project_id,
            project_name=names.get(row.project_id) if row.project_id else None,
            placement=row.placement,
            starts_at=row.starts_at,
            ends_at=row.ends_at,
            is_active=row.is_active,
            priority=row.priority,
            state=state_of(row, now),
            has_been_live=row.went_live_at is not None,
            is_sample=row.is_sample,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]


def testimonials_out(db: Session, rows: Sequence[TestimonialRow]) -> list[Testimonial]:
    names = project_names(db, (row.project_id for row in rows))
    photos = content_links.library_items(db, (row.photo_media_id for row in rows))
    return [
        Testimonial(
            id=row.id,
            person_name=row.person_name,
            person_detail=row.person_detail,
            quote=row.quote,
            project_id=row.project_id,
            project_name=names.get(row.project_id) if row.project_id else None,
            source=row.source,
            source_url=row.source_url,
            consent_date=row.consent_date,
            rating=row.rating,
            photo=photos.get(row.photo_media_id) if row.photo_media_id else None,
            is_visible=row.is_visible,
            can_show=bool(row.consent_date and len(row.source.strip()) >= 3),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
        for row in rows
    ]
