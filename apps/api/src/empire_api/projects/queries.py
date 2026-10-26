"""Read-only service functions other modules call about projects: the leads module (public
project by slug, names for lead rows, configuration checks) and the dashboard (counts, drafts
blocked from publishing, sample data still present).

Collaborators: leads/intake.py, leads/present.py, leads/service.py, leads/report.py,
dashboard/service.py. Implements: ARCHITECTURE §2 (modules call service functions, never another
module's tables), §7 (what the public site may show), D-015 (no sample data on the live site).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.projects.blockers import Blocker, publish_blockers
from empire_api.projects.models import Configuration, Project


@dataclass(frozen=True)
class ProjectRef:
    id: uuid.UUID
    slug: str
    name: str


def public_project(db: Session, slug: str) -> ProjectRef | None:
    """A project a visitor can see on the website (ARCHITECTURE §7): published, not off-market,
    and in production never sample data. Anything else is "not found" for public intake."""
    stmt = select(Project.id, Project.slug, Project.name).where(
        Project.slug == slug,
        Project.publish_state == "published",
        Project.sales_status != "off_market",
    )
    if get_settings().app_env == "production":
        stmt = stmt.where(Project.is_sample.is_(False))
    row = db.execute(stmt).first()
    return ProjectRef(*row) if row else None


def project_ref(db: Session, project_id: uuid.UUID) -> ProjectRef | None:
    """Any project by id (staff choose archived projects too)."""
    row = db.execute(
        select(Project.id, Project.slug, Project.name).where(Project.id == project_id)
    ).first()
    return ProjectRef(*row) if row else None


def project_refs(
    db: Session, project_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, ProjectRef]:
    ids = {project_id for project_id in project_ids if project_id is not None}
    if not ids:
        return {}
    rows = db.execute(select(Project.id, Project.slug, Project.name).where(Project.id.in_(ids)))
    return {row[0]: ProjectRef(*row) for row in rows}


def configuration_names(
    db: Session, configuration_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, str]:
    ids = {config_id for config_id in configuration_ids if config_id is not None}
    if not ids:
        return {}
    rows = db.execute(select(Configuration.id, Configuration.name).where(Configuration.id.in_(ids)))
    return dict(rows.all())


def configuration_in_project(
    db: Session, configuration_id: uuid.UUID, project_id: uuid.UUID
) -> bool:
    found = db.scalar(
        select(Configuration.id).where(
            Configuration.id == configuration_id, Configuration.project_id == project_id
        )
    )
    return found is not None


# --- Dashboard ---------------------------------------------------------------------------------


@dataclass(frozen=True)
class BlockedProject:
    ref: ProjectRef
    blockers: list[Blocker]


def publish_state_counts(db: Session) -> dict[str, int]:
    """publish_state → number of projects (draft, published, archived)."""
    rows = db.execute(select(Project.publish_state, func.count()).group_by(Project.publish_state))
    counts = {"draft": 0, "published": 0, "archived": 0}
    counts.update({state: int(count) for state, count in rows})
    return counts


def blocked_drafts(db: Session) -> list[BlockedProject]:
    """Drafts that can't be published yet, with every reason, most recently edited first.

    PERF: one blocker check per draft (a few queries each); a developer has a handful of drafts.
    """
    drafts = db.scalars(
        select(Project)
        .where(Project.publish_state == "draft")
        .order_by(Project.updated_at.desc(), Project.id)
    ).all()
    found: list[BlockedProject] = []
    for project in drafts:
        blockers = publish_blockers(db, project)
        if blockers:
            found.append(
                BlockedProject(ProjectRef(project.id, project.slug, project.name), blockers)
            )
    return found


def sample_project_count(db: Session) -> int:
    """Projects still marked as sample data (D-015: the dashboard warns while any exist)."""
    return int(
        db.scalar(select(func.count()).select_from(Project).where(Project.is_sample.is_(True))) or 0
    )
