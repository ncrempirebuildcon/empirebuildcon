"""Erasing a lead's personal data: on a person's request (`leads.erase`, super-admin) and by the
daily retention clean-up for leads with no activity for years (SECURITY.md §8).

Collaborators: routes.py (DELETE /admin/leads/{id}), integrations/outbox_drain.cleanup (daily),
effects.py (timeline, audit, event scrubbing), site_settings `privacy.lead_retention_years`.
Implements: ARCHITECTURE §6 (leads are never hard-deleted; erasure replaces personal fields with
a stub and logs it), SECURITY.md §8 (erasure, retention), DPDP.

What a request erases (DELETE /admin/leads/{id}): the lead and its whole duplicate group (the
lead it repeats and every lead that repeats it, both ways, until nothing new is found); with
`scope=person`, also every other lead with the same phone number. Leads already erased are
skipped. Each erased lead gets its own audit row with the scope, the lead the request was made
on, and how many leads the request erased.

COMPLIANCE: what is replaced or removed for each lead, in one transaction:
  - lead: name and phone → "[erased]"; the lost-reason note (staff's words) → "[erased]";
    email, message, page URL, referrer, preferred contact time, UTM term and content (both
    typed by people, often personal), the five click ids and the IP hash → empty;
  - every note's text → "[erased]"; every site visit's notes → empty;
  - consent rows: the page URL → empty and staff's consent note → "[erased]";
  - timeline: the free text in `data` (effects.PERSONAL_ACTIVITY_KEYS) → "[erased]";
  - the payload of every outbox event of this lead that carried personal data (lead.created,
    lead.status_changed with a note), delivered or not → a stub with the lead id and reference.
What stays, so reports and the proof of consent still work: the reference, stage and reason
code, source, UTM source, medium and campaign, project and configuration, BHK and budget, owner,
every timestamp, the rest of the timeline, the consent text id, version, label and time, and
the audit trail. Audit rows never hold personal text (effects.audit_view), and they are never
edited (platform/models.AuditLog INVARIANT), so they need no scrubbing. An erasure can't be
undone. Changing this list needs owner approval.
INVARIANT: the lead row itself is never deleted (tests/test_leads_erasure.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Final, Literal

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session

from empire_api.leads import effects
from empire_api.leads.access import Staff, load_lead
from empire_api.leads.models import Lead, LeadConsent, LeadNote, SiteVisit
from empire_api.leads.vocab import ERASED, ErasureScope
from empire_api.logs import get_logger
from empire_api.site_settings.defaults import DEFAULT_SETTINGS, read_group
from empire_api.timeutil import utcnow

Reason = Literal["request", "retention"]
CLEARED_FIELDS: Final = (
    "email",
    "message",
    "page_url",
    "referrer",
    "preferred_contact_time",
    "utm_term",
    "utm_content",
    "gclid",
    "gbraid",
    "wbraid",
    "fbclid",
    "msclkid",
    "ip_hash",
)
STUBBED_FIELDS: Final = ("name", "phone_e164")
# Stubbed only when set (a null note stays null; the CHECK keeps notes on lost leads only).
STUBBED_IF_SET: Final = ("lost_reason_note",)
# How many rounds of "repeats / is repeated by" a duplicate group is followed (each lead points
# at its group's first lead, so one round is normal; the cap only guards against bad data).
GROUP_ROUNDS: Final = 10
# PERF: the daily clean-up anonymises at most this many leads per run; the rest wait a day.
RETENTION_BATCH: Final = 500
MIN_RETENTION_YEARS: Final = 1
DEFAULT_RETENTION_YEARS: Final[int] = DEFAULT_SETTINGS["privacy"]["lead_retention_years"]

log = get_logger(__name__)


def _erase(
    db: Session,
    lead: Lead,
    *,
    reason: Reason,
    actor_id: uuid.UUID | None,
    ip: str | None,
    now: datetime,
    request: dict[str, object] | None = None,
) -> None:
    """Replace the personal data of one locked lead (module header). Caller commits."""
    for field in STUBBED_FIELDS:
        setattr(lead, field, ERASED)
    for field in STUBBED_IF_SET:
        if getattr(lead, field) is not None:
            setattr(lead, field, ERASED)
    for field in CLEARED_FIELDS:
        setattr(lead, field, None)
    lead.erased_at = now
    notes = db.execute(update(LeadNote).where(LeadNote.lead_id == lead.id).values(body=ERASED))
    visits = db.execute(update(SiteVisit).where(SiteVisit.lead_id == lead.id).values(notes=None))
    db.execute(update(LeadConsent).where(LeadConsent.lead_id == lead.id).values(page_url=None))
    db.execute(
        update(LeadConsent)
        .where(LeadConsent.lead_id == lead.id, LeadConsent.consent_note.is_not(None))
        .values(consent_note=ERASED)
    )
    timeline = effects.scrub_activity(db, lead)
    events = effects.scrub_events(db, lead)
    effects.activity(db, lead, "erased", actor_id, now, reason=reason, **(request or {}))
    effects.record(
        db,
        action="lead.erased" if reason == "request" else "lead.anonymised",
        lead_id=lead.id,
        actor_id=actor_id,
        ip=ip,
        changes={
            "erased": [False, True],
            "reason": [None, reason],
            "fields": [None, [*STUBBED_FIELDS, *STUBBED_IF_SET, *CLEARED_FIELDS]],
            "notes": [None, int(getattr(notes, "rowcount", 0) or 0)],
            "site_visits": [None, int(getattr(visits, "rowcount", 0) or 0)],
            "timeline_rows_scrubbed": [None, timeline],
            "events_scrubbed": [None, events],
        }
        | {key: [None, value] for key, value in (request or {}).items()},
    )


def _group_ids(db: Session, lead: Lead) -> set[uuid.UUID]:
    """The lead's duplicate group: follow `duplicate_of` both ways until nothing new appears."""
    found = {lead.id}
    for _round in range(GROUP_ROUNDS):
        rows = db.execute(
            select(Lead.id, Lead.duplicate_of_id).where(
                or_(Lead.id.in_(found), Lead.duplicate_of_id.in_(found))
            )
        ).all()
        grown = found | {row[0] for row in rows} | {row[1] for row in rows if row[1]}
        if grown == found:
            break
        found = grown
    return found


