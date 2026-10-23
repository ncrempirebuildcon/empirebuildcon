"""Lead endpoints: /api/v1/admin/leads/** and /api/v1/admin/lead-owners (design contract tag
"Leads").

HTTP only: the rules are in service.py, erasure.py and export.py. Permissions (ARCHITECTURE §11):
read `leads.read`; change, notes and manual leads `leads.update` (a new owner also needs
`leads.assign`); erase `leads.erase`; export `leads.export`.
SECURITY.md §1: without `leads.read_all`, every route here sees only the caller's own leads,
and anyone else's lead answers 404 (access.py).

WHY `/leads/export.csv` is declared before `/leads/{id}`: routes match in order, and "export.csv"
would otherwise reach the detail route and fail as an invalid id (422).
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Final

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.leads import erasure, export, present, service
from empire_api.leads.access import Staff, load_lead
from empire_api.leads.filters import GENERAL, ME, UNASSIGNED, LeadFilters
from empire_api.leads.schemas import (
    Lead,
    LeadActivity,
    LeadList,
    LeadManualCreate,
    LeadNote,
    LeadNoteInput,
    LeadOwner,
    LeadStatusCounts,
    LeadUpdate,
)
from empire_api.leads.vocab import ErasureScope, LeadSource, LeadStatus
from empire_api.pagination import PageParams, page_params
from empire_api.users.deps import require, staff
from empire_api.users.schemas import PageMeta
from empire_api.users.sessions import SessionInfo, csrf_matches

router = APIRouter(
    prefix="/api/v1/admin", tags=["Leads"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]
LeadId = Annotated[uuid.UUID, Path(alias="id")]
Reader = Annotated[SessionInfo, Depends(require("leads.read"))]
Updater = Annotated[SessionInfo, Depends(require("leads.update"))]
Eraser = Annotated[SessionInfo, Depends(require("leads.erase"))]
Exporter = Annotated[SessionInfo, Depends(require("leads.export"))]
CONFLICT = problem_responses(409)
BAD_ID: Final = "Use an id, or {words}."
EXPORT_NEEDS_HEADER: Final = (
    "Export from the CMS: this download needs your session token. Reload the page."
)
EXPORT_SAME_ORIGIN: Final = "Exports can only be started from the CMS itself."


def _id_or_word(value: str | None, field: str, words: tuple[str, ...]) -> str | None:
    if value is None or value in words:
        return value
    try:
        return str(uuid.UUID(value))
    except ValueError as exc:
        message = BAD_ID.format(words=" or ".join(f"'{w}'" for w in words))
        raise ApiProblem(422, message, errors=[{"field": field, "message": message}]) from exc


def lead_filters(
    q: Annotated[
        str | None, Query(max_length=100, description="Name, reference, or the phone's last digits")
    ] = None,
    status: LeadStatus | None = None,
    project_id: Annotated[
        str | None, Query(max_length=36, description="A project's id, or 'none' (general)")
    ] = None,
    owner_id: Annotated[
        str | None, Query(max_length=36, description="An id, 'me' or 'unassigned'")
    ] = None,
    read: Annotated[bool | None, Query(description="false = unread only")] = None,
    source: LeadSource | None = None,
    utm_source: Annotated[
        str | None, Query(max_length=200, description="Exact tag; empty = no tag")
    ] = None,
    utm_medium: Annotated[
        str | None, Query(max_length=200, description="Exact tag; empty = no tag")
    ] = None,
    utm_campaign: Annotated[
        str | None, Query(max_length=200, description="Exact tag; empty = no tag")
    ] = None,
    date_from: Annotated[date | None, Query(alias="from", description="IST day, included")] = None,
    date_to: Annotated[date | None, Query(alias="to", description="IST day, included")] = None,
    include_spam: bool = False,
    is_spam: Annotated[
        bool | None, Query(description="true = spam only; false = no spam (wins over include_spam)")
    ] = None,
    include_sample: Annotated[bool, Query(description="Seeded sample leads (D-015)")] = True,
    still_open: Annotated[
        bool | None,
        Query(
            alias="open",
            description="true = still being worked (not booked, lost or erased); false = the rest",
        ),
    ] = None,
) -> LeadFilters:
    """The inbox filters (filters.py explains each)."""
    return LeadFilters(
        q=q,
        status=status,
        project_id=_id_or_word(project_id, "project_id", (GENERAL,)),
        owner_id=_id_or_word(owner_id, "owner_id", (ME, UNASSIGNED)),
        read=read,
        source=source,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        date_from=date_from,
        date_to=date_to,
        include_spam=include_spam,
        is_spam=is_spam,
        include_sample=include_sample,
        open=still_open,
    )


Filters = Annotated[LeadFilters, Depends(lead_filters)]


def _one(db: Session, lead_id: uuid.UUID, viewer: Staff) -> Lead:
    db.expire_all()
    return present.leads_out(db, [load_lead(db, lead_id, viewer)], viewer)[0]


@router.get(
    "/leads",
    response_model=LeadList,
    operation_id="list_leads",
    summary="Lead inbox, newest first",
    description="Sales users without leads.read_all see only leads assigned to them.",
    **staff("leads.read"),
)
def list_leads(
    actor: Reader, request: Request, db: Db, paging: Paging, filters: Filters
) -> LeadList:
    viewer = Staff.of(actor, request)
    rows, total, counts = service.list_leads(db, viewer, filters, paging)
    return LeadList(
        items=present.leads_out(db, rows, viewer),
        meta=PageMeta(**paging.meta(total)),
        status_counts=LeadStatusCounts(**counts),
    )


@router.post(
    "/leads",
    status_code=201,
    response_model=Lead,
    operation_id="create_lead_manually",
    summary="Add a lead by hand (walk-in, phone call)",
    **staff("leads.update", write=True),
)
def create_lead_manually(body: LeadManualCreate, actor: Updater, request: Request, db: Db) -> Lead:
    """`consent_note` is required. Leaving `owner_user_id` out makes you the owner."""
    viewer = Staff.of(actor, request)
    lead = service.create_manual_lead(db, viewer, body)
    return _one(db, lead.id, viewer)


def _same_origin_download(actor: SessionInfo, request: Request) -> None:
    """SECURITY: the export writes (audit, timeline) and returns personal data, so a cross-site
    page must not be able to trigger it with a link or form. A navigation can't add headers, so
    the CSRF header is required as on any write; a browser's Sec-Fetch-Site, when sent, must say
    same-origin (our web proxy is the only origin)."""
    if not csrf_matches(actor.session.id, request.headers.get("x-csrf-token")):
        raise ApiProblem(403, EXPORT_NEEDS_HEADER)
    site = request.headers.get("sec-fetch-site")
    if site is not None and site != "same-origin":
        raise ApiProblem(403, EXPORT_SAME_ORIGIN)


@router.get(
    "/leads/export.csv",
    operation_id="export_leads",
    summary="CSV export of the filtered list (logged in the audit log)",
    description=(
        "Same filters and access rule as the inbox. At most 50,000 rows (more → 422, narrow the "
        "filters). Every export is in the audit log with its filters and row count (a search is "
        "recorded only by its length), and on each exported lead's timeline. The file contains "
        "personal data. Although it is a GET, it needs the X-CSRF-Token header (403 without it), "
        "and a Sec-Fetch-Site header other than same-origin is refused (403): download it with "
        "fetch and save the blob, never with a plain link. Columns: "
        + ", ".join(export.HEADER)
        + "."
    ),
    response_class=StreamingResponse,
    responses={
        200: {"description": "CSV file", "content": {"text/csv": {"schema": {"type": "string"}}}}
    },
    **staff("leads.export", write=True),
)
def export_leads(actor: Exporter, request: Request, db: Db, filters: Filters) -> StreamingResponse:
    _same_origin_download(actor, request)
    viewer = Staff.of(actor, request)
    export.prepare(db, viewer, filters)
    return StreamingResponse(
        export.stream(viewer, filters),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{export.filename()}"'},
    )


@router.get(
    "/leads/{id}",
    response_model=Lead,
    operation_id="get_lead",
    summary="Lead detail",
    **staff("leads.read"),
)
def get_lead(lead_id: LeadId, actor: Reader, request: Request, db: Db) -> Lead:
    """Reading doesn't mark it read; the CMS calls …/read when the lead is opened."""
    return _one(db, lead_id, Staff.of(actor, request))


