"""Publish blockers: the one place that decides whether a project may go on the website.

Collaborators: service.publish_project (409 when the list isn't empty), present.project_admin
(`publish_blockers` on ProjectAdmin, so the CMS can show the checklist before anyone clicks),
media/queries.py (the RERA QR link).
Implements: D-002 (RERA number and QR before publishing), D-015 (no sample data on the live
site), ARCHITECTURE §7.

COMPLIANCE: UP-RERA requires the registration number and the project QR code on every project
page and advert. Don't remove or weaken a blocker without the owner's approval.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.media import queries as media_queries
from empire_api.projects.models import Configuration, Project

RERA_NUMBER_MISSING: Final = "RERA registration number missing"
RERA_QR_MISSING: Final = "RERA QR code missing"
SAMPLE_ON_LIVE_SITE: Final = "Sample data can't be published on the live site"
NO_CONFIGURATION: Final = "Add at least one configuration"


@dataclass(frozen=True)
class Blocker:
    """`field` is where the CMS shows the message; `message` is the checklist line."""

    field: str
    message: str


def projects_with_rera_qr(db: Session, project_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
    """Of these projects, the ones that show their RERA QR code: a *visible* `rera_qr` image link.

    COMPLIANCE: hidden doesn't count, because the website wouldn't show it (D-002).
    """
    return media_queries.rera_qr_projects(db, project_ids)


def publish_blockers(db: Session, project: Project) -> list[Blocker]:
    """Every reason the project can't be published now, in checklist order (empty = ready)."""
    return publish_blockers_for(db, [project])[project.id]


def publish_blockers_for(
    db: Session, projects: Sequence[Project]
) -> dict[uuid.UUID, list[Blocker]]:
    """`publish_blockers` for many projects at once: project id → its blockers.

    PERF: two queries for the whole list, not two per project (the dashboard checks every
    draft; with a project per query it took seconds once drafts ran into the hundreds, L1).
    INVARIANT: the one rule set. `publish_blockers` calls this, so a single project and the
    dashboard can't disagree.
    """
    ids = [project.id for project in projects]
    with_qr = projects_with_rera_qr(db, ids)
    with_configurations: set[uuid.UUID] = (
        set(
            db.scalars(
                select(Configuration.project_id).where(Configuration.project_id.in_(ids)).distinct()
            )
        )
        if ids
        else set()
    )
    production = get_settings().app_env == "production"
    found: dict[uuid.UUID, list[Blocker]] = {}
    for project in projects:
        blockers: list[Blocker] = []
        if not (project.rera_number or "").strip():
            blockers.append(Blocker("rera_number", RERA_NUMBER_MISSING))
        if project.id not in with_qr:
            blockers.append(Blocker("rera.qr", RERA_QR_MISSING))
        if project.is_sample and production:
            blockers.append(Blocker("is_sample", SAMPLE_ON_LIVE_SITE))
        if project.id not in with_configurations:
            blockers.append(Blocker("configurations", NO_CONFIGURATION))
        found[project.id] = blockers
    return found
