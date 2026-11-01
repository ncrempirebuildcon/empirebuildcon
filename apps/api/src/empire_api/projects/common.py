"""Helpers shared by the projects module's services: who is acting, audit snapshots, outbox
events, locking a project, slugs, and turning database conflicts into 409 problems.

Collaborators: service.py, children.py, catalogue.py; platform/audit.py and platform/outbox.py.
Implements: ARCHITECTURE §9 (events in the same transaction), §11 (audit on every change).

INVARIANT: helpers here only add to the caller's session; the service function commits once,
so a change, its audit row and its event are saved together or not at all.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.logs import get_logger
from empire_api.platform import audit, outbox
from empire_api.projects.models import Project

INVALID: Final = "Some fields need attention."
SLUG_MAX: Final = 120

log = get_logger(__name__)


@dataclass(frozen=True)
class Actor:
    """The signed-in staff member making a change, as the services need it."""

    user_id: uuid.UUID
    ip: str | None
    can_publish: bool = False


@dataclass(frozen=True)
class FieldError:
    field: str
    message: str


def invalid(errors: Iterable[FieldError], detail: str = INVALID) -> ApiProblem:
    """A 422 problem listing field errors (same shape as request validation errors)."""
    return ApiProblem(
        422, detail, errors=[{"field": e.field, "message": e.message} for e in errors]
    )


def conflict(detail: str, field: str | None = None, message: str | None = None) -> ApiProblem:
    errors = [{"field": field, "message": message or detail}] if field else None
    return ApiProblem(409, detail, errors=errors)


# --- Slugs -----------------------------------------------------------------------------------


# Characters with an obvious ASCII spelling in names: "24×7" → "24x7", "Children's" → "childrens".
_SLUG_SPELLINGS: Final = str.maketrans({"×": "x", "&": " and ", "'": "", "’": ""})


def slugify(text: str, max_length: int = SLUG_MAX) -> str:
    """ "Sample — Project A" → "sample-project-a". Accents are dropped; other scripts vanish,
    so the caller must handle an empty result (e.g. a Hindi-only name)."""
    spelled = text.translate(_SLUG_SPELLINGS)
    ascii_text = unicodedata.normalize("NFKD", spelled).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug[:max_length].rstrip("-")


def with_suffix(base: str, suffix: str, max_length: int = SLUG_MAX) -> str:
    """`base` + `suffix`, cutting `base` so the result fits: ("long…", "-copy-2")."""
    return f"{base[: max_length - len(suffix)].rstrip('-')}{suffix}"


def slug_or_error(explicit: str | None, name: str, field: str = "slug") -> str:
    slug = explicit or slugify(name)
    if not slug:
        raise invalid(
            [FieldError(field, "Add a web address (slug) using English letters or numbers.")]
        )
    return slug


# --- Price and area columns (shared by projects and configurations) --------------------------

# API `Price` keys → PriceColumns (models.py). `display` is read-only and never stored.
PRICE_COLUMNS: Final = {
    "on_request": "price_on_request",
    "min_inr": "price_min_inr",
    "max_inr": "price_max_inr",
    "rate_inr": "rate_inr",
    "rate_unit": "rate_unit",
    "note": "price_note",
}


def price_columns(sent: Mapping[str, Any]) -> dict[str, Any]:
    """The price columns a (possibly partial) `Price` body sets."""
    return {column: sent[key] for key, column in PRICE_COLUMNS.items() if key in sent}


def to_sqm(value: float | None) -> Decimal | None:
    """Square metres as stored: two decimals (numeric(12, 2))."""
    return None if value is None else Decimal(str(value)).quantize(Decimal("0.01"))


def check_price(state: Mapping[str, Any], prefix: str = "price") -> list[FieldError]:
    """Range and rate rules on the merged (stored + sent) price columns."""
    errors: list[FieldError] = []
    low, high = state.get("price_min_inr"), state.get("price_max_inr")
    if low is not None and high is not None and low > high:
        errors.append(
            FieldError(f"{prefix}.max_inr", "The highest price can't be below the lowest.")
        )
    if state.get("rate_inr") is not None and state.get("rate_unit") is None:
        errors.append(
            FieldError(f"{prefix}.rate_unit", "Choose what the rate is per: sq ft, sq yd or sq m.")
        )
    return errors


def check_area(low: Decimal | None, high: Decimal | None, prefix: str) -> list[FieldError]:
    if low is not None and high is not None and low > high:
        return [FieldError(f"{prefix}.max_sqm", "The largest area can't be below the smallest.")]
    return []


def escape_like(text: str) -> str:
    """Escape LIKE wildcards so user text matches literally (pair with `escape="\\\\"`)."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def like_pattern(text: str) -> str:
    """`%text%` for a case-insensitive "contains" match on lower-cased columns."""
    return f"%{escape_like(text.strip().lower())}%"


