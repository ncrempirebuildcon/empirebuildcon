"""Lead and site-visit rows → the contract shapes `Lead`, `SiteVisit`, `LeadNote` and
`LeadActivity`, loading what they name (projects, people, consent, duplicates, visits) in a few
batched queries per page instead of one per row.

Collaborators: service.py, visits.py, dashboard/service.py; projects/queries.py and
users/directory.py for names (ARCHITECTURE §2). Nothing here writes to the database.

SECURITY (SECURITY.md §1): a lead names other leads (its original, its later duplicates) and its
timeline can too. Everything here is shown to a viewer, so another lead appears only when that
viewer may open it (access.owner_filter); otherwise it is left out, and nothing says it exists.
A timeline's `duplicate_linked` line about a lead the viewer can't open becomes a generic line
("A repeat enquiry was linked") with no id, reference, source or actor.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.leads import schemas
from empire_api.leads.access import Staff, owner_filter
from empire_api.leads.models import Lead, LeadActivity, LeadConsent, LeadNote, SiteVisit
from empire_api.leads.vocab import OPEN_VISIT_STATUSES
from empire_api.projects import queries as project_queries
from empire_api.projects.queries import ProjectRef
from empire_api.timeutil import IST
from empire_api.users import directory
from empire_api.users.schemas import UserRef

REPEAT_ENQUIRY: Final = "A repeat enquiry was linked"


def _consent_out(row: LeadConsent | None) -> schemas.LeadConsentRecord | None:
    if row is None:
        return None
    return schemas.LeadConsentRecord(
        consent_text_id=row.consent_text_id,
        text_version=row.version,
        consented_at=row.accepted_at,
        page_url=row.page_url,
        checkbox_label=row.checkbox_label,
        consent_note=row.consent_note,
    )


def visit_out(
    visit: SiteVisit,
    lead: Lead,
    projects: dict[uuid.UUID, ProjectRef],
    people: dict[uuid.UUID, UserRef],
) -> schemas.SiteVisit:
    project = projects[visit.project_id]
    return schemas.SiteVisit(
        id=visit.id,
        lead_id=lead.id,
        lead_reference=lead.reference,
        lead_name=lead.name,
        lead_phone_e164=lead.phone_e164,
        lead_status=lead.status,
        lead_owner=people.get(lead.owner_user_id) if lead.owner_user_id else None,
        project=schemas.SiteVisitProject(id=project.id, slug=project.slug, name=project.name),
        preferred_date=visit.preferred_date,
        preferred_slot=visit.preferred_slot,
        confirmed_for=visit.confirmed_for,
        status=visit.status,
        handled_by=people.get(visit.handled_by_user_id) if visit.handled_by_user_id else None,
        notes=visit.notes,
        is_sample=visit.is_sample,
        created_at=visit.created_at,
        updated_at=visit.updated_at,
    )


def visits_out(db: Session, rows: Sequence[tuple[SiteVisit, Lead]]) -> list[schemas.SiteVisit]:
    projects = project_queries.project_refs(db, (visit.project_id for visit, _ in rows))
    people = directory.user_refs(
        db,
        [visit.handled_by_user_id for visit, _ in rows] + [lead.owner_user_id for _, lead in rows],
    )
    return [visit_out(visit, lead, projects, people) for visit, lead in rows]


def visit_day_key(visit: SiteVisit) -> tuple[object, ...]:
    """Calendar order: the confirmed time (as an IST day) when there is one, else the day asked."""
    day = (
        visit.confirmed_for.astimezone(IST).date() if visit.confirmed_for else visit.preferred_date
    )
    return (day, visit.confirmed_for is None, visit.confirmed_for or visit.created_at, visit.id)


@dataclass
class _Related:
    projects: dict[uuid.UUID, ProjectRef]
    configurations: dict[uuid.UUID, str]
    people: dict[uuid.UUID, UserRef]
    consents: dict[tuple[uuid.UUID, str], LeadConsent]
    originals: dict[uuid.UUID, str]
    duplicates: dict[uuid.UUID, list[schemas.LeadRef]]
    next_visits: dict[uuid.UUID, SiteVisit]
    same_phone: dict[str, int] | None


def _next_visits(db: Session, lead_ids: list[uuid.UUID]) -> dict[uuid.UUID, SiteVisit]:
    """lead id → its open visit that comes first on the calendar."""
    visits = db.scalars(
        select(SiteVisit).where(
            SiteVisit.lead_id.in_(lead_ids), SiteVisit.status.in_(OPEN_VISIT_STATUSES)
        )
    ).all()
    first: dict[uuid.UUID, SiteVisit] = {}
    for visit in sorted(visits, key=visit_day_key):
        first.setdefault(visit.lead_id, visit)
    return first


def _originals(db: Session, leads: Sequence[Lead], viewer: Staff) -> dict[uuid.UUID, str]:
    """original id → reference, for the originals this viewer may open (module SECURITY)."""
    original_ids = {lead.duplicate_of_id for lead in leads if lead.duplicate_of_id}
    if not original_ids:
        return {}
    stmt = select(Lead.id, Lead.reference).where(Lead.id.in_(original_ids))
    owner = owner_filter(viewer)
    if owner is not None:
        stmt = stmt.where(Lead.owner_user_id == owner)
    return dict(db.execute(stmt).all())


def _duplicates(
    db: Session, ids: list[uuid.UUID], viewer: Staff
) -> dict[uuid.UUID, list[schemas.LeadRef]]:
    """original id → its later duplicates that this viewer may open (module SECURITY)."""
    stmt = (
        select(Lead.duplicate_of_id, Lead.id, Lead.reference, Lead.source, Lead.created_at)
        .where(Lead.duplicate_of_id.in_(ids))
        .order_by(Lead.created_at, Lead.id)
    )
    owner = owner_filter(viewer)
    if owner is not None:
        stmt = stmt.where(Lead.owner_user_id == owner)
    found: dict[uuid.UUID, list[schemas.LeadRef]] = defaultdict(list)
    for original, lead_id, reference, source, created_at in db.execute(stmt):
        if original is not None:
            found[original].append(
                schemas.LeadRef(
                    id=lead_id, reference=reference, source=source, created_at=created_at
                )
            )
    return found


def _same_phone(db: Session, leads: Sequence[Lead], viewer: Staff) -> dict[str, int] | None:
    """phone → how many leads have it, for viewers who may erase (the erase dialog's offer)."""
    if not viewer.can("leads.erase"):
        return None
    phones = {lead.phone_e164 for lead in leads if lead.erased_at is None}
    if not phones:
        return {}
    rows = db.execute(
        select(Lead.phone_e164, func.count())
        .where(Lead.phone_e164.in_(phones), Lead.erased_at.is_(None))
        .group_by(Lead.phone_e164)
    )
    return {phone: int(count) for phone, count in rows}


def _related(db: Session, leads: Sequence[Lead], viewer: Staff) -> _Related:
    ids = [lead.id for lead in leads]
    consents = {
        (row.lead_id, row.kind): row
        for row in db.scalars(select(LeadConsent).where(LeadConsent.lead_id.in_(ids)))
    }
    next_visits = _next_visits(db, ids)
    projects = project_queries.project_refs(
        db, [lead.project_id for lead in leads] + [v.project_id for v in next_visits.values()]
    )
    people = directory.user_refs(
        db,
        [lead.owner_user_id for lead in leads]
        + [v.handled_by_user_id for v in next_visits.values()],
    )
    return _Related(
        projects=projects,
        configurations=project_queries.configuration_names(
            db, (lead.configuration_id for lead in leads)
        ),
        people=people,
        consents=consents,
        originals=_originals(db, leads, viewer),
        duplicates=_duplicates(db, ids, viewer),
        next_visits=next_visits,
        same_phone=_same_phone(db, leads, viewer),
    )


def _lead_out(lead: Lead, related: _Related) -> schemas.Lead:
    project = related.projects.get(lead.project_id) if lead.project_id else None
    config_name = (
        related.configurations.get(lead.configuration_id) if lead.configuration_id else None
    )
    consent = _consent_out(related.consents.get((lead.id, "lead_form")))
    assert consent is not None  # noqa: S101 — INVARIANT: every lead has a lead_form consent row
    visit = related.next_visits.get(lead.id)
    return schemas.Lead(
        id=lead.id,
        reference=lead.reference,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        last_activity_at=lead.last_activity_at,
        name=lead.name,
        phone_e164=lead.phone_e164,
        email=lead.email,
        message=lead.message,
        project=(
            schemas.LeadProjectRef(id=project.id, slug=project.slug, name=project.name)
            if project
            else None
        ),
        configuration=(
            schemas.LeadConfigurationRef(id=lead.configuration_id, name=config_name)
            if lead.configuration_id and config_name is not None
            else None
        ),
        source=lead.source,
        status=lead.status,
        lost_reason=lead.lost_reason,
        lost_reason_note=lead.lost_reason_note,
        owner=related.people.get(lead.owner_user_id) if lead.owner_user_id else None,
        assigned_at=lead.assigned_at,
        read_at=lead.read_at,
        page_url=lead.page_url,
        referrer=lead.referrer,
        utm=schemas.Utm(
            source=lead.utm_source,
            medium=lead.utm_medium,
            campaign=lead.utm_campaign,
            term=lead.utm_term,
            content=lead.utm_content,
        ),
        click_ids=schemas.ClickIds(
            gclid=lead.gclid,
            gbraid=lead.gbraid,
            wbraid=lead.wbraid,
            fbclid=lead.fbclid,
            msclkid=lead.msclkid,
        ),
        preferred_bhk=None if lead.preferred_bhk is None else float(lead.preferred_bhk),
        budget_max_inr=lead.budget_max_inr,
        preferred_contact_time=lead.preferred_contact_time,
        language=lead.language,
        consent=consent,
        marketing_consent=_consent_out(related.consents.get((lead.id, "marketing"))),
        is_spam=lead.is_spam,
        is_sample=lead.is_sample,
        erased_at=lead.erased_at,
        # SECURITY: only an original the viewer may open (module header).
        duplicate_of=lead.duplicate_of_id if lead.duplicate_of_id in related.originals else None,
        duplicate_of_reference=(
            related.originals.get(lead.duplicate_of_id) if lead.duplicate_of_id else None
        ),
        duplicates=related.duplicates.get(lead.id, []),
        same_phone_count=(
            related.same_phone.get(lead.phone_e164)
            if related.same_phone is not None and lead.erased_at is None
            else None
        ),
        next_visit=(
            visit_out(visit, lead, related.projects, related.people) if visit is not None else None
        ),
    )


def leads_out(db: Session, leads: Sequence[Lead], viewer: Staff) -> list[schemas.Lead]:
    """Leads as this viewer may see them (module SECURITY)."""
    if not leads:
        return []
    related = _related(db, leads, viewer)
    return [_lead_out(lead, related) for lead in leads]


def notes_out(db: Session, notes: Iterable[LeadNote]) -> list[schemas.LeadNote]:
    rows = list(notes)
    people = directory.user_refs(db, (note.author_user_id for note in rows))
    return [
        schemas.LeadNote(
            id=note.id,
            author=(people.get(note.author_user_id) if note.author_user_id else None)
            or UserRef(id=uuid.UUID(int=0), name=directory.UNKNOWN_NAME),
            body=note.body,
            created_at=note.created_at,
        )
        for note in rows
    ]


def _visible_lead_ids(db: Session, lead_ids: set[uuid.UUID], viewer: Staff) -> set[uuid.UUID]:
    owner = owner_filter(viewer)
    if not lead_ids or owner is None:
        return lead_ids
    found = db.scalars(
        select(Lead.id).where(Lead.id.in_(lead_ids), Lead.owner_user_id == owner)
    ).all()
    return set(found)


def _named_lead(data: dict[str, Any], key: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(data[key])) if data.get(key) else None
    except ValueError:
        return None


def activity_out(
    db: Session, rows: Iterable[LeadActivity], viewer: Staff
) -> list[schemas.LeadActivity]:
    """The timeline as this viewer may see it: lines naming another lead the viewer can't open
    say nothing about it (module SECURITY)."""
    items = list(rows)
    named = {
        lead_id
        for row in items
        for key in ("lead_id", "duplicate_of")
        if (lead_id := _named_lead(row.data, key)) is not None
    }
    visible = _visible_lead_ids(db, named, viewer)
    people = directory.user_refs(db, (row.actor_user_id for row in items))
    out = []
    for row in items:
        data, actor_id = dict(row.data), row.actor_user_id
        if row.kind == "duplicate_linked" and _named_lead(data, "lead_id") not in visible:
            data, actor_id = {"summary": REPEAT_ENQUIRY}, None
        elif (other := _named_lead(data, "duplicate_of")) is not None and other not in visible:
            data["duplicate_of"] = None
        out.append(
            schemas.LeadActivity(
                id=row.id,
                kind=row.kind,
                actor=people.get(actor_id) if actor_id else None,
                data=data,
                created_at=row.created_at,
            )
        )
    return out
