"""The child collections of a project, described once each: which columns a request body sets
(with its validation) and how rows become responses. children.py runs the shared operations.

Kinds: towers, configurations, specifications, location advantages, construction updates and
payment plans (design contract schemas *Input → *).

Collaborators: children.py (operations), present.py (responses), common.py (price/area rules).
Implements: ARCHITECTURE §6 (area in square metres, whole rupees, min ≤ max), D-004 (a
configuration is a property), D-015 (a sample project's configurations are samples too).
"""

from __future__ import annotations

import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Final

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.projects import present
from empire_api.projects.common import (
    FieldError,
    check_area,
    check_price,
    conflict,
    invalid,
    price_columns,
    slug_or_error,
    snapshot,
    to_sqm,
)
from empire_api.projects.models import (
    Configuration,
    ConstructionUpdate,
    LocationAdvantage,
    PaymentPlan,
    Project,
    Specification,
    Tower,
)

ColumnsFn = Callable[[Session, Project, Mapping[str, Any], Any | None], dict[str, Any]]
PresentFn = Callable[[Session, uuid.UUID, Sequence[Any]], list[BaseModel]]

CONFIG_SLUG_TAKEN: Final = (
    "Another configuration of this project already uses this web address. Choose another."
)


@dataclass(frozen=True)
class ChildKind:
    """One child collection. `key` is the audit entity type; `plural` names the collection."""

    key: str
    plural: str
    label: str
    model: type[Any]
    columns: ColumnsFn
    present: PresentFn
    conflicts: Mapping[str, tuple[str, str]] = field(default_factory=dict)


def _pick(sent: Mapping[str, Any], keys: Sequence[str]) -> dict[str, Any]:
    """The plain fields that were sent. A `sort_order` of null means "leave it"."""
    values = {key: sent[key] for key in keys if key in sent}
    if values.get("sort_order", 0) is None:
        values.pop("sort_order")
    return values


def _tower_must_belong(db: Session, project: Project, tower_id: uuid.UUID | None) -> None:
    if tower_id is None:
        return
    tower = db.get(Tower, tower_id)
    if tower is None or tower.project_id != project.id:
        raise invalid([FieldError("tower_id", "Choose a tower of this project.")])


# --- Per-kind columns ------------------------------------------------------------------------


def _tower_columns(
    db: Session, project: Project, sent: Mapping[str, Any], row: Any | None
) -> dict[str, Any]:
    keys = ("name", "kind", "floors", "units_count", "status", "rera_number", "possession_date")
    return _pick(sent, (*keys, "sort_order"))


def _configuration_columns(
    db: Session, project: Project, sent: Mapping[str, Any], row: Any | None
) -> dict[str, Any]:
    keys = ("name", "tower_id", "property_type", "bathrooms", "balconies", "sales_status")
    values = _pick(sent, (*keys, "translations", "sort_order"))
    if "bhk" in sent:
        values["bhk"] = None if sent["bhk"] is None else Decimal(str(sent["bhk"]))
    if row is None:
        values["slug"] = slug_or_error(sent.get("slug"), sent["name"])
    elif sent.get("slug"):
        values["slug"] = sent["slug"]  # a slug left out (or null) keeps the current one
    if "price" in sent:
        values.update(price_columns(sent["price"]))
    area = sent.get("area") or {}
    for key in ("min_sqm", "max_sqm"):
        if key in area:
            values[f"area_{key}"] = to_sqm(area[key])
    for key in ("basis", "display_unit"):
        if key in area:
            values[f"area_{key}"] = area[key]
    _tower_must_belong(db, project, values.get("tower_id"))
    merged = {**(snapshot(row) if row is not None else {}), **values}
    errors = check_price(merged) + check_area(
        values.get("area_min_sqm", row.area_min_sqm if row else None),
        values.get("area_max_sqm", row.area_max_sqm if row else None),
        "area",
    )
    if errors:
        raise invalid(errors)
    slug = values.get("slug")
    if slug and (row is None or slug != row.slug):
        configuration_slug_must_be_free(db, project.id, slug)
    if row is None:
        values["is_sample"] = project.is_sample  # D-015: samples stay marked all the way down
    return values


