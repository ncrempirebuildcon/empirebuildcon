"""Service functions the media module calls about the owners of its links: which project an
owner belongs to (locked), and which library items projects use as their SEO share image.

Collaborators: media/links.py, media/library.py, media/seed.py (callers); common.lock_project.
Implements: ARCHITECTURE §2 (modules call each other's service functions, never their tables),
§6 (media links: project, configuration and construction update owners).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Final

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.projects.common import lock_project
from empire_api.projects.models import Configuration, ConstructionUpdate, Project

_MISSING: Final = {
    "project": "No project with this id.",
    "configuration": "No configuration with this id.",
    "construction_update": "No construction update with this id.",
}
SAMPLE_SLUGS: Final = ("sample-project-a", "sample-project-b")


def owner_project_id(db: Session, owner_type: str, owner_id: uuid.UUID) -> uuid.UUID | None:
    """The id of the project that owns this owner, or None when the owner doesn't exist."""
    if owner_type == "project":
        return db.scalar(select(Project.id).where(Project.id == owner_id))
    if owner_type == "configuration":
        return db.scalar(select(Configuration.project_id).where(Configuration.id == owner_id))
    if owner_type == "construction_update":
        return db.scalar(
            select(ConstructionUpdate.project_id).where(ConstructionUpdate.id == owner_id)
        )
    return None


def lock_owner_project(db: Session, owner_type: str, owner_id: uuid.UUID) -> Project:
    """The owner's project row, locked until commit, or 404 naming the missing owner.

    WHY lock the project: every write to a project's tree takes this lock (common.lock_project),
    so a media change can't race a publish that checks the RERA QR, or a child's delete.
    """
    project_id = owner_project_id(db, owner_type, owner_id)
    if project_id is None:
        raise ApiProblem(404, _MISSING.get(owner_type, "No owner with this id."))
    project = lock_project(db, project_id)
    if owner_project_id(db, owner_type, owner_id) != project.id:
        # The owner was deleted (or moved) between the two reads.
        raise ApiProblem(404, _MISSING[owner_type])
    return project


def projects_using_share_image(db: Session, media_id: uuid.UUID) -> int:
    """How many projects name this library item as their SEO share image (`seo.og_image_id`)."""
    count = db.scalar(
        select(func.count())
        .select_from(Project)
        .where(Project.seo["og_image_id"].astext == str(media_id))
    )
    return int(count or 0)


def share_image_ids() -> Select[str]:
    """The media ids (as text) projects use as their SEO share image, for library filters."""
    share = Project.seo["og_image_id"].astext
    return select(share).where(share.is_not(None))


def share_image_counts(db: Session, media_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    """media id → how many projects use it as their SEO share image."""
    if not media_ids:
        return {}
    share = Project.seo["og_image_id"].astext
    rows = db.execute(
        select(share, func.count()).where(share.in_([str(i) for i in media_ids])).group_by(share)
    ).all()
    return {uuid.UUID(media_id): int(count) for media_id, count in rows}


def projects_by_ids(db: Session, project_ids: set[uuid.UUID]) -> list[Project]:
    """Projects by id (for event payloads: id, slug and publish state)."""
    if not project_ids:
        return []
    return list(db.scalars(select(Project).where(Project.id.in_(project_ids))))


def sample_project_ids(db: Session) -> list[uuid.UUID]:
    """Ids of the seeded sample projects that exist (D-015)."""
    rows = db.scalars(
        select(Project.id).where(Project.slug.in_(SAMPLE_SLUGS), Project.is_sample.is_(True))
    )
    return list(rows)


def update_projects(db: Session, update_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, uuid.UUID]:
    """construction update id → its project's id (for media counts per project)."""
    ids = set(update_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(ConstructionUpdate.id, ConstructionUpdate.project_id).where(
            ConstructionUpdate.id.in_(ids)
        )
    )
    return dict(rows.all())
