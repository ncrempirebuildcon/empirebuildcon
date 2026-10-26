"""Staff work on leads: the inbox, one lead, pipeline and detail changes, read/unread, notes, the
timeline, manual leads and the list of people a lead can be assigned to.

Collaborators: routes.py (HTTP), access.py (who sees what), filters.py, effects.py, routing.py,
creation.py, present.py.
Implements: ARCHITECTURE §8 (pipeline, inbox), §9 (lead.status_changed, lead.assigned), §11
(leads.* permissions, audit), SECURITY.md §1 (object-level rule), §8.

Pipeline rules:
  - Stages: new → contacted → site_visit → negotiation → booked / lost. Staff may also move a
    lead back (correcting a mistake); the timeline records the direction.
  - `lost` needs a reason code (vocab.LOST_REASON_LABELS); `other` also needs a short note.
    Leaving `lost` clears both, and a reason or note without `lost` is refused.
  - Changing the owner needs `leads.assign`, and the new owner must be an active person who can
    open leads (`leads.read`).
  - An erased lead keeps its stub; it can't be changed or get notes (409).
  - Every change writes timeline rows and one audit row, and emits `lead.status_changed` and/or
    `lead.assigned`. Other detail changes (email, BHK, budget, project, spam) emit no event yet.

INVARIANT: each write commits once, after its activity, audit row and events.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.leads import creation, effects, routing
from empire_api.leads.access import Staff, load_lead, owner_filter, scope_leads
from empire_api.leads.filters import LeadFilters, conditions
from empire_api.leads.models import Lead, LeadActivity, LeadNote
from empire_api.leads.phone import PhoneError, normalise_phone
from empire_api.leads.schemas import LeadManualCreate, LeadUpdate
from empire_api.leads.vocab import LEAD_STATUSES, PIPELINE
from empire_api.pagination import PageParams
from empire_api.projects import queries as project_queries
from empire_api.timeutil import utcnow
from empire_api.users import directory
from empire_api.users.models import User

ERASED_LEAD: Final = "This lead's personal data was erased, so it can't be changed."
NEEDS_ASSIGN: Final = "Only admins can change who a lead belongs to."
OWNER_INVALID: Final = routing.OWNER_INVALID
LOST_NEEDS_REASON: Final = "Pick a reason to mark this lead lost."
OTHER_NEEDS_NOTE: Final = "Say in a few words why the lead was lost."
REASON_ONLY_LOST: Final = "A reason is only kept for lost leads."
NO_PROJECT: Final = "No project with this id."
NOT_NULL: Final = "Send a value; this can't be empty."


def _field(status: int, field: str, message: str) -> ApiProblem:
    return ApiProblem(status, message, errors=[{"field": field, "message": message}])


# --- Reading ---------------------------------------------------------------------------------


def list_leads(
    db: Session, staff: Staff, filters: LeadFilters, paging: PageParams
) -> tuple[list[Lead], int, dict[str, int]]:
    """The inbox page, newest first, its total, and leads per stage (ignoring `status`)."""
    stmt = scope_leads(select(Lead).where(*conditions(filters, staff)), staff)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(Lead.created_at.desc(), Lead.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    by_stage = scope_leads(
        select(Lead.status, func.count())
        .where(*conditions(filters, staff, with_status=False))
        .group_by(Lead.status),
        staff,
    )
    counts = dict.fromkeys(LEAD_STATUSES, 0)
    counts.update({status: int(count) for status, count in db.execute(by_stage)})
    return list(rows), total, counts


def list_notes(db: Session, staff: Staff, lead_id: uuid.UUID) -> list[LeadNote]:
    load_lead(db, lead_id, staff)
    return list(
        db.scalars(
            select(LeadNote)
            .where(LeadNote.lead_id == lead_id)
            .order_by(LeadNote.created_at.desc(), LeadNote.id.desc())
        )
    )


def list_activity(db: Session, staff: Staff, lead_id: uuid.UUID) -> list[LeadActivity]:
    load_lead(db, lead_id, staff)
    return list(
        db.scalars(
            select(LeadActivity)
            .where(LeadActivity.lead_id == lead_id)
            .order_by(LeadActivity.created_at.desc(), LeadActivity.id.desc())
        )
    )


def lead_owners(db: Session) -> list[User]:
    """Everyone a lead can be assigned to: accounts that can sign in (not just invited) and
    open leads (routing.owner_refusal)."""
    return directory.ready_users_with(db, routing.OWNER_PERMISSION)


# --- Pipeline and details --------------------------------------------------------------------


def _direction(before: str, after: str) -> str:
    if PIPELINE[after] > PIPELINE[before]:
        return "forward"
    return "backward" if PIPELINE[after] < PIPELINE[before] else "sideways"


def _check_owner(db: Session, staff: Staff, lead: Lead, sent: dict[str, Any]) -> None:
    if "owner_user_id" not in sent or sent["owner_user_id"] == lead.owner_user_id:
        sent.pop("owner_user_id", None)
        return
    if not staff.can("leads.assign"):
        raise ApiProblem(403, NEEDS_ASSIGN)
    new_owner = sent["owner_user_id"]
    refusal = routing.owner_refusal(db, new_owner) if new_owner is not None else None
    if refusal is not None:
        raise _field(422, "owner_user_id", refusal)


def _check_status(lead: Lead, sent: dict[str, Any]) -> None:
    """Fills `sent` with the final status, reason code and note (module rules)."""
    for key in ("status", "is_spam"):
        if key in sent and sent[key] is None:
            raise _field(422, key, NOT_NULL)
    target = sent.get("status", lead.status)
    reason = sent.get("lost_reason", lead.lost_reason)
    note = sent.get("lost_reason_note", lead.lost_reason_note)
    if target == "lost":
        if reason is None:
            raise _field(422, "lost_reason", LOST_NEEDS_REASON)
        if reason == "other" and not note:
            raise _field(422, "lost_reason_note", OTHER_NEEDS_NOTE)
    else:
        for key in ("lost_reason", "lost_reason_note"):
            if sent.get(key):
                raise _field(422, key, REASON_ONLY_LOST)
        reason = note = None
    sent["status"], sent["lost_reason"], sent["lost_reason_note"] = target, reason, note


def _check_project(db: Session, lead: Lead, sent: dict[str, Any]) -> None:
    project_id = sent.get("project_id", lead.project_id)
    if "project_id" not in sent or project_id == lead.project_id:
        sent.pop("project_id", None)
        return
    if project_id is not None and project_queries.project_ref(db, project_id) is None:
        raise _field(422, "project_id", NO_PROJECT)
    if lead.configuration_id is not None and (
        project_id is None
        or not project_queries.configuration_in_project(db, lead.configuration_id, project_id)
    ):
        sent["configuration_id"] = None


def update_lead(db: Session, staff: Staff, lead_id: uuid.UUID, body: LeadUpdate) -> None:
    """Apply a PATCH (module rules).

    How it works:
      1. Lock the visible lead (404 otherwise); an erased lead answers 409.
      2. Check the owner, status/reason and project changes.
      3. Apply; write the timeline rows, one audit row with a masked diff, and the events.
         Nothing changed → nothing is written.
    """
    lead = load_lead(db, lead_id, staff, lock=True)  # 1
    if lead.erased_at is not None:
        raise ApiProblem(409, ERASED_LEAD)
    sent = body.model_dump(exclude_unset=True)
    _check_owner(db, staff, lead, sent)  # 2
    _check_status(lead, sent)
    _check_project(db, lead, sent)
    before, old_status, old_owner = effects.audit_view(lead), lead.status, lead.owner_user_id
    old_text = {"email": lead.email, "lost_reason_note": lead.lost_reason_note}
    for key, value in sent.items():  # 3
        setattr(lead, key, value)
    now = utcnow()
    if lead.owner_user_id != old_owner:
        lead.assigned_at = now if lead.owner_user_id else None
    db.flush()
    after = effects.audit_view(lead)
    diff = effects.masked_diff(
        before,
        after,
        raw_changed=[key for key, value in old_text.items() if getattr(lead, key) != value],
    )
    if not diff:
        db.rollback()
        return
    _timeline(db, staff, lead, diff, old_status, old_owner, now)
    effects.record(
        db,
        action="lead.updated",
        lead_id=lead.id,
        actor_id=staff.user_id,
        ip=staff.ip,
        changes=diff,
    )
    if lead.status != old_status:
        effects.status_changed(db, lead, old_status, staff.user_id)
    if lead.owner_user_id != old_owner:
        effects.assigned(db, lead, old_owner, staff.user_id)
    db.commit()


def _timeline(
    db: Session,
    staff: Staff,
    lead: Lead,
    diff: dict[str, Any],
    old_status: str,
    old_owner: uuid.UUID | None,
    now: datetime,
) -> None:
    if lead.status != old_status:
        effects.activity(
            db,
            lead,
            "status_changed",
            staff.user_id,
            now,
            **{"from": old_status, "to": lead.status},
            direction=_direction(old_status, lead.status),
            lost_reason=lead.lost_reason,
            # COMPLIANCE: staff's free text; erasure replaces it (effects.PERSONAL_ACTIVITY_KEYS).
            lost_reason_note=lead.lost_reason_note,
        )
    elif reason_fields := sorted({"lost_reason", "lost_reason_note"} & set(diff)):
        effects.activity(db, lead, "details_changed", staff.user_id, now, fields=reason_fields)
    if lead.owner_user_id != old_owner:
        effects.activity(
            db,
            lead,
            "assigned",
            staff.user_id,
            now,
            from_user_id=old_owner,
            to_user_id=lead.owner_user_id,
        )
    if "is_spam" in diff:
        effects.activity(db, lead, "spam_marked", staff.user_id, now, is_spam=lead.is_spam)
    details = sorted({"email", "preferred_bhk", "budget_max_inr", "project_id"} & set(diff))
    if details:
        effects.activity(db, lead, "details_changed", staff.user_id, now, fields=details)


def set_read(db: Session, staff: Staff, lead_id: uuid.UUID, *, read: bool) -> None:
    """Mark read (first open is on the timeline) or unread. No audit row: WHY, it is a
    display flag; who opened which lead is on the lead's own timeline instead."""
    lead = load_lead(db, lead_id, staff, lock=True)
    if read == (lead.read_at is not None):
        return
    lead.read_at = utcnow() if read else None
    effects.activity(db, lead, "read" if read else "unread", staff.user_id)
    db.commit()