@router.patch(
    "/leads/{id}",
    response_model=Lead,
    operation_id="update_lead",
    summary="Change status, owner, details",
    description=(
        "Changing owner needs leads.assign. `lost` needs a `lost_reason` code; `other` also "
        "needs `lost_reason_note`."
    ),
    responses=CONFLICT,
    **staff("leads.update", write=True),
)
def update_lead(
    lead_id: LeadId, body: LeadUpdate, actor: Updater, request: Request, db: Db
) -> Lead:
    viewer = Staff.of(actor, request)
    service.update_lead(db, viewer, lead_id, body)
    return _one(db, lead_id, viewer)


@router.delete(
    "/leads/{id}",
    status_code=204,
    operation_id="erase_lead",
    summary="Erase a lead's personal data on request (keeps an anonymised stub)",
    description=(
        "Erases this lead and its whole duplicate group (the lead it repeats and every lead "
        "that repeats it); `scope=person` also erases every other lead with the same phone "
        "number (`same_phone_count` on the lead says how many). Name and phone become "
        "'[erased]'; email, message, page URL, referrer, click ids, preferred contact time and "
        "the UTM term and content are removed; note texts, the lost-reason note and visit notes "
        "are replaced or removed, in the timeline and stored events too. The reference, stage, "
        "reason code, source, UTM source/medium/campaign, project, timestamps and the consent "
        "record's version and time stay. Audited with the scope and count; can't be undone. "
        "Leads already erased are skipped (204 again)."
    ),
    **staff("leads.erase", write=True),
)
def erase_lead(
    lead_id: LeadId,
    actor: Eraser,
    request: Request,
    db: Db,
    scope: Annotated[
        ErasureScope,
        Query(
            description="group (default): the duplicate group; person: every lead with the phone"
        ),
    ] = "group",
) -> Response:
    erasure.erase_on_request(db, Staff.of(actor, request), lead_id, scope)
    return Response(status_code=204)


