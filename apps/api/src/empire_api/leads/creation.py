"""Writing a new lead: the row with a unique reference, its consent rows, the duplicate link and
the "created" timeline entry. Shared by public intake, manual leads and the sample seed.

Collaborators: intake.py, service.create_manual_lead, seed.py; reference.py, effects.py.
Implements: ARCHITECTURE §8 (consent stored with the lead; duplicate check), §6 (references).

DO NOT CHANGE: the consent rows are written in the same transaction as the lead (the caller
commits once). Splitting them would allow a lead without a consent record, which breaks DPDP
compliance (CODE_STYLE §2.1 example; INVARIANT in models.py).

How the duplicate check works (ARCHITECTURE §8):
  1. Take a transaction-level advisory lock on the phone number, so two forms from the same
     person a moment apart are checked one after the other (the second sees the first).
  2. Look for the earliest lead with the same phone and the same project (both "no project"
     counts as the same) created in the last 24 hours, ignoring spam and erased leads.
  3. If found, the new lead is still saved, with `duplicate_of_id` naming the original (the
     original's own original when it was itself a duplicate), so nothing the visitor typed is
     lost; the original's timeline gets a `duplicate_linked` line.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from empire_api.content.models import ConsentText
from empire_api.leads import effects
from empire_api.leads.models import Lead, LeadConsent
from empire_api.leads.reference import MAX_ATTEMPTS, new_reference
from empire_api.leads.vocab import DUPLICATE_WINDOW_HOURS
from empire_api.logs import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class ConsentShown:
    """A consent box the visitor ticked, next to this exact text."""

    text: ConsentText
    page_url: str | None


def lock_phone(db: Session, phone_e164: str) -> None:
    """Step 1 of the duplicate check (module header)."""
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"lead-phone:{phone_e164}"}
    )


def find_original(
    db: Session,
    phone_e164: str,
    project_id: uuid.UUID | None,
    now: datetime,
    *,
    only_owner: uuid.UUID | None = None,
) -> Lead | None:
    """Steps 2–3: the lead a new one from this phone and project duplicates, or None.

    `only_owner` limits the search to leads that person owns: a manual lead may only link to a
    lead its creator can open (SECURITY.md §1), so the link never tells them another
    salesperson's lead exists. Public enquiries search every lead (and go to its owner).
    """
    stmt = (
        select(Lead)
        .where(
            Lead.phone_e164 == phone_e164,
            Lead.project_id.is_not_distinct_from(project_id),
            Lead.created_at >= now - timedelta(hours=DUPLICATE_WINDOW_HOURS),
            Lead.is_spam.is_(False),
            Lead.erased_at.is_(None),
        )
        .order_by(Lead.created_at, Lead.id)
        .limit(1)
    )
    if only_owner is not None:
        stmt = stmt.where(Lead.owner_user_id == only_owner)
    earliest = db.scalar(stmt)
    if earliest is None or earliest.duplicate_of_id is None:
        return earliest
    root = db.get(Lead, earliest.duplicate_of_id)
    if root is None or (only_owner is not None and root.owner_user_id != only_owner):
        return earliest
    return root


def insert_with_reference(db: Session, lead: Lead) -> None:
    """Flush the new lead with a fresh EMP-XXXXX reference, drawing again on the rare clash.

    WHY a savepoint per try: the unique index on `reference` refuses a clash at INSERT time;
    rolling back only the savepoint keeps the rest of the transaction intact.
    """
    for _attempt in range(MAX_ATTEMPTS):
        lead.reference = new_reference()
        try:
            with db.begin_nested():
                db.add(lead)
                db.flush()
        except IntegrityError as exc:
            name = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
            if name != "uq_lead_reference":
                raise
            log.warning("lead_reference_clash")
            continue
        return
    raise RuntimeError("Could not draw a free lead reference")


def add_consent(
    db: Session,
    lead: Lead,
    kind: str,
    accepted_at: datetime,
    shown: ConsentShown | None = None,
    note: str | None = None,
) -> LeadConsent:
    """One consent row: the text, version and label shown, or staff's note for manual leads."""
    row = LeadConsent(
        lead_id=lead.id,
        kind=kind,
        consent_text_id=shown.text.id if shown else None,
        version=shown.text.version if shown else None,
        accepted_at=accepted_at,
        page_url=shown.page_url if shown else None,
        checkbox_label=shown.text.checkbox_label if shown else None,
        consent_note=note,
    )
    db.add(row)
    return row


def record_created(
    db: Session,
    lead: Lead,
    original: Lead | None,
    actor_id: uuid.UUID | None,
    now: datetime,
    intent: str,
) -> None:
    """The "created" timeline line, and the link on the original when this is a duplicate."""
    effects.activity(
        db,
        lead,
        "created",
        actor_id,
        now,
        source=lead.source,
        intent=intent,
        owner_user_id=lead.owner_user_id,
        duplicate_of=lead.duplicate_of_id,
    )
    if original is not None:
        effects.activity(
            db,
            original,
            "duplicate_linked",
            actor_id,
            now,
            lead_id=lead.id,
            reference=lead.reference,
            source=lead.source,
        )