def add_note(db: Session, staff: Staff, lead_id: uuid.UUID, body: str) -> LeadNote:
    lead = load_lead(db, lead_id, staff, lock=True)
    if lead.erased_at is not None:
        raise ApiProblem(409, ERASED_LEAD)
    note = LeadNote(lead_id=lead.id, author_user_id=staff.user_id, body=body)
    db.add(note)
    db.flush()
    effects.activity(db, lead, "note_added", staff.user_id, note_id=note.id)
    effects.record(
        db,
        action="lead.note_added",
        lead_id=lead.id,
        actor_id=staff.user_id,
        ip=staff.ip,
        changes={"note_id": [None, str(note.id)], "characters": [None, len(body)]},
    )
    db.commit()
    db.refresh(note)
    return note


# --- Manual leads ------------------------------------------------------------------------------


def _manual_owner(db: Session, staff: Staff, sent: dict[str, Any]) -> uuid.UUID | None:
    """Left out: the person typing it in. Anyone else, or null (the inbox): leads.assign."""
    if "owner_user_id" not in sent or sent["owner_user_id"] == staff.user_id:
        return staff.user_id
    if not staff.can("leads.assign"):
        raise ApiProblem(403, NEEDS_ASSIGN)
    owner: uuid.UUID | None = sent["owner_user_id"]
    refusal = routing.owner_refusal(db, owner) if owner is not None else None
    if refusal is not None:
        raise _field(422, "owner_user_id", refusal)
    return owner


