"""Business rules for the media library itself: list and search it, rename an item and set its
alt text and honest label, and delete an unused item.

Collaborators: links.py (attached counts), events.py, rules.py (labels), projects/media_owners.py
(projects using a file, the SEO share image), store.py (the file itself is destroyed later by
handlers.py); routes.py (HTTP).
Implements: ARCHITECTURE §9 (media.updated / media.removed), §11 (audit), §12; the honest
labels (AGENTS.md "Honest content").

Rules:
  - Delete only when nothing uses the file: no link (409 "Remove it from … first") and no
    project's SEO share image. The row goes at once; `media.removed` makes the outbox handler
    destroy the file at the store, with the normal retries.
  - A progress photo always has a month; only actual and progress photos carry one; documents
    have no label (also CHECK constraints in 0003_media). The month is stored as its first day.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Select, String, cast, exists, func, or_, select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.media import events
from empire_api.media.links import links_count
from empire_api.media.models import Media, MediaLink
from empire_api.media.rules import LABEL_FIRST, Owner, check_label, needs_label, normalise_month
from empire_api.media.schemas import MediaUpdate, label_problem
from empire_api.pagination import PageParams
from empire_api.projects.common import Actor, commit, conflict, like_pattern, record, snapshot
from empire_api.projects.media_owners import (
    owner_project_id,
    projects_by_ids,
    projects_using_share_image,
    share_image_ids,
)

NO_MEDIA: Final = "No media with this id."
_AUDIT_SKIP: Final = ("created_by",)


@dataclass(frozen=True)
class MediaFilters:
    kind: str | None = None
    q: str | None = None
    attached_to: Owner | None = None
    unattached: bool = False


def _filtered(filters: MediaFilters) -> Select[Media]:
    stmt = select(Media)
    if filters.kind:
        stmt = stmt.where(Media.kind == filters.kind)
    if filters.q and filters.q.strip():
        pattern = like_pattern(filters.q)
        stmt = stmt.where(
            or_(
                func.lower(Media.title).like(pattern, escape="\\"),
                func.lower(func.coalesce(Media.alt_text, "")).like(pattern, escape="\\"),
            )
        )
    if filters.attached_to is not None:
        owned = select(MediaLink.media_id).where(filters.attached_to.matches())
        stmt = stmt.where(Media.id.in_(owned))
    if filters.unattached:
        # A project's SEO share image is in use too, even without a link (delete would 409).
        stmt = stmt.where(
            ~exists().where(MediaLink.media_id == Media.id),
            cast(Media.id, String).not_in(share_image_ids()),
        )
    return stmt


def list_media(db: Session, paging: PageParams, filters: MediaFilters) -> tuple[list[Media], int]:
    """The library, newest first, with the CMS filters (kind, search, owner, unattached)."""
    stmt = _filtered(filters)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(Media.created_at.desc(), Media.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


def get_locked(db: Session, media_id: uuid.UUID) -> Media:
    media = db.get(Media, media_id, with_for_update=True, populate_existing=True)
    if media is None:
        raise ApiProblem(404, NO_MEDIA)
    return media


def update_media(db: Session, actor: Actor, media_id: uuid.UUID, body: MediaUpdate) -> Media:
    """Rename, alt text and label. Checks the label rules on the merged values."""
    media = get_locked(db, media_id)
    sent = body.model_dump(exclude_unset=True)
    if "label_month" in sent:
        sent["label_month"] = normalise_month(sent["label_month"])
    label = sent.get("label", media.label)
    month = sent.get("label_month", media.label_month)
    if "label" in sent and sent["label"] not in ("actual_photo", "progress_photo"):
        # Moving to a label without a month (or none) drops the month, unless one was sent.
        month = sent.get("label_month")
    check_label(media.kind, label)
    if label is None and media.label is not None and _shown_where_label_needed(db, media):
        raise conflict(LABEL_FIRST)
    problem = label_problem(label, month)
    if problem:
        raise ApiProblem(422, problem, errors=[{"field": "label_month", "message": problem}])
    before = snapshot(media, _AUDIT_SKIP)
    for key in ("title", "alt_text"):
        if key in sent:
            setattr(media, key, sent[key])
    media.label, media.label_month = label, month
    db.flush()
    after = snapshot(media, _AUDIT_SKIP)
    if after != before:
        record(
            db,
            actor,
            action="media.updated",
            entity_type="media",
            entity_id=media.id,
            before=before,
            after=after,
        )
        events.media_event(db, actor, "media.updated", media, "details")
        _notify_live_projects(db, actor, media)
    commit(db)
    return media


def _shown_where_label_needed(db: Session, media: Media) -> bool:
    """COMPLIANCE: whether the file is visible in a photo list that needs a label."""
    links = db.scalars(
        select(MediaLink).where(MediaLink.media_id == media.id, MediaLink.is_visible.is_(True))
    )
    unlabelled = Media(kind=media.kind, label=None, is_sample=media.is_sample)
    return any(needs_label(unlabelled, link.role) for link in links)


def _notify_live_projects(db: Session, actor: Actor, media: Media) -> None:
    """A renamed or relabelled file changes the pages of every published project using it."""
    links = db.scalars(select(MediaLink).where(MediaLink.media_id == media.id)).all()
    seen: dict[uuid.UUID, tuple[Owner, str]] = {}
    for link in links:
        owner = Owner.of(link)
        project_id = owner_project_id(db, owner.type, owner.id)
        if project_id is not None:
            seen.setdefault(project_id, (owner, link.role))
    for project in projects_by_ids(db, set(seen)):
        owner, role = seen[project.id]
        events.owner_changed(db, actor, project, owner, role, "details")


def delete_media(db: Session, actor: Actor, media_id: uuid.UUID) -> None:
    """Delete an unused file from the library; the store copy goes through the outbox."""
    media = get_locked(db, media_id)
    used = links_count(db, media.id)
    if used:
        places = "1 place" if used == 1 else f"{used} places"
        raise conflict(f"This file is used in {places}. Remove it from there first.")
    if projects_using_share_image(db, media.id):
        raise conflict("This image is a project's share image (SEO). Choose another one first.")
    record(
        db,
        actor,
        action="media.deleted",
        entity_type="media",
        entity_id=media.id,
        before=snapshot(media, _AUDIT_SKIP),
    )
    events.removed(db, actor, media)
    db.delete(media)
    commit(db)
