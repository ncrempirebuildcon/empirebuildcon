"""Duplicate a project: a new draft with copies of every child (Phase 4 spec, "Duplicate").

Collaborators: service.load_project (the source with its children), common.py (audit,
commit, slugs); routes.py (`POST /admin/projects/{id}/duplicate`).

Rules:
  - Slug `<slug>-copy`, then `<slug>-copy-2`, `-copy-3`, … (cut to 120 characters).
  - Name gets " (copy)"; state is draft; featured is reset so the copy can't reach the home
    page; `is_sample` is kept (D-015: a copy of sample data is still sample data).
  - COMPLIANCE: the RERA registration is NOT copied: number, regulator URL, designated
    account, tower/phase registrations and the SEO canonical path are cleared (D-002).
  - Towers, configurations, specifications, location advantages, construction updates,
    payment plans and the amenity list are copied; configurations and updates point at the
    copied towers.
  - COMPLIANCE: media links are NOT copied (photos, videos, documents, brochure, floor plans,
    progress photos, and above all the RERA QR, which belongs to the source's registration).
    The SEO share image (`seo.og_image_id`) is cleared too. The copy needs its own QR and
    photos, so it shows "RERA QR code missing" until staff upload them (D-002).
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.ids import new_id
from empire_api.platform import audit
from empire_api.projects.common import Actor, commit, flush, record, snapshot, with_suffix
from empire_api.projects.models import (
    Configuration,
    ConstructionUpdate,
    LocationAdvantage,
    PaymentPlan,
    Project,
    ProjectAmenity,
    Specification,
    Tower,
)
from empire_api.projects.project_input import SLUG_TAKEN

_NOT_COPIED: Final = frozenset({"id", "project_id", "created_at", "updated_at"})
NAME_MAX: Final = 120
SLUG_CONFLICTS: Final = {"uq_project_slug": ("slug", SLUG_TAKEN)}
# COMPLIANCE (D-002): a copy must never carry another project's RERA registration: not the
# number, the regulator page, the designated bank account, nor the canonical path of the
# source's page. The authority (UP-RERA) is kept; the copy shows "RERA registration number
# missing" until staff enter its own registration.
_NO_REGISTRATION: Final = dict.fromkeys(
    ("rera_number", "rera_url", "rera_bank_name", "rera_account_name", "rera_account_number")
)


def _copy(row: Any, **overrides: Any) -> dict[str, Any]:
    values = {
        column.key: getattr(row, column.key)
        for column in row.__table__.columns
        if column.key not in _NOT_COPIED
    }
    values.update(overrides)
    return values


def duplicate_project(db: Session, source: Project, actor: Actor) -> uuid.UUID:
    """Copy `source` (loaded with its children) as a new draft. Returns the copy's id."""
    copy_id = new_id()
    name = f"{source.name} (copy)"
    db.add(
        Project(
            **_copy(
                source,
                id=copy_id,
                slug=free_copy_slug(db, source.slug),
                name=name if len(name) <= NAME_MAX else source.name,
                publish_state="draft",
                published_at=None,
                is_featured=False,
                featured_order=None,
                created_by=actor.user_id,
                updated_by=actor.user_id,
                **_NO_REGISTRATION,
                seo={
                    k: v
                    for k, v in source.seo.items()
                    if k not in ("canonical_path", "og_image_id")
                },
            )
        )
    )
    flush(db, SLUG_CONFLICTS)
    _copy_children(db, source, copy_id)
    copied = db.get(Project, copy_id)
    assert copied is not None  # noqa: S101 — inserted just above
    changes = audit.diff({}, snapshot(copied, ("updated_by",)))
    changes["duplicated_from"] = [None, str(source.id)]
    record(
        db,
        actor,
        action="project.duplicated",
        entity_type="project",
        entity_id=copy_id,
        changes=changes,
    )
    commit(db, SLUG_CONFLICTS)
    return copy_id


def _copy_children(db: Session, source: Project, copy_id: uuid.UUID) -> None:
    tower_ids = {tower.id: new_id() for tower in source.towers}
    db.add_all(
        # COMPLIANCE: a phase's own registration belongs to the source too (module header).
        Tower(**_copy(t, id=tower_ids[t.id], project_id=copy_id, rera_number=None))
        for t in source.towers
    )
    db.flush()  # towers first: configurations and updates point at them

    def tower_of(old: uuid.UUID | None) -> uuid.UUID | None:
        return tower_ids.get(old) if old else None

    db.add_all(
        Configuration(**_copy(c, project_id=copy_id, tower_id=tower_of(c.tower_id)))
        for c in source.configurations
    )
    db.add_all(
        ConstructionUpdate(**_copy(u, project_id=copy_id, tower_id=tower_of(u.tower_id)))
        for u in source.construction_updates
    )
    db.add_all(Specification(**_copy(s, project_id=copy_id)) for s in source.specifications)
    db.add_all(
        LocationAdvantage(**_copy(a, project_id=copy_id)) for a in source.location_advantages
    )
    db.add_all(PaymentPlan(**_copy(p, project_id=copy_id)) for p in source.payment_plans)
    db.add_all(
        ProjectAmenity(project_id=copy_id, amenity_id=link.amenity_id, sort_order=link.sort_order)
        for link in source.amenity_links
    )
    db.flush()


def free_copy_slug(db: Session, slug: str) -> str:
    """`<slug>-copy`, or the first free `<slug>-copy-N` (N = 2, 3, …).

    WHY one query per candidate and not one LIKE: near the 120-character limit each suffix cuts
    the base differently, so the candidates don't share a prefix. Copies of copies are rare.
    """
    candidate, number = with_suffix(slug, "-copy"), 1
    while db.scalar(select(Project.id).where(Project.slug == candidate)) is not None:
        number += 1
        candidate = with_suffix(slug, f"-copy-{number}")
    return candidate
