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

from dataclasses import dataclass
from typing import Final

from sqlalchemy import func, select
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


def rera_qr_present(db: Session, project: Project) -> bool:
    """Whether the project shows its RERA QR code: a *visible* `rera_qr` image link exists.

    COMPLIANCE: hidden doesn't count, because the website wouldn't show it (D-002).
    """
    return media_queries.rera_qr_present(db, project.id)


def publish_blockers(db: Session, project: Project) -> list[Blocker]:
    """Every reason the project can't be published now, in checklist order (empty = ready)."""
    blockers: list[Blocker] = []
    if not (project.rera_number or "").strip():
        blockers.append(Blocker("rera_number", RERA_NUMBER_MISSING))
    if not rera_qr_present(db, project):
        blockers.append(Blocker("rera.qr", RERA_QR_MISSING))
    if project.is_sample and get_settings().app_env == "production":
        blockers.append(Blocker("is_sample", SAMPLE_ON_LIVE_SITE))
    configurations = db.scalar(
        select(func.count())
        .select_from(Configuration)
        .where(Configuration.project_id == project.id)
    )
    if not configurations:
        blockers.append(Blocker("configurations", NO_CONFIGURATION))
    return blockers
