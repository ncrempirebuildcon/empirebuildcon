"""Site visits in the CMS: the calendar list and changes (confirm, reschedule, complete, no-show,
cancel, who handles it, notes).

Collaborators: routes_visits.py (HTTP), access.py, effects.py, present.py.
Implements: D-016 ("sales confirms by phone and records it in the calendar"), ARCHITECTURE §8,
§9 (`site_visit.updated`), SECURITY.md §1 (a visit shows its lead's name and number, so the
lead's object-level rule applies: without leads.read_all, only visits of your own leads).

Rules:
  - A visit's calendar day is its confirmed time (in IST) once confirmed, else the day asked.
  - `confirmed` needs a time: sent now, or already on the visit. A new time on a confirmed
    visit is a reschedule.
  - Any status may follow any other (staff correct mistakes); the timeline records each move.
  - The change INTO `confirmed` moves the lead to `site_visit` when it is still `new` or
    `contacted`, recorded and announced like any stage change. It never moves a lead backwards,
    and a later edit of a confirmed visit (time, notes, handler) never moves it again: staff
    may have moved the lead back on purpose.
  - `handled_by` must be an active person with `site_visits.manage`.
  - Visits of erased leads can't be changed (409).

INVARIANT: each change commits once, with its timeline rows, audit row and events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Final

from sqlalchemy import ColumnElement, Select, and_, not_, or_, select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.leads import effects
from empire_api.leads.access import Staff, scope_leads
from empire_api.leads.filters import ist_day_start
from empire_api.leads.models import Lead, SiteVisit
from empire_api.leads.present import visit_day_key
from empire_api.leads.schemas import SiteVisitUpdate
from empire_api.leads.vocab import OPEN_VISIT_STATUSES, VISITS_MAX_ROWS
from empire_api.timeutil import utcnow
from empire_api.users import directory

NO_VISIT: Final = "No site visit with this id."
NEEDS_TIME: Final = "Add the agreed date and time to confirm the visit."
HANDLER_INVALID: Final = "Choose an active team member who manages site visits."
ERASED: Final = "This visit's lead was erased, so the visit can't be changed."
NOT_NULL: Final = "Send a value; this can't be empty."
# Lead stages a confirmed visit moves forward to `site_visit`.
_BEFORE_VISIT: Final = frozenset({"new", "contacted"})


@dataclass(frozen=True)
class VisitFilters:
    date_from: date | None = None
    date_to: date | None = None
    status: str | None = None
    project_id: uuid.UUID | None = None
    lead_id: uuid.UUID | None = None
    # true = still on the calendar (requested or confirmed); the dashboard's visit counts.
    open: bool | None = None

    def query_params(self) -> dict[str, str]:
        """The filters as the calendar URL writes them (only those set): dashboard links."""
        values = {
            "from": self.date_from.isoformat() if self.date_from else None,
            "to": self.date_to.isoformat() if self.date_to else None,
            "status": self.status,
            "project_id": str(self.project_id) if self.project_id else None,
            "lead_id": str(self.lead_id) if self.lead_id else None,
            "open": None if self.open is None else ("true" if self.open else "false"),
        }
        return {key: value for key, value in values.items() if value is not None}


def _on_or_after(day: date) -> ColumnElement[bool]:
    return or_(
        SiteVisit.confirmed_for >= ist_day_start(day),
        and_(SiteVisit.confirmed_for.is_(None), SiteVisit.preferred_date >= day),
    )


def _before(day: date) -> ColumnElement[bool]:
    return or_(
        SiteVisit.confirmed_for < ist_day_start(day),
        and_(SiteVisit.confirmed_for.is_(None), SiteVisit.preferred_date < day),
    )


def visit_query(staff: Staff, filters: VisitFilters) -> Select[SiteVisit, Lead]:
    """Visits joined to their (visible) leads, filtered; the caller orders and limits."""
    stmt = scope_leads(select(SiteVisit, Lead).join(Lead, Lead.id == SiteVisit.lead_id), staff)
    if filters.date_from is not None:
        stmt = stmt.where(_on_or_after(filters.date_from))
    if filters.date_to is not None:
        stmt = stmt.where(_before(filters.date_to + timedelta(days=1)))
    for column, value in (
        (SiteVisit.status, filters.status),
        (SiteVisit.project_id, filters.project_id),
        (SiteVisit.lead_id, filters.lead_id),
    ):
        if value is not None:
            stmt = stmt.where(column == value)
    if filters.open is not None:
        still_open = SiteVisit.status.in_(OPEN_VISIT_STATUSES)
        stmt = stmt.where(still_open if filters.open else not_(still_open))
    return stmt


def list_visits(db: Session, staff: Staff, filters: VisitFilters) -> list[tuple[SiteVisit, Lead]]:
    """Calendar order (present.visit_day_key), at most VISITS_MAX_ROWS."""
    result = db.execute(
        visit_query(staff, filters)
        .order_by(SiteVisit.preferred_date, SiteVisit.id)
        .limit(VISITS_MAX_ROWS)
    )
    rows = [(visit, lead) for visit, lead in result]
    return sorted(rows, key=lambda row: visit_day_key(row[0]))


def load_visit(
    db: Session, staff: Staff, visit_id: uuid.UUID, *, lock: bool = False
) -> tuple[SiteVisit, Lead]:
    """The visit and its lead, or 404 (also when the lead isn't visible: SECURITY.md §1)."""
    stmt = visit_query(staff, VisitFilters()).where(SiteVisit.id == visit_id)
    if lock:
        stmt = stmt.with_for_update()
    row = db.execute(stmt.execution_options(populate_existing=True)).first()
    if row is None:
        raise ApiProblem(404, NO_VISIT)
    return row


def _field(status: int, field: str, message: str) -> ApiProblem:
    return ApiProblem(status, message, errors=[{"field": field, "message": message}])


def _check(db: Session, visit: SiteVisit, sent: dict[str, Any]) -> None:
    if "status" in sent and sent["status"] is None:
        raise _field(422, "status", NOT_NULL)
    status = sent.get("status", visit.status)
    confirmed_for = sent.get("confirmed_for", visit.confirmed_for)
    if status == "confirmed" and confirmed_for is None:
        raise _field(422, "confirmed_for", NEEDS_TIME)
    handler = sent.get("handled_by_user_id")
    if handler is not None and not directory.is_active_with(db, handler, "site_visits.manage"):
        raise _field(422, "handled_by_user_id", HANDLER_INVALID)


_TRACKED: Final = ("status", "confirmed_for", "handled_by_user_id", "notes")


def _values(visit: SiteVisit) -> dict[str, Any]:
    return {key: getattr(visit, key) for key in _TRACKED}


def _audit_diff(
    before: dict[str, Any], after: dict[str, Any], changed: list[str]
) -> dict[str, Any]:
    """SECURITY.md §8: notes are free text, so the audit row says only that they changed."""
    return {
        key: [effects.HIDDEN, effects.HIDDEN] if key == "notes" else [before[key], after[key]]
        for key in changed
    }


def update_visit(db: Session, staff: Staff, visit_id: uuid.UUID, body: SiteVisitUpdate) -> None:
    """Apply a change (module rules).

    How it works:
      1. Lock the visit and its lead (404 when not visible; 409 when the lead was erased).
      2. Check the change, apply it, and record what changed on the lead's timeline.
      3. A confirm moves an early-stage lead to `site_visit` (recorded and announced).
      4. One audit row and `site_visit.updated`; commit once. Nothing changed → nothing written.
    """
    visit, lead = load_visit(db, staff, visit_id, lock=True)  # 1
    if lead.erased_at is not None:
        raise ApiProblem(409, ERASED)
    sent = body.model_dump(exclude_unset=True)
    _check(db, visit, sent)  # 2
    before = _values(visit)
    for key, value in sent.items():
        setattr(visit, key, value)
    after = _values(visit)
    changed = [key for key in _TRACKED if before[key] != after[key]]
    if not changed:
        db.rollback()
        return
    now = utcnow()
    effects.activity(
        db,
        lead,
        "visit_updated",
        staff.user_id,
        now,
        visit_id=visit.id,
        from_status=before["status"],
        to_status=visit.status,
        confirmed_for=visit.confirmed_for,
        changed=changed,
    )
    newly_confirmed = before["status"] != "confirmed" and visit.status == "confirmed"
    moved = _move_lead(db, staff, lead, visit, now) if newly_confirmed else None  # 3
    diff = _audit_diff(before, after, changed)
    if moved:
        diff["lead_status"] = [moved, lead.status]
    effects.record(  # 4
        db,
        action="site_visit.updated",
        entity_type="site_visit",
        lead_id=visit.id,
        actor_id=staff.user_id,
        ip=staff.ip,
        changes=diff,
    )
    effects.visit_event(db, visit, "site_visit.updated", staff.user_id, changed=changed)
    db.commit()


def _move_lead(
    db: Session, staff: Staff, lead: Lead, visit: SiteVisit, now: datetime
) -> str | None:
    """Step 3, only when the visit has just become confirmed (not on a later edit of a confirmed
    visit: staff may have moved the lead back on purpose). Returns the lead's previous stage
    when it moved, else None."""
    if lead.status not in _BEFORE_VISIT:
        return None
    previous = lead.status
    lead.status = "site_visit"
    effects.activity(
        db,
        lead,
        "status_changed",
        staff.user_id,
        now,
        **{"from": previous, "to": "site_visit"},
        direction="forward",
        via="site_visit_confirmed",
        visit_id=visit.id,
    )
    effects.status_changed(
        db, lead, previous, staff.user_id, via="site_visit_confirmed", visit_id=visit.id
    )
    return previous