@router.post(
    "/leads/{id}/read",
    status_code=204,
    operation_id="mark_lead_read",
    summary="Mark read",
    **staff("leads.read", write=True),
)
def mark_lead_read(lead_id: LeadId, actor: Reader, request: Request, db: Db) -> Response:
    service.set_read(db, Staff.of(actor, request), lead_id, read=True)
    return Response(status_code=204)


@router.post(
    "/leads/{id}/unread",
    status_code=204,
    operation_id="mark_lead_unread",
    summary="Mark unread",
    **staff("leads.read", write=True),
)
def mark_lead_unread(lead_id: LeadId, actor: Reader, request: Request, db: Db) -> Response:
    service.set_read(db, Staff.of(actor, request), lead_id, read=False)
    return Response(status_code=204)


@router.get(
    "/leads/{id}/notes",
    response_model=list[LeadNote],
    operation_id="list_lead_notes",
    summary="Notes",
    **staff("leads.read"),
)
def list_lead_notes(lead_id: LeadId, actor: Reader, request: Request, db: Db) -> list[LeadNote]:
    """Newest first."""
    return present.notes_out(db, service.list_notes(db, Staff.of(actor, request), lead_id))


@router.post(
    "/leads/{id}/notes",
    status_code=201,
    response_model=LeadNote,
    operation_id="add_lead_note",
    summary="Add note",
    responses=CONFLICT,
    **staff("leads.update", write=True),
)
def add_lead_note(
    lead_id: LeadId, body: LeadNoteInput, actor: Updater, request: Request, db: Db
) -> LeadNote:
    note = service.add_note(db, Staff.of(actor, request), lead_id, body.body)
    return present.notes_out(db, [note])[0]


@router.get(
    "/leads/{id}/activity",
    response_model=list[LeadActivity],
    operation_id="lead_activity",
    summary="Timeline",
    **staff("leads.read"),
)
def lead_activity(lead_id: LeadId, actor: Reader, request: Request, db: Db) -> list[LeadActivity]:
    """Newest first. `data` holds ids, stages and times only."""
    viewer = Staff.of(actor, request)
    return present.activity_out(db, service.list_activity(db, viewer, lead_id), viewer)


@router.get(
    "/lead-owners",
    response_model=list[LeadOwner],
    operation_id="list_lead_owners",
    summary="People a lead can be assigned to",
    description="Active accounts whose role can open leads. Contract addition (Phase 4 part 3).",
    **staff("leads.read"),
)
def list_lead_owners(actor: Reader, db: Db) -> list[LeadOwner]:
    return [
        LeadOwner(id=user.id, name=user.name, role=user.role) for user in service.lead_owners(db)
    ]
