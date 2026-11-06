"""Read-only service functions the projects module calls to fill its media fields: a project's
gallery, videos, documents, brochure, cover and RERA QR; configurations' floor plans; updates'
progress photos; and the checks behind the publish blocker and the SEO share image. Also the
public brochure address (leads/intake.py) and the dashboard's "photos hidden until labelled".

Collaborators: projects/present.py, routes.py, child_kinds.py, blockers.py, project_input.py,
leads/intake.py, dashboard/service.py.
Implements: ARCHITECTURE §2 (other modules call these, never the media tables), the cover rule
(pinned, else the first visible photo in order) and D-002 (RERA QR before publishing).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Collection, Iterable
from dataclasses import dataclass, field

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from empire_api.media import present, schemas
from empire_api.media.models import Media, MediaLink
from empire_api.projects.media_owners import update_projects


@dataclass
class ProjectMedia:
    """A project's own media, as ProjectAdmin shows it (hidden items included, in order)."""

    gallery: list[schemas.LinkedMedia] = field(default_factory=list)
    videos: list[schemas.LinkedMedia] = field(default_factory=list)
    documents: list[schemas.LinkedMedia] = field(default_factory=list)
    brochure: schemas.LinkedMedia | None = None
    cover: schemas.Media | None = None
    rera_qr: schemas.Media | None = None


def _ordered(stmt: Select[MediaLink]) -> Select[MediaLink]:
    return stmt.order_by(MediaLink.sort_order, MediaLink.id)


def _cover_link(links: Iterable[MediaLink]) -> MediaLink | None:
    """INVARIANT: the pinned photo, else the first visible one in order; hidden never counts."""
    visible = [link for link in links if link.is_visible]
    pinned = [link for link in visible if link.is_cover]
    chosen = pinned or visible
    return chosen[0] if chosen else None


def project_media(db: Session, project_id: uuid.UUID) -> ProjectMedia:
    links = list(db.scalars(_ordered(select(MediaLink).where(MediaLink.project_id == project_id))))
    counts = present.attached_counts(db, (link.media_id for link in links))
    by_role: dict[str, list[MediaLink]] = defaultdict(list)
    for link in links:
        by_role[link.role].append(link)
    out = ProjectMedia(
        gallery=present.linked_list(by_role["gallery"], counts),
        videos=present.linked_list(by_role["video"], counts),
        documents=present.linked_list(by_role["document"], counts),
    )
    if by_role["brochure"]:
        out.brochure = present.linked_list(by_role["brochure"][:1], counts)[0]
    cover = _cover_link(by_role["gallery"])
    if cover is not None:
        out.cover = present.media_out(cover.media, counts.get(cover.media_id, 0))
    qr = [link for link in by_role["rera_qr"] if link.is_visible]
    if qr:
        out.rera_qr = present.media_out(qr[0].media, counts.get(qr[0].media_id, 0))
    return out


def covers_and_qrs(
    db: Session, project_ids: Iterable[uuid.UUID]
) -> tuple[dict[uuid.UUID, schemas.Media], dict[uuid.UUID, schemas.Media]]:
    """For list rows: project id → cover, and project id → visible RERA QR (two dicts)."""
    ids = set(project_ids)
    if not ids:
        return {}, {}
    links = list(
        db.scalars(
            _ordered(
                select(MediaLink).where(
                    MediaLink.project_id.in_(ids), MediaLink.role.in_(("gallery", "rera_qr"))
                )
            )
        )
    )
    counts = present.attached_counts(db, (link.media_id for link in links))
    galleries: dict[uuid.UUID, list[MediaLink]] = defaultdict(list)
    qrs: dict[uuid.UUID, schemas.Media] = {}
    for link in links:
        assert link.project_id is not None  # noqa: S101 — filtered above
        if link.role == "gallery":
            galleries[link.project_id].append(link)
        elif link.is_visible:
            qrs[link.project_id] = present.media_out(link.media, counts.get(link.media_id, 0))
    covers: dict[uuid.UUID, schemas.Media] = {}
    for project_id, gallery in galleries.items():
        cover = _cover_link(gallery)
        if cover is not None:
            covers[project_id] = present.media_out(cover.media, counts.get(cover.media_id, 0))
    return covers, qrs


