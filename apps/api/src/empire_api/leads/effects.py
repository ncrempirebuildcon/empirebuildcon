"""What every change to a lead leaves behind: a timeline row (`lead_activity`), an audit row and
an outbox event, written into the caller's transaction.

Collaborators: intake.py, service.py, visits.py, erasure.py, export.py; platform/audit.py and
platform/outbox.py.
Implements: ARCHITECTURE §8 ("every change writes a lead_activity row"), §9 (lead.* and
site_visit.* events), §11 (audit); SECURITY.md §8 (masked phones, no form bodies in audit).

INVARIANT: helpers only add to the session; the service commits once, so the change, its
activity, audit row and event are saved together or not at all.
COMPLIANCE: personal data (name, phone, email, message, and the browser's User-Agent when the
visitor gave marketing consent, for ad platforms, D-057) goes ONLY into `lead.created`, and
staff's lost-reason note into `lead.status_changed`; both are flagged `contains_personal_data`
so they reach only webhooks allowed to receive it (ARCHITECTURE §9), and erasure scrubs them.
Audit diffs never hold personal text; activity data holds the lost-reason note only
(PERSONAL_ACTIVITY_KEYS); every other event carries ids, stages and times.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, update
from sqlalchemy.orm import Session

from empire_api.leads.models import Lead, LeadActivity, SiteVisit
from empire_api.leads.vocab import ERASED
from empire_api.logs import mask_phone
from empire_api.platform import audit, outbox
from empire_api.platform.models import OutboxEvent
from empire_api.projects.common import jsonable
from empire_api.timeutil import utcnow

# Timeline keys that may hold free text; erasure replaces them (scrub_activity).
PERSONAL_ACTIVITY_KEYS: Final = ("lost_reason_note",)
# Activity kinds that are work on the lead. Reads, unreads and exports are not: otherwise
# browsing or a yearly export would keep every lead "active" and defeat the retention rule.
_NOT_WORK: Final = frozenset({"read", "unread", "exported", "alert_sent", "webhook_sent"})
HIDDEN: Final = "[hidden]"


def activity(
    db: Session,
    lead: Lead,
    kind: str,
    actor_id: uuid.UUID | None,
    now: datetime | None = None,
    **data: Any,
) -> LeadActivity:
    """One timeline row. COMPLIANCE: pass ids, stages and times only (models.LeadActivity)."""
    when = now or utcnow()
    row = LeadActivity(
        lead_id=lead.id, kind=kind, actor_user_id=actor_id, data=jsonable(data), created_at=when
    )
    db.add(row)
    if kind not in _NOT_WORK:
        lead.last_activity_at = when
    return row


def record(
    db: Session,
    *,
    action: str,
    lead_id: uuid.UUID,
    actor_id: uuid.UUID | None,
    ip: str | None,
    changes: dict[str, Any],
    entity_type: str = "lead",
) -> None:
    """An audit row. Callers build `changes` with `audit_view` / `masked_diff`, never raw rows."""
    audit.record(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=lead_id,
        actor_id=actor_id,
        ip=ip,
        changes=jsonable(changes),
    )


def audit_view(lead: Lead) -> dict[str, Any]:
    """The lead as audit diffs may show it. SECURITY.md §8: the phone is masked, and the name,
    email, message and lost-reason note are never copied into the audit log (only whether they
    are set). WHY: audit rows are never edited (platform/models.AuditLog INVARIANT), so personal
    text must not reach them in the first place; erasure then has nothing to chase there."""
    return {
        "reference": lead.reference,
        "phone": mask_phone(lead.phone_e164),
        "status": lead.status,
        "lost_reason": lead.lost_reason,
        "lost_reason_note": HIDDEN if lead.lost_reason_note else None,
        "owner_user_id": lead.owner_user_id,
        "project_id": lead.project_id,
        "source": lead.source,
        "is_spam": lead.is_spam,
        "preferred_bhk": lead.preferred_bhk,
        "budget_max_inr": lead.budget_max_inr,
        "email": HIDDEN if lead.email else None,
    }


def masked_diff(
    before: dict[str, Any], after: dict[str, Any], *, raw_changed: Iterable[str] = ()
) -> dict[str, list[Any]]:
    """Diff of two `audit_view`s. `raw_changed` names hidden fields whose text changed while
    staying set (e.g. one email for another): they show as [hidden] → [hidden]."""
    diff = audit.diff(jsonable(before), jsonable(after))
    for key in raw_changed:
        diff.setdefault(key, [HIDDEN, HIDDEN])
    return diff


# --- Events -----------------------------------------------------------------------------------


def lead_ref(lead: Lead) -> dict[str, Any]:
    return {"lead_id": str(lead.id), "reference": lead.reference}


def lead_created(
    db: Session,
    lead: Lead,
    *,
    intent: str,
    alert: bool,
    marketing_consent: bool,
    project_slug: str | None,
    actor_id: uuid.UUID | None = None,
    user_agent: str | None = None,
) -> None:
    """`lead.created`, the only event with personal data (COMPLIANCE in the module header).

    `alert` is false for duplicates (same phone and project within 24 h), manual leads and
    samples: the part 5 email handler must skip those (integrations/handlers.py TODO).
    `marketing_consent` gates ad-platform conversions (ARCHITECTURE §17).
    """
    outbox.emit(
        db,
        type_="lead.created",
        aggregate_type="lead",
        aggregate_id=lead.id,
        actor_id=actor_id,
        contains_personal_data=True,
        data=jsonable(
            {
                **lead_ref(lead),
                "intent": intent,
                "alert": alert,
                "source": lead.source,
                "project_id": lead.project_id,
                "project_slug": project_slug,
                "configuration_id": lead.configuration_id,
                "owner_user_id": lead.owner_user_id,
                "duplicate_of": lead.duplicate_of_id,
                "marketing_consent": marketing_consent,
                "is_sample": lead.is_sample,
                "name": lead.name,
                "phone_e164": lead.phone_e164,
                "email": lead.email,
                "message": lead.message,
                "language": lead.language,
                # Public forms with marketing consent only; for the Meta Conversions API (D-057).
                "user_agent": (user_agent or "")[:500] or None,
                "utm": {
                    "source": lead.utm_source,
                    "medium": lead.utm_medium,
                    "campaign": lead.utm_campaign,
                    "term": lead.utm_term,
                    "content": lead.utm_content,
                },
            }
        ),
    )


def status_changed(
    db: Session, lead: Lead, before: str, actor_id: uuid.UUID | None, **extra: Any
) -> None:
    """`lead.status_changed`. A lost lead's reason code goes with it, and staff's note when
    there is one; COMPLIANCE: the note is free text, so such an event is flagged as personal
    data (webhooks allowed to receive it only) and erasure scrubs it (`scrub_events`)."""
    data: dict[str, Any] = {**lead_ref(lead), "from": before, "to": lead.status, **extra}
    note = lead.lost_reason_note if lead.status == "lost" else None
    if lead.status == "lost":
        data |= {"lost_reason": lead.lost_reason, "lost_reason_note": note}
    outbox.emit(
        db,
        type_="lead.status_changed",
        aggregate_type="lead",
        aggregate_id=lead.id,
        actor_id=actor_id,
        contains_personal_data=note is not None,
        data=jsonable(data),
    )


def assigned(db: Session, lead: Lead, before: uuid.UUID | None, actor_id: uuid.UUID | None) -> None:
    """`lead.assigned`: the part 5 handler emails the new owner."""
    outbox.emit(
        db,
        type_="lead.assigned",
        aggregate_type="lead",
        aggregate_id=lead.id,
        actor_id=actor_id,
        data=jsonable({**lead_ref(lead), "from_user_id": before, "to_user_id": lead.owner_user_id}),
    )


def visit_event(
    db: Session, visit: SiteVisit, type_: str, actor_id: uuid.UUID | None, **extra: Any
) -> None:
    """`site_visit.requested` / `site_visit.updated`: ids, day, slot and status only."""
    outbox.emit(
        db,
        type_=type_,
        aggregate_type="site_visit",
        aggregate_id=visit.id,
        actor_id=actor_id,
        data=jsonable(
            {
                "visit_id": visit.id,
                "lead_id": visit.lead_id,
                "project_id": visit.project_id,
                "status": visit.status,
                "preferred_date": visit.preferred_date,
                "preferred_slot": visit.preferred_slot,
                "confirmed_for": visit.confirmed_for,
                **extra,
            }
        ),
    )


def scrub_activity(db: Session, lead: Lead) -> int:
    """COMPLIANCE (erasure): replace the free text in this lead's timeline (the keys in
    PERSONAL_ACTIVITY_KEYS) with "[erased]". Returns how many timeline rows changed."""
    changed = 0
    for key in PERSONAL_ACTIVITY_KEYS:
        result = db.execute(
            update(LeadActivity)
            .where(
                LeadActivity.lead_id == lead.id,
                LeadActivity.data[key].astext.is_not(None),
            )
            .values(data=LeadActivity.data.op("||")(func.jsonb_build_object(key, ERASED)))
        )
        changed += int(getattr(result, "rowcount", 0) or 0)
    return changed


def scrub_events(db: Session, lead: Lead) -> int:
    """COMPLIANCE (erasure): replace the payload of this lead's personal-data events, delivered
    or not, with a stub. Returns how many events were scrubbed."""
    result = db.execute(
        update(OutboxEvent)
        .where(
            OutboxEvent.aggregate_type == "lead",
            OutboxEvent.aggregate_id == str(lead.id),
            OutboxEvent.contains_personal_data.is_(True),
        )
        .values(payload={**lead_ref(lead), "erased": True})
    )
    return int(getattr(result, "rowcount", 0) or 0)