def configuration_slug_must_be_free(db: Session, project_id: uuid.UUID, slug: str) -> None:
    """409 with a field error when another configuration of the project has this slug. A race
    past this check is caught by the unique index (common.flush)."""
    taken = db.scalar(
        select(Configuration.id).where(
            Configuration.project_id == project_id, Configuration.slug == slug
        )
    )
    if taken is not None:
        raise conflict(CONFIG_SLUG_TAKEN, "slug", CONFIG_SLUG_TAKEN)


def _specification_columns(
    db: Session, project: Project, sent: Mapping[str, Any], row: Any | None
) -> dict[str, Any]:
    return _pick(sent, ("category", "text", "sort_order"))


def _advantage_columns(
    db: Session, project: Project, sent: Mapping[str, Any], row: Any | None
) -> dict[str, Any]:
    values = _pick(sent, ("label", "kind", "travel_minutes", "sort_order"))
    if "distance_km" in sent:
        km = sent["distance_km"]
        values["distance_km"] = None if km is None else Decimal(str(km)).quantize(Decimal("0.01"))
    return values


def _update_columns(
    db: Session, project: Project, sent: Mapping[str, Any], row: Any | None
) -> dict[str, Any]:
    keys = ("tower_id", "title", "update_date", "progress_percent", "body", "publish_state")
    values = _pick(sent, (*keys, "sort_order"))
    _tower_must_belong(db, project, values.get("tower_id"))
    return values


def _plan_columns(
    db: Session, project: Project, sent: Mapping[str, Any], row: Any | None
) -> dict[str, Any]:
    values = _pick(sent, ("name", "description", "is_visible", "sort_order"))
    if "stages" in sent:
        # Stage order is the list order; sort_order is rewritten to match it.
        values["stages"] = [
            {"label": stage["label"], "percent": stage["percent"], "sort_order": index}
            for index, stage in enumerate(sent["stages"])
        ]
    return values


# --- Per-kind responses ----------------------------------------------------------------------


def _present_towers(db: Session, project_id: uuid.UUID, rows: Sequence[Any]) -> list[BaseModel]:
    updates = db.scalars(
        select(ConstructionUpdate).where(ConstructionUpdate.project_id == project_id)
    ).all()
    progress = present.tower_progress(updates)
    return [present.tower_out(row, progress.get(row.id)) for row in rows]


def _each(fn: Callable[[Any], BaseModel]) -> PresentFn:
    def run(db: Session, project_id: uuid.UUID, rows: Sequence[Any]) -> list[BaseModel]:
        return [fn(row) for row in rows]

    return run


KINDS: Final = {
    kind.key: kind
    for kind in (
        ChildKind("tower", "towers", "tower", Tower, _tower_columns, _present_towers),
        ChildKind(
            "configuration",
            "configurations",
            "configuration",
            Configuration,
            _configuration_columns,
            _each(present.configuration_out),
            {"uq_configuration_project_id_slug": ("slug", CONFIG_SLUG_TAKEN)},
        ),
        ChildKind(
            "specification",
            "specifications",
            "specification",
            Specification,
            _specification_columns,
            _each(present.specification_out),
        ),
        ChildKind(
            "location_advantage",
            "location_advantages",
            "location advantage",
            LocationAdvantage,
            _advantage_columns,
            _each(present.advantage_out),
        ),
        ChildKind(
            "construction_update",
            "construction_updates",
            "construction update",
            ConstructionUpdate,
            _update_columns,
            _each(present.update_out),
        ),
        ChildKind(
            "payment_plan",
            "payment_plans",
            "payment plan",
            PaymentPlan,
            _plan_columns,
            _each(present.plan_out),
        ),
    )
}