# --- Audit and events ------------------------------------------------------------------------


def jsonable(value: Any) -> Any:
    """Audit diffs are JSON: ids and dates become strings, numeric columns become floats."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, Mapping):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    return value


def snapshot(row: Any, skip: Iterable[str] = ()) -> dict[str, Any]:
    """Column values of a row for audit diffs (timestamps left out: they always change)."""
    skipped = {"created_at", "updated_at", *skip}
    return {
        column.key: jsonable(getattr(row, column.key))
        for column in row.__table__.columns
        if column.key not in skipped and getattr(column, "computed", None) is None
    }


def record(
    db: Session,
    actor: Actor,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    before: Mapping[str, Any] | None = None,
    after: Mapping[str, Any] | None = None,
    changes: dict[str, Any] | None = None,
) -> None:
    """One audit row with a before/after diff (ARCHITECTURE §11)."""
    diff = changes if changes is not None else audit.diff(dict(before or {}), dict(after or {}))
    if before and after is None:  # a delete: keep what was removed
        diff = {key: [value, None] for key, value in before.items()}
    audit.record(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor.user_id,
        ip=actor.ip,
        changes=diff,
    )


def emit(
    db: Session,
    actor: Actor,
    project: Project,
    type_: str,
    *,
    aggregate_type: str = "project",
    aggregate_id: uuid.UUID | None = None,
    **data: Any,
) -> None:
    """An outbox event about a project or one of its children (ARCHITECTURE §9).

    The payload always names the project (id and slug) so consumers can revalidate its pages.
    No personal data is ever included.
    """
    outbox.emit(
        db,
        type_=type_,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id or project.id,
        actor_id=actor.user_id,
        data={"project_id": str(project.id), "slug": project.slug, **jsonable(data)},
    )


def touch(project: Project, actor: Actor) -> None:
    """A child changed: the project counts as edited (list order, "last edited by")."""
    project.updated_by = actor.user_id
    project.updated_at = func.now()


def lock_project(db: Session, project_id: uuid.UUID) -> Project:
    """The project row, locked until commit, or 404.

    WHY lock: publish checks "at least one configuration" while another request might delete
    the last one; locking the parent row serialises every write to one project's tree.
    """
    project = db.get(Project, project_id, with_for_update=True, populate_existing=True)
    if project is None:
        raise ApiProblem(404, "No project with this id.")
    return project


# --- Flush and commit ------------------------------------------------------------------------

Conflicts = Mapping[str, tuple[str, str]]


def flush(db: Session, conflicts: Conflicts | None = None) -> None:
    """Flush, turning a unique-constraint violation into a 409 with a field error.

    WHY: services check "slug is free" first, but two requests can pass that check at the same
    moment; the database's unique index then refuses the second at INSERT/UPDATE time, which
    happens here (before the commit). Same mapping as `commit`.
    """
    _guard(db, db.flush, conflicts)


def commit(db: Session, conflicts: Conflicts | None = None) -> None:
    """Commit, turning a unique-constraint race into a 409 with a field error.

    `conflicts` maps a constraint name to (field, message). Any other integrity error is a bug
    and is re-raised (it becomes a logged 500).
    """
    _guard(db, db.commit, conflicts)


def _guard(db: Session, action: Callable[[], None], conflicts: Conflicts | None) -> None:
    try:
        action()
    except IntegrityError as exc:
        db.rollback()
        name = str(getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or "")
        if conflicts and name in conflicts:
            field, message = conflicts[name]
            raise conflict(message, field, message) from exc
        log.error("integrity_error", constraint=name)
        raise