def _targets(db: Session, lead: Lead, scope: ErasureScope) -> list[Lead]:
    """Every lead the request erases (module header), locked, in id order (no deadlocks)."""
    ids = _group_ids(db, lead)
    if scope == "person" and lead.erased_at is None:
        same_phone = db.scalars(select(Lead.id).where(Lead.phone_e164 == lead.phone_e164))
        ids |= set(same_phone)
    return list(
        db.scalars(
            select(Lead)
            .where(Lead.id.in_(ids))
            .order_by(Lead.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )


def erase_on_request(
    db: Session, staff: Staff, lead_id: uuid.UUID, scope: ErasureScope = "group"
) -> int:
    """DELETE /admin/leads/{id}: erase the lead's group (or the person's every lead) now.

    Leads already erased are skipped, so a retry changes nothing. Returns how many were erased.
    """
    lead = load_lead(db, lead_id, staff, lock=True)
    targets = [row for row in _targets(db, lead, scope) if row.erased_at is None]
    now = utcnow()
    request: dict[str, object] = {
        "scope": scope,
        "requested_for": str(lead.id),
        "leads_in_request": len(targets),
    }
    for row in targets:
        _erase(
            db,
            row,
            reason="request",
            actor_id=staff.user_id,
            ip=staff.ip,
            now=now,
            request=request,
        )
    db.commit()
    log.info("lead_erased", lead_id=str(lead.id), scope=scope, count=len(targets))
    return len(targets)


def years_before(moment: datetime, years: int) -> datetime:
    """The same day and time `years` earlier (29 February → 28 February)."""
    try:
        return moment.replace(year=moment.year - years)
    except ValueError:
        return moment.replace(year=moment.year - years, day=28)


def retention_years(db: Session) -> int:
    """The `privacy.lead_retention_years` setting, never below one year (else the default)."""
    value = read_group(db, "privacy").get("lead_retention_years")
    if isinstance(value, int) and not isinstance(value, bool) and value >= MIN_RETENTION_YEARS:
        return value
    log.warning("lead_retention_setting_invalid")
    return DEFAULT_RETENTION_YEARS


def anonymise_inactive(db: Session, now: datetime | None = None) -> int:
    """Erase leads with no activity for `retention_years` (SECURITY.md §8). Caller commits.

    WHY `last_activity_at`: it moves on work only (a stage change, a note, a visit, a new
    enquiry from the same person), not on reads or exports, so browsing the inbox doesn't keep
    old leads alive. SKIP LOCKED: a lead being edited right now waits for tomorrow's run.
    """
    now = now or utcnow()
    cutoff = years_before(now, retention_years(db))
    leads = db.scalars(
        select(Lead)
        .where(Lead.erased_at.is_(None), Lead.last_activity_at < cutoff)
        .order_by(Lead.last_activity_at, Lead.id)
        .limit(RETENTION_BATCH)
        .with_for_update(skip_locked=True)
    ).all()
    for lead in leads:
        _erase(db, lead, reason="retention", actor_id=None, ip=None, now=now)
    if leads:
        log.info("leads_anonymised", count=len(leads))
    return len(leads)
