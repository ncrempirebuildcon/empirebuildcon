"""The UTM report: how many leads, visit requests and bookings each campaign brought, by UTM
source, medium and campaign and by project. Counts only (`leads.report`).

Collaborators: routes_visits.py (GET /admin/reports/utm), access.report_owner_filter,
projects/queries.py (project names).
Implements: ARCHITECTURE §11 (leads.report: counts only, no personal data), SECURITY.md §1
(sales see counts of their own leads; access.py explains why marketing sees all counts).

Rules:
  - `group_by` one of source, medium, campaign or project; left out, rows are grouped by all
    four together. Leads with no tag are grouped under null ("direct / none").
  - `from` / `to` are IST days, both included, on the day the lead arrived. Left out: all time.
  - Spam never counts. Sample leads count unless `include_sample=false` (none in production).
  - `site_visits` counts leads with at least one visit request; `booked` counts booked leads.
COMPLIANCE: the answer holds tags, project names and counts, never a lead's own data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Final

from sqlalchemy import func, null, select
from sqlalchemy.orm import Session

from empire_api.leads.access import Staff, report_owner_filter
from empire_api.leads.filters import ist_day_start
from empire_api.leads.models import Lead, SiteVisit
from empire_api.leads.schemas import UtmReportRow
from empire_api.leads.vocab import UtmGroup
from empire_api.projects import queries as project_queries

_COLUMNS: Final[dict[str, Any]] = {
    "source": Lead.utm_source,
    "medium": Lead.utm_medium,
    "campaign": Lead.utm_campaign,
    "project": Lead.project_id,
}


@dataclass(frozen=True)
class ReportFilters:
    date_from: date | None = None
    date_to: date | None = None
    group_by: UtmGroup | None = None
    include_sample: bool = True


def utm_report(db: Session, staff: Staff, filters: ReportFilters) -> list[UtmReportRow]:
    """Rows with the most leads first (module rules)."""
    groups = [filters.group_by] if filters.group_by else list(_COLUMNS)
    picked = {
        name: (column if name in groups else null()).label(name)
        for name, column in _COLUMNS.items()
    }
    visited = select(SiteVisit.lead_id).distinct().subquery()
    stmt = (
        select(
            *picked.values(),
            func.count(Lead.id).label("leads"),
            func.count(visited.c.lead_id).label("site_visits"),
            func.count(Lead.id).filter(Lead.status == "booked").label("booked"),
        )
        .select_from(Lead)
        .outerjoin(visited, visited.c.lead_id == Lead.id)
        .where(Lead.is_spam.is_(False))
        .group_by(*(_COLUMNS[name] for name in groups))
        .order_by(func.count(Lead.id).desc(), *(_COLUMNS[name] for name in groups))
    )
    owner = report_owner_filter(staff)
    if owner is not None:
        stmt = stmt.where(Lead.owner_user_id == owner)
    if filters.date_from is not None:
        stmt = stmt.where(Lead.created_at >= ist_day_start(filters.date_from))
    if filters.date_to is not None:
        stmt = stmt.where(Lead.created_at < ist_day_start(filters.date_to + timedelta(days=1)))
    if not filters.include_sample:
        stmt = stmt.where(Lead.is_sample.is_(False))
    rows = db.execute(stmt).mappings().all()
    projects = project_queries.project_refs(db, (row["project"] for row in rows))
    return [_row(row, projects) for row in rows]


def _row(row: Any, projects: dict[uuid.UUID, project_queries.ProjectRef]) -> UtmReportRow:
    project_id = row["project"]
    project = projects.get(project_id) if project_id else None
    return UtmReportRow(
        source=row["source"],
        medium=row["medium"],
        campaign=row["campaign"],
        project=project.name if project else None,
        project_id=project_id,
        leads=int(row["leads"]),
        site_visits=int(row["site_visits"]),
        booked=int(row["booked"]),
    )