def _children_links(
    db: Session, column: str, owner_ids: Iterable[uuid.UUID], role: str
) -> dict[uuid.UUID, list[schemas.LinkedMedia]]:
    ids = set(owner_ids)
    if not ids:
        return {}
    owner = getattr(MediaLink, column)
    links = list(
        db.scalars(_ordered(select(MediaLink).where(owner.in_(ids), MediaLink.role == role)))
    )
    counts = present.attached_counts(db, (link.media_id for link in links))
    grouped: dict[uuid.UUID, list[MediaLink]] = defaultdict(list)
    for link in links:
        grouped[getattr(link, column)].append(link)
    return {key: present.linked_list(rows, counts) for key, rows in grouped.items()}


def floor_plans(
    db: Session, configuration_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[schemas.LinkedMedia]]:
    """configuration id → its floor plan (a list of at most one: floor_plan is single-valued)."""
    return _children_links(db, "configuration_id", configuration_ids, "floor_plan")


def progress_photos(
    db: Session, update_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[schemas.LinkedMedia]]:
    """construction update id → its photos, in order (hidden ones included for the CMS)."""
    return _children_links(db, "construction_update_id", update_ids, "gallery")


def rera_qr_projects(db: Session, project_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
    """COMPLIANCE (D-002): of these projects, the ones with a *visible* RERA QR image attached.

    One query for any number of projects (a single publish, or the dashboard's blocked drafts).
    """
    if not project_ids:
        return set()
    return set(
        db.scalars(
            select(MediaLink.project_id)
            .where(
                MediaLink.project_id.in_(project_ids),
                MediaLink.role == "rera_qr",
                MediaLink.is_visible.is_(True),
            )
            .distinct()
        )
    )


def is_library_image(db: Session, media_id: uuid.UUID) -> bool:
    """Whether this is an image in the library, read FOR SHARE.

    WHY the share lock: a project saving it as its share image and a library delete must not
    pass each other. The lock makes the delete wait for this transaction and then see the
    reference (409), or makes this check see the deleted row (422).
    """
    found = db.scalar(
        select(Media.id)
        .where(Media.id == media_id, Media.kind == "image")
        .with_for_update(read=True)
    )
    return found is not None


def library_item(db: Session, media_id: uuid.UUID | None) -> schemas.Media | None:
    """One library item as `Media` (e.g. the project's SEO share image), or None."""
    if media_id is None:
        return None
    row = db.get(Media, media_id)
    if row is None:
        return None
    return present.media_out(row, present.attached_counts(db, [row.id]).get(row.id, 0))


def visible_brochure_url(db: Session, project_id: uuid.UUID) -> str | None:
    """The address of the project's brochure PDF when it is shown on the website, else None.

    Used by public brochure requests (leads/intake.py). The address is public: gating collects a
    lead, it doesn't protect the file.
    """
    link = db.scalar(
        select(MediaLink).where(
            MediaLink.project_id == project_id,
            MediaLink.role == "brochure",
            MediaLink.is_visible.is_(True),
        )
    )
    if link is None:
        return None
    return present.media_out(link.media, 0).url


def hidden_unlabelled_photos(db: Session) -> dict[uuid.UUID, int]:
    """project id → photos (its own gallery and its progress photos) that stay hidden until
    they get an honest label (rules.LABEL_FIRST). Sample tiles are left out: they are never
    public, so they don't need a label (D-033)."""
    rows = db.execute(
        select(MediaLink.project_id, MediaLink.construction_update_id, func.count())
        .join(Media, Media.id == MediaLink.media_id)
        .where(
            MediaLink.role == "gallery",
            MediaLink.is_visible.is_(False),
            Media.label.is_(None),
            Media.is_sample.is_(False),
        )
        .group_by(MediaLink.project_id, MediaLink.construction_update_id)
    )
    by_project: dict[uuid.UUID, int] = defaultdict(int)
    by_update: dict[uuid.UUID, int] = {}
    for project_id, update_id, count in rows:
        if project_id is not None:
            by_project[project_id] += int(count)
        elif update_id is not None:
            by_update[update_id] = int(count)
    for update_id, project_id in update_projects(db, by_update).items():
        by_project[project_id] += by_update[update_id]
    return dict(by_project)