def create_manual_lead(db: Session, staff: Staff, body: LeadManualCreate) -> Lead:
    """A walk-in or phone enquiry. Consent is staff's note (no text was shown on a page).

    The duplicate check applies as for public forms, but only against leads the creator can
    open (without leads.read_all: their own), so it never reveals someone else's lead.
    `lead.created` carries `alert: false`
    (whoever typed it in already knows); a lead given to someone else also emits
    `lead.assigned`, so the new owner hears about it.
    """
    try:
        phone = normalise_phone(body.phone).e164
    except PhoneError as exc:
        raise _field(422, "phone", str(exc)) from exc
    project = None
    if body.project_id is not None:
        project = project_queries.project_ref(db, body.project_id)
        if project is None:
            raise _field(422, "project_id", NO_PROJECT)
    owner = _manual_owner(db, staff, body.model_dump(exclude_unset=True))
    now = utcnow()
    creation.lock_phone(db, phone)
    # SECURITY: link only to a lead the person typing this in can open (creation.py).
    original = creation.find_original(
        db, phone, body.project_id, now, only_owner=owner_filter(staff)
    )
    lead = Lead(
        name=body.name,
        phone_e164=phone,
        email=body.email,
        message=body.message,
        project_id=body.project_id,
        source=body.source,
        status="new",
        owner_user_id=owner,
        assigned_at=now if owner else None,
        read_at=now,  # WHY: the person who typed it in has read it
        duplicate_of_id=original.id if original else None,
    )
    creation.insert_with_reference(db, lead)
    creation.add_consent(db, lead, "lead_form", now, note=body.consent_note)
    creation.record_created(db, lead, original, staff.user_id, now, "manual")
    effects.record(
        db,
        action="lead.created",
        lead_id=lead.id,
        actor_id=staff.user_id,
        ip=staff.ip,
        changes={key: [None, value] for key, value in effects.audit_view(lead).items()}
        | {"manual": [None, True]},
    )
    effects.lead_created(
        db,
        lead,
        intent="manual",
        alert=False,
        marketing_consent=False,
        project_slug=project.slug if project else None,
        actor_id=staff.user_id,
    )
    if owner is not None and owner != staff.user_id:
        effects.assigned(db, lead, None, staff.user_id)
    db.commit()
    return lead
