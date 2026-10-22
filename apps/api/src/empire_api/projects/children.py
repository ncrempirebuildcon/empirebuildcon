"""Business rules for a project's ordered children: towers, configurations, specifications,
location advantages, construction updates and payment plans (list, create, update, delete,
reorder), and the project's amenity list.

Collaborators: child_kinds.py (what each kind stores and returns), common.py (locks, audit,
events), routes_children.py and routes.py (HTTP).
Implements: ARCHITECTURE §9 (configuration.changed, construction_update.published,
project.updated), §11 (audit on every change, reorder included).

The five operations are shared, so every collection behaves the same way: the parent project
row is locked, the change is audited with a before/after diff, the project counts as edited,
and events go out only while the project is published.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.projects.child_kinds import KINDS, ChildKind
from empire_api.projects.common import (
    Actor,
    FieldError,
    commit,
    conflict,
    emit,
    flush,
    invalid,
    lock_project,
    record,
    snapshot,
    touch,
)
from empire_api.projects.models import (
    Amenity,
    Configuration,
    ConstructionUpdate,
    Project,
    ProjectAmenity,
)

__all__ = ["KINDS", "ChildKind"]

LAST_CONFIGURATION: Final = (
    "A published project needs at least one configuration. Add another one first, or "
    "unpublish the project."
)


# --- Shared operations -----------------------------------------------------------------------


def _project_must_exist(db: Session, project_id: uuid.UUID) -> None:
    if db.get(Project, project_id) is None:
        raise ApiProblem(404, "No project with this id.")


def _ordered(db: Session, kind: ChildKind, project_id: uuid.UUID) -> list[Any]:
    model = kind.model
    return list(
        db.scalars(
            select(model).where(model.project_id == project_id).order_by(model.sort_order, model.id)
        ).all()
    )


def _get(db: Session, kind: ChildKind, project_id: uuid.UUID, item_id: uuid.UUID) -> Any:
    row = db.get(kind.model, item_id)
    if row is None or row.project_id != project_id:
        raise ApiProblem(404, f"No {kind.label} with this id in this project.")
    return row


def present_one(db: Session, kind: ChildKind, row: Any) -> BaseModel:
    return kind.present(db, row.project_id, [row])[0]


def list_children(db: Session, kind: ChildKind, project_id: uuid.UUID) -> list[BaseModel]:
    _project_must_exist(db, project_id)
    return kind.present(db, project_id, _ordered(db, kind, project_id))


def create_child(
    db: Session, kind: ChildKind, project_id: uuid.UUID, body: BaseModel, actor: Actor
) -> Any:
    """Add an item; without `sort_order` it goes to the end of the list."""
    project = lock_project(db, project_id)
    values = kind.columns(db, project, body.model_dump(exclude_unset=True), None)
    if "sort_order" not in values:
        values["sort_order"] = len(_ordered(db, kind, project.id))
    row = kind.model(project_id=project.id, **values)
    db.add(row)
    flush(db, kind.conflicts)
    touch(project, actor)
    record(
        db,
        actor,
        action=f"{kind.key}.created",
        entity_type=kind.key,
        entity_id=row.id,
        before={},
        after=snapshot(row),
    )
    _emit(db, actor, project, kind, "created", row=row, was_published_update=False)
    commit(db, kind.conflicts)
    return row


def update_child(
    db: Session,
    kind: ChildKind,
    project_id: uuid.UUID,
    item_id: uuid.UUID,
    body: BaseModel,
    actor: Actor,
) -> Any:
    """Change the fields that were sent; the others keep their stored values."""
    project = lock_project(db, project_id)
    row = _get(db, kind, project.id, item_id)
    before = snapshot(row)
    values = kind.columns(db, project, body.model_dump(exclude_unset=True), row)
    for key, value in values.items():
        setattr(row, key, value)
    flush(db, kind.conflicts)
    after = snapshot(row)
    if after != before:
        touch(project, actor)
        record(
            db,
            actor,
            action=f"{kind.key}.updated",
            entity_type=kind.key,
            entity_id=row.id,
            before=before,
            after=after,
        )
        was_live = before.get("publish_state") == "published"
        _emit(db, actor, project, kind, "updated", row=row, was_published_update=was_live)
    commit(db, kind.conflicts)
    return row


def delete_child(
    db: Session, kind: ChildKind, project_id: uuid.UUID, item_id: uuid.UUID, actor: Actor
) -> None:
    project = lock_project(db, project_id)
    row = _get(db, kind, project.id, item_id)
    # COMPLIANCE: the publish rule "at least one configuration" keeps holding while live.
    last_live_configuration = (
        kind.model is Configuration
        and project.publish_state == "published"
        and len(_ordered(db, kind, project.id)) <= 1
    )
    if last_live_configuration:
        raise conflict(LAST_CONFIGURATION)
    record(
        db,
        actor,
        action=f"{kind.key}.deleted",
        entity_type=kind.key,
        entity_id=row.id,
        before=snapshot(row),
    )
    db.delete(row)
    touch(project, actor)
    _emit(db, actor, project, kind, "deleted", row=row, was_published_update=False)
    commit(db)


def reorder_children(
    db: Session, kind: ChildKind, project_id: uuid.UUID, ids: list[uuid.UUID], actor: Actor
) -> None:
    """Set the full order. `ids` must list every item of the collection exactly once."""
    project = lock_project(db, project_id)
    rows = _ordered(db, kind, project.id)
    by_id = {row.id: row for row in rows}
    if len(ids) != len(rows) or set(ids) != set(by_id):
        raise invalid([FieldError("ids", f"Send every {kind.label} of this project exactly once.")])
    old_order = [str(row.id) for row in rows]
    for index, item_id in enumerate(ids):
        by_id[item_id].sort_order = index
    touch(project, actor)
    record(
        db,
        actor,
        action=f"{kind.key}.reordered",
        entity_type="project",
        entity_id=project.id,
        changes={f"{kind.plural}_order": [old_order, [str(i) for i in ids]]},
    )
    _emit(db, actor, project, kind, "reordered", row=None, was_published_update=False)
    commit(db)


def _emit(
    db: Session,
    actor: Actor,
    project: Project,
    kind: ChildKind,
    change: str,
    *,
    row: Any | None,
    was_published_update: bool,
) -> None:
    """Events for a child change, only while the project is on the website (ARCHITECTURE §9).

    - configurations → `configuration.changed`;
    - a construction update going live → `construction_update.published`;
    - anything else → `project.updated` naming the collection.
    """
    if project.publish_state != "published":
        return
    item = {"aggregate_type": kind.key, "aggregate_id": row.id} if row is not None else {}
    if kind.model is Configuration:
        emit(db, actor, project, "configuration.changed", change=change, **item)
        return
    goes_live = (
        kind.model is ConstructionUpdate
        and row is not None
        and change != "deleted"
        and row.publish_state == "published"
        and not was_published_update
    )
    if goes_live:
        emit(db, actor, project, "construction_update.published", **item)
        return
    emit(db, actor, project, "project.updated", changed=[kind.plural], change=change)


# --- Amenities -------------------------------------------------------------------------------


def set_amenities(
    db: Session, project_id: uuid.UUID, amenity_ids: list[uuid.UUID], actor: Actor
) -> list[Amenity]:
    """Replace the project's amenities with this ordered list (empty clears it)."""
    project = lock_project(db, project_id)
    found = {a.id: a for a in db.scalars(select(Amenity).where(Amenity.id.in_(amenity_ids)))}
    missing = [str(i) for i in amenity_ids if i not in found]
    if missing:
        raise invalid([FieldError("amenity_ids", "Unknown amenity: " + ", ".join(missing))])
    current = db.scalars(
        select(ProjectAmenity.amenity_id)
        .where(ProjectAmenity.project_id == project.id)
        .order_by(ProjectAmenity.sort_order)
    ).all()
    before, after = [str(i) for i in current], [str(i) for i in amenity_ids]
    if before != after:
        db.execute(delete(ProjectAmenity).where(ProjectAmenity.project_id == project.id))
        db.add_all(
            ProjectAmenity(project_id=project.id, amenity_id=amenity_id, sort_order=index)
            for index, amenity_id in enumerate(amenity_ids)
        )
        touch(project, actor)
        record(
            db,
            actor,
            action="project.amenities_set",
            entity_type="project",
            entity_id=project.id,
            changes={"amenity_ids": [before, after]},
        )
        if project.publish_state == "published":
            emit(db, actor, project, "project.updated", changed=["amenities"])
    commit(db)
    return [found[i] for i in amenity_ids]
