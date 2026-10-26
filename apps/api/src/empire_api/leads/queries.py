"""Read-only service functions other modules call about leads: whether a project has leads (the
projects module refuses to delete it) and the dashboard's counts and short lists.

Collaborators: projects/service.delete_project, dashboard/service.py.
Implements: ARCHITECTURE §2 (modules call service functions, never another module's tables),
§6 ("projects with leads … are archived, not deleted"), §8 (dashboard counts link to the inbox).
SECURITY: every function that returns or counts leads takes the staff member and applies the
object-level rule (access.scope_leads), so the dashboard shows sales their own leads only;
`leads_by_source` is counts only and uses the UTM report's scope (access.report_owner_filter).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from empire_api.leads.access import Staff, report_owner_filter, scope_leads
from empire_api.leads.filters import LeadFilters, conditions, ist_day_start
from empire_api.leads.models import Lead, SiteVisit
from empire_api.leads.present import visit_day_key
from empire_api.leads.visits import VisitFilters, visit_query
from empire_api.leads.vocab import OPEN_VISIT_STATUSES, VISITS_MAX_ROWS


def project_has_leads(db: Session, project_id: uuid.UUID) -> bool:
    """Any lead (spam, sample and erased included) names this project."""
    return bool(db.scalar(select(exists().where(Lead.project_id == project_id))))


def count_matching(db: Session, staff: Staff, filters: LeadFilters) -> int:
    """How many leads the inbox lists for `filters` (same conditions, same access rule), so a
    dashboard count always equals the total its link opens."""
    stmt = scope_leads(
        select(func.count()).select_from(Lead).where(*conditions(filters, staff)), staff
    )
    return int(db.scalar(stmt) or 0)


def latest_leads(db: Session, staff: Staff, limit: int) -> list[Lead]:
    return list(
        db.scalars(
            scope_leads(select(Lead).where(Lead.is_spam.is_(False)), staff)
            .order_by(Lead.created_at.desc(), Lead.id.desc())
            .limit(limit)
        )
    )


def count_visits(db: Session, staff: Staff, filters: VisitFilters) -> int:
    """How many visits the calendar lists for `filters` (the dashboard links there)."""
    stmt = visit_query(staff, filters)
    return int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)


def upcoming_visits(
    db: Session, staff: Staff, today: date, limit: int
) -> list[tuple[SiteVisit, Lead]]:
    """The next open visits from today on, in calendar order."""
    stmt = (
        visit_query(staff, VisitFilters(date_from=today))
        .where(SiteVisit.status.in_(OPEN_VISIT_STATUSES))
        .order_by(SiteVisit.preferred_date, SiteVisit.id)
        .limit(VISITS_MAX_ROWS)
    )
    rows = [(visit, lead) for visit, lead in db.execute(stmt)]
    return sorted(rows, key=lambda row: visit_day_key(row[0]))[:limit]


def leads_by_source(db: Session, staff: Staff, since: date) -> list[tuple[str, int]]:
    """(source, leads) since an IST day, most first. Counts only, with the UTM report's scope
    (access.report_owner_filter): all leads for leads.read_all and for marketing (leads.report
    without leads.read), own leads for sales."""
    stmt = (
        select(Lead.source, func.count())
        .where(Lead.is_spam.is_(False), Lead.created_at >= ist_day_start(since))
        .group_by(Lead.source)
        .order_by(func.count().desc(), Lead.source)
    )
    owner = report_owner_filter(staff)
    if owner is not None:
        stmt = stmt.where(Lead.owner_user_id == owner)
    return [(source, int(count)) for source, count in db.execute(stmt)]


def days_back(today: date, days: int) -> date:
    return today - timedelta(days=days - 1)


def week_bounds(today: date) -> tuple[date, date]:
    """Monday to Sunday of the IST week holding `today`."""
    monday = today - timedelta(days=today.weekday())
    return monday, monday + timedelta(days=6)
