"""Site-visit calendar and the UTM report: /api/v1/admin/site-visits/** and
/api/v1/admin/reports/utm (design contract tag "Leads").

HTTP only: the rules are in visits.py and report.py. Permissions (ARCHITECTURE §11): visits
`site_visits.manage`; the report `leads.report` (counts only). SECURITY.md §1: a visit carries
its lead's name and number, so without `leads.read_all` you see visits of your own leads only.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.leads import present, report, visits
from empire_api.leads.access import Staff
from empire_api.leads.schemas import SiteVisit, SiteVisitUpdate, UtmReportRow
from empire_api.leads.vocab import UtmGroup, VisitStatus
from empire_api.users.deps import require, staff
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Leads"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
VisitId = Annotated[uuid.UUID, Path(alias="id")]
Manager = Annotated[SessionInfo, Depends(require("site_visits.manage"))]
Reporter = Annotated[SessionInfo, Depends(require("leads.report"))]
FromDay = Annotated[date | None, Query(alias="from", description="IST day, included")]
ToDay = Annotated[date | None, Query(alias="to", description="IST day, included")]


@router.get(
    "/site-visits",
    response_model=list[SiteVisit],
    operation_id="list_site_visits",
    summary="Site-visit calendar",
    description=(
        "Calendar order. A visit's day is its confirmed time (IST) once confirmed, else the day "
        "the buyer asked for. At most 500 visits; use from/to for a week or a month."
    ),
    **staff("site_visits.manage"),
)
def list_site_visits(
    actor: Manager,
    request: Request,
    db: Db,
    date_from: FromDay = None,
    date_to: ToDay = None,
    status: VisitStatus | None = None,
    project_id: uuid.UUID | None = None,
    lead_id: Annotated[uuid.UUID | None, Query(description="One lead's visits")] = None,
    still_open: Annotated[
        bool | None,
        Query(alias="open", description="true = requested or confirmed; false = the rest"),
    ] = None,
) -> list[SiteVisit]:
    filters = visits.VisitFilters(date_from, date_to, status, project_id, lead_id, still_open)
    return present.visits_out(db, visits.list_visits(db, Staff.of(actor, request), filters))


@router.patch(
    "/site-visits/{id}",
    response_model=SiteVisit,
    operation_id="update_site_visit",
    summary="Confirm, reschedule, complete",
    description=(
        "Confirm: status `confirmed` with `confirmed_for` (also moves a new or contacted lead to "
        "`site_visit`). Reschedule: a new `confirmed_for`. Also `completed`, `no_show`, "
        "`cancelled`, `handled_by_user_id` and `notes`. Every change is on the lead's timeline "
        "and in the audit log."
    ),
    responses=problem_responses(409),
    **staff("site_visits.manage", write=True),
)
def update_site_visit(
    visit_id: VisitId, body: SiteVisitUpdate, actor: Manager, request: Request, db: Db
) -> SiteVisit:
    viewer = Staff.of(actor, request)
    visits.update_visit(db, viewer, visit_id, body)
    db.expire_all()
    return present.visits_out(db, [visits.load_visit(db, viewer, visit_id)])[0]


@router.get(
    "/reports/utm",
    response_model=list[UtmReportRow],
    operation_id="utm_report",
    summary="Leads by source, campaign and project",
    description=(
        "Counts only, never personal data. `group_by` source, medium, campaign or project; "
        "left out, rows group by all four. Spam never counts. Sales see their own leads' counts."
    ),
    **staff("leads.report"),
)
def utm_report(
    actor: Reporter,
    request: Request,
    db: Db,
    date_from: FromDay = None,
    date_to: ToDay = None,
    group_by: UtmGroup | None = None,
    include_sample: Annotated[bool, Query(description="Seeded sample leads (D-015)")] = True,
) -> list[UtmReportRow]:
    filters = report.ReportFilters(date_from, date_to, group_by, include_sample)
    return report.utm_report(db, Staff.of(actor, request), filters)
