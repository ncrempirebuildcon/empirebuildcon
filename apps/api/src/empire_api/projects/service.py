"""Business rules for a project as a whole: list, load, create, update (including archive and
restore), delete, publish, unpublish and duplicate.

Collaborators: project_input.py (body → columns, cross-field rules), duplicate.py,
blockers.py (publish rules), common.py (audit, events, locks), children.py, routes.py.
Implements: ARCHITECTURE §6 (publishing, deletion), §7, §9 (project.* events), §11 (audit);
D-002, D-015.

Rules (the Phase 4 spec):
  - New projects are drafts. Publish needs `projects.publish` and an empty blocker list.
  - Delete only drafts that were never published and have no leads; otherwise 409 "Archive it
    instead". Leads keep their project when it is archived (leads/queries.project_has_leads).
    Nor while a page block or an offer names it (content/queries.project_uses, review L12):
    409 naming where, so nothing on a page points at a project that is gone.
  - Archive = PATCH publish_state "archived"; unpublish (or PATCH "draft") = back to draft.
    Taking a *published* project off the site either way needs `projects.publish`, and so
    does moving its sales_status to or from off_market (hidden from the site, ARCHITECTURE §7).
  - project.updated is emitted only while the project is published.
  - A slug change on a published project leaves a 308 redirect from the old address
    (seo/redirects.py, Phase 4 part 4); publishing removes a redirect from its own address.

INVARIANT: every function commits once, after its audit row and events (common.py header).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from empire_api.content import queries as content_queries
from empire_api.errors import ApiProblem
from empire_api.leads import queries as lead_queries
from empire_api.pagination import PageParams
from empire_api.platform import audit
from empire_api.projects import blockers as blocker_rules
from empire_api.projects import duplicate, project_input
from empire_api.projects.common import (
    Actor,
    commit,
    conflict,
    emit,
    flush,
    like_pattern,
    lock_project,
    record,
    slug_or_error,
    snapshot,
)
from empire_api.projects.models import Project, ProjectAmenity
from empire_api.projects.schemas import ProjectInput, ProjectUpdate
from empire_api.seo import redirects
from empire_api.seo.paths import project_path
from empire_api.timeutil import utcnow

SLUG_CONFLICTS: Final = {"uq_project_slug": ("slug", project_input.SLUG_TAKEN)}
NOT_ALLOWED_OFF_SITE: Final = (
    "Your role can't take a published project off the website. Ask an admin."
)
NOT_ALLOWED_VISIBILITY: Final = (
    "Your role can't hide a published project from the website or bring it back. Ask an admin."
)
WAS_PUBLISHED: Final = (
    "This project has been on the website, so it can't be deleted. Archive it instead."
)
NOT_A_DRAFT: Final = "Only drafts can be deleted. Restore it to draft first, or keep it archived."
HAS_LEADS: Final = "This project has leads, so it can't be deleted. Archive it instead."
SHOWN_IN_MESSAGE: Final = 5
_AUDIT_SKIP: Final = ("updated_by", "search_vector")

# Everything a project row loads for the full CMS view (ProjectAdmin).
FULL: Final = (
    selectinload(Project.city),
    selectinload(Project.locality),
    selectinload(Project.towers),
    selectinload(Project.configurations),
    selectinload(Project.specifications),
    selectinload(Project.location_advantages),
    selectinload(Project.construction_updates),
    selectinload(Project.payment_plans),
    selectinload(Project.amenity_links).joinedload(ProjectAmenity.amenity),
)


@dataclass(frozen=True)
class ProjectFilters:
    q: str | None = None
    status: str | None = None
    publish_state: str | None = None
    sales_status: str | None = None
    city_id: uuid.UUID | None = None
    # true = can't be published now (at least one publish blocker); false = ready.
    blocked: bool | None = None


def load_project(db: Session, project_id: uuid.UUID) -> Project:
    """A project with every child loaded (fresh from the database), or 404."""
    project = db.scalar(
        select(Project)
        .where(Project.id == project_id)
        .options(*FULL)
        .execution_options(populate_existing=True)
    )
    if project is None:
        raise ApiProblem(404, "No project with this id.")
    return project


def list_projects(
    db: Session, paging: PageParams, filters: ProjectFilters
) -> tuple[list[Project], int]:
    """The CMS list, most recent edit first. `q` matches name or slug, ignoring case.

    TODO(phase-5): full-text search (tsvector + pg_trgm, ARCHITECTURE §14) replaces the LIKE.
    """
    stmt = select(Project)
    if filters.q and filters.q.strip():
        pattern = like_pattern(filters.q)
        stmt = stmt.where(
            or_(
                func.lower(Project.name).like(pattern, escape="\\"),
                Project.slug.like(pattern, escape="\\"),
            )
        )
    for column, value in (
        (Project.status, filters.status),
        (Project.publish_state, filters.publish_state),
        (Project.sales_status, filters.sales_status),
        (Project.city_id, filters.city_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if filters.blocked is not None:
        stmt = stmt.where(Project.id.in_(_blocked_ids(db, stmt, blocked=filters.blocked)))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.options(
            selectinload(Project.city),
            selectinload(Project.locality),
            selectinload(Project.configurations),
        )
        .order_by(Project.updated_at.desc(), Project.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


def _blocked_ids(db: Session, stmt: Any, *, blocked: bool) -> list[uuid.UUID]:
    """Ids of the matching projects that are (or aren't) blocked from publishing.

    WHY in Python: blockers.publish_blockers is the one place that decides "ready to publish"
    (RERA number, visible RERA QR, a configuration, no sample data in production), and the
    dashboard's "drafts blocked" count uses it too, so the count and this list always agree.
    PERF: one blocker check per matching project; a developer has a few dozen at most.
    """
    rows = db.scalars(stmt).all()
    return [p.id for p in rows if bool(blocker_rules.publish_blockers(db, p)) == blocked]


# --- Create and update -----------------------------------------------------------------------


def create_project(db: Session, body: ProjectInput, actor: Actor) -> Project:
    """A new draft. The slug comes from the name unless given; a taken slug is a 409."""
    sent = body.model_dump(exclude_unset=True)
    changes = project_input.columns(db, None, sent)
    changes["slug"] = slug_or_error(sent.get("slug"), body.name)
    project_input.validate(db, changes)
    project_input.slug_must_be_free(db, changes["slug"])
    project = Project(
        **changes, publish_state="draft", created_by=actor.user_id, updated_by=actor.user_id
    )
    db.add(project)
    flush(db, SLUG_CONFLICTS)
    record(
        db,
        actor,
        action="project.created",
        entity_type="project",
        entity_id=project.id,
        before={},
        after=snapshot(project, _AUDIT_SKIP),
    )
    commit(db, SLUG_CONFLICTS)
    return project


def update_project(db: Session, project_id: uuid.UUID, body: ProjectUpdate, actor: Actor) -> None:
    """Apply a PATCH. Archive/restore ride on `publish_state`; see the module rules.

    How it works:
      1. Lock the project and turn the body into column changes (nested objects merge).
         A share image that has left the library is cleared (audited with a note).
      2. Check the state change is allowed, then validate the merged result.
      3. Apply, write one audit row with the diff, and emit the event the change implies.
         Nothing changed → nothing is written.
    """
    project = lock_project(db, project_id)  # 1
    sent = body.model_dump(exclude_unset=True)
    target = sent.pop("publish_state", None)
    before = snapshot(project, _AUDIT_SKIP)
    changes = project_input.columns(db, project, sent)
    dangling = project_input.drop_dangling_share_image(db, project, sent, changes)
    _check_transition(project.publish_state, target, actor)  # 2
    visibility_changed = _check_visibility(project, changes, actor)
    merged = {column.key: getattr(project, column.key) for column in Project.__table__.columns}
    merged.update(changes)
    if target is not None:
        merged["publish_state"] = target
    project_input.validate(db, merged)
    if changes.get("slug", project.slug) != project.slug:
        project_input.slug_must_be_free(db, changes["slug"], project.id)
    for key, value in changes.items():  # 3
        setattr(project, key, value)
    if target is not None:
        project.publish_state = target
    flush(db, SLUG_CONFLICTS)
    diff = audit.diff(before, snapshot(project, _AUDIT_SKIP))
    if not diff:
        db.rollback()
        return
    project.updated_by = actor.user_id
    if dangling:
        diff["seo.og_image_id"] = [dangling, None]
        diff["note"] = [None, "The share image had been deleted from the library; cleared."]
    record(
        db,
        actor,
        action=_update_action(before["publish_state"], project.publish_state),
        entity_type="project",
        entity_id=project.id,
        changes=diff,
    )
    _emit_after_update(db, actor, project, before, diff, visibility_changed=visibility_changed)
    commit(db, SLUG_CONFLICTS)


def _check_transition(current: str, target: str | None, actor: Actor) -> None:
    """SECURITY: archiving or un-drafting a *published* project takes it off the website, which
    is the `projects.publish` permission's job (ARCHITECTURE §11), not `projects.write`'s."""
    if target is None or target == current:
        return
    if current == "published" and not actor.can_publish:
        raise ApiProblem(403, NOT_ALLOWED_OFF_SITE)


def _check_visibility(project: Project, changes: Mapping[str, Any], actor: Actor) -> bool:
    """Whether this edit hides a live project (sales_status → off_market) or shows it again.

    SECURITY: off_market projects are hidden from the website (ARCHITECTURE §7), so on a
    published project this is the same outcome as archiving and needs `projects.publish`.
    A configuration's own off_market stays with `projects.write` (the project stays visible).
    """
    if project.publish_state != "published" or "sales_status" not in changes:
        return False
    flips = bool(changes["sales_status"] == "off_market") != (project.sales_status == "off_market")
    if flips and not actor.can_publish:
        raise ApiProblem(403, NOT_ALLOWED_VISIBILITY)
    return flips


def _update_action(was: str, now: str) -> str:
    if was == now:
        return "project.updated"
    if now == "archived":
        return "project.archived"
    return "project.unpublished" if was == "published" else "project.restored"


def _emit_after_update(
    db: Session,
    actor: Actor,
    project: Project,
    before: Mapping[str, Any],
    diff: dict[str, Any],
    *,
    visibility_changed: bool,
) -> None:
    was_published = before["publish_state"] == "published"
    if was_published and project.publish_state != "published":
        emit(db, actor, project, "project.unpublished", reason=project.publish_state)
    elif project.publish_state == "published":
        extra: dict[str, Any] = {"previous_slug": before["slug"]} if "slug" in diff else {}
        if visibility_changed:
            # Consumers drop the project from (or add it back to) lists and the sitemap.
            extra["visibility_changed"] = True
        if "slug" in diff and was_published:
            # ARCHITECTURE §16: the old address keeps working (308, chains collapsed).
            redirects.slug_changed(
                db, actor, "project", project_path(before["slug"]), project_path(project.slug)
            )
        emit(db, actor, project, "project.updated", changed=sorted(diff), **extra)


# --- Delete, publish, unpublish, duplicate ---------------------------------------------------


def delete_project(db: Session, project_id: uuid.UUID, actor: Actor) -> None:
    """Delete a draft that was never published and has no leads, with all its children.

    INVARIANT: `published_at` is never cleared (models.py), so it tells "never published".
    COMPLIANCE: a project with leads is only ever archived (ARCHITECTURE §6): its leads keep
    pointing at it, and leads are never deleted. The foreign key is RESTRICT as a backstop.
    """
    project = lock_project(db, project_id)
    if project.published_at is not None:
        raise conflict(WAS_PUBLISHED)
    if project.publish_state != "draft":
        raise conflict(NOT_A_DRAFT)
    if lead_queries.project_has_leads(db, project.id):
        raise conflict(HAS_LEADS)
    uses = content_queries.project_uses(db, project.id)
    if uses:
        raise conflict(_named_by_content(uses))
    record(
        db,
        actor,
        action="project.deleted",
        entity_type="project",
        entity_id=project.id,
        before=snapshot(project, _AUDIT_SKIP),
    )
    db.delete(project)
    commit(db)


def _named_by_content(uses: list[str]) -> str:
    """'Content still names this project: page “X” (a map block), offer “Y”. …'"""
    named = ", ".join(uses[:SHOWN_IN_MESSAGE])
    more = f" and {len(uses) - SHOWN_IN_MESSAGE} more" if len(uses) > SHOWN_IN_MESSAGE else ""
    return (
        f"Content still names this project: {named}{more}. Change or remove "
        f"{'that' if len(uses) == 1 else 'those'} first, then delete the project."
    )


def publish_project(db: Session, project_id: uuid.UUID, actor: Actor) -> None:
    """Put the project on the website, or 409 listing every blocker in `errors[]`.

    Publishing an already published project changes nothing (safe to retry).
    """
    project = lock_project(db, project_id)
    if project.publish_state == "published":
        return
    found = blocker_rules.publish_blockers(db, project)
    if found:
        raise ApiProblem(
            409,
            "This project can't be published yet: " + "; ".join(b.message for b in found) + ".",
            title="Publish blocked",
            errors=[{"field": b.field, "message": b.message} for b in found],
        )
    before = snapshot(project, _AUDIT_SKIP)
    project.publish_state = "published"
    project.published_at = utcnow()
    project.updated_by = actor.user_id
    db.flush()
    # A redirect from this project's address would hide it now that it is live (redirects.py).
    redirects.claim_path(db, actor, project_path(project.slug))
    record(
        db,
        actor,
        action="project.published",
        entity_type="project",
        entity_id=project.id,
        before=before,
        after=snapshot(project, _AUDIT_SKIP),
    )
    emit(db, actor, project, "project.published")
    commit(db)


def unpublish_project(db: Session, project_id: uuid.UUID, actor: Actor) -> None:
    """Take the project off the website (back to draft). No-op when it isn't published."""
    project = lock_project(db, project_id)
    if project.publish_state != "published":
        return
    project.publish_state = "draft"
    project.updated_by = actor.user_id
    record(
        db,
        actor,
        action="project.unpublished",
        entity_type="project",
        entity_id=project.id,
        changes={"publish_state": ["published", "draft"]},
    )
    emit(db, actor, project, "project.unpublished", reason="draft")
    commit(db)


def duplicate_project(db: Session, project_id: uuid.UUID, actor: Actor) -> uuid.UUID:
    """A draft copy with every child (rules in duplicate.py). Returns the new id."""
    return duplicate.duplicate_project(db, load_project(db, project_id), actor)
