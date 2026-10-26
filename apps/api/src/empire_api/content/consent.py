"""Consent texts: list versions, write a new draft version, make a version current, find the
current text, and seed the draft wording in development and tests.

Collaborators: content/routes.py (HTTP), leads/intake.py (checks every enquiry against the
current text), dashboard/service.py (the "still a draft" task), cli.py (`empire-api seed`).
Implements: ARCHITECTURE §8 (consent), §9 (`consent_text.published`), SECURITY.md §8, D-017.

Rules:
  - A new text is a draft: the next version number of its kind, not published, not current.
  - Publishing makes it the one current text of its kind (the previous one stops being current,
    in the same transaction). A version that was published before can be made current again.
  - A text is never edited; a change is a new version (models.py COMPLIANCE).
  - In production, a text still carrying the draft mark can't be published (D-017: the owner
    approves the wording first; removing the mark in a new version is that approval).
  - Seeds: development and test only. Production starts with no text, so public intake answers
    503 until the owner publishes approved wording.

INVARIANT: each write commits once, together with its audit row and event.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Final

from sqlalchemy import func, select, text, update
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content.models import ConsentText
from empire_api.content.vocab import CONSENT_KINDS, DRAFT_MARK, ConsentKind
from empire_api.errors import ApiProblem
from empire_api.platform import audit, outbox
from empire_api.projects.common import Actor
from empire_api.timeutil import utcnow

NO_TEXT: Final = "No consent text with this id."
STILL_DRAFT: Final = (
    "This text still says it is a draft. Write a new version without the draft mark once the "
    "owner has approved the wording, then publish that."
)

# D-017: Claude's draft wording, in plain language, marked as a draft until the owner approves.
# Not legal advice; the owner accepted that risk (D-017).
DRAFT_TEXTS: Final[dict[str, tuple[str, str]]] = {
    "lead_form": (
        f"{DRAFT_MARK} When you send this form, Empire will use your name, phone number and any "
        "other details you give only to answer this enquiry: to call you, or to message you by "
        "SMS or WhatsApp, about the project you asked about. We keep a record of the enquiry and "
        "of this consent. You can ask us at any time to stop contacting you or to delete your "
        "details. Our privacy notice explains how we look after your data.",
        "[DRAFT] Contact me about this enquiry by call, SMS or WhatsApp.",
    ),
    "marketing": (
        f"{DRAFT_MARK} Optional. If you tick this box, Empire may also send you news about new "
        "launches and offers by SMS, WhatsApp or email, and may share a scrambled (hashed) form "
        "of your phone number or email with advertising platforms to measure its adverts. Leave "
        "it unticked and we will only contact you about this enquiry. You can change your mind "
        "at any time by telling us.",
        "[DRAFT] Send me news about new launches and offers (optional).",
    ),
}


def is_draft(row: ConsentText) -> bool:
    """COMPLIANCE (D-017): the wording still says it awaits the owner's approval."""
    return "[draft" in f"{row.body}\n{row.checkbox_label}".lower()


@dataclass(frozen=True)
class KindSummary:
    """One purpose's state for the CMS (part 5): its current text and its versions."""

    kind: str
    current: ConsentText | None
    versions: int
    latest: ConsentText | None


def kinds_summary(db: Session) -> list[KindSummary]:
    """Every purpose (kind), even those with no text yet, in CONSENT_KINDS order."""
    found = []
    for kind in CONSENT_KINDS:
        texts = list_texts(db, kind)
        current = next((t for t in texts if t.is_current), None)
        found.append(
            KindSummary(
                kind=kind, current=current, versions=len(texts), latest=texts[0] if texts else None
            )
        )
    return found


def list_texts(db: Session, kind: ConsentKind | None = None) -> list[ConsentText]:
    """Every version, grouped by kind, newest version first."""
    stmt = select(ConsentText).order_by(ConsentText.kind, ConsentText.version.desc())
    if kind is not None:
        stmt = stmt.where(ConsentText.kind == kind)
    return list(db.scalars(stmt))


def current_text(db: Session, kind: str) -> ConsentText | None:
    """The text a form of this kind must show now, or None (then intake is closed)."""
    return db.scalar(
        select(ConsentText).where(ConsentText.kind == kind, ConsentText.is_current.is_(True))
    )


def _lock_kind(db: Session, kind: str) -> None:
    """WHY: two drafts written at the same moment would both take version N+1; the second would
    hit the unique index. A transaction-level advisory lock per kind serialises them."""
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"consent:{kind}"})


def create_draft(
    db: Session, kind: ConsentKind, body: str, checkbox_label: str, actor: Actor
) -> ConsentText:
    """A new draft version of `kind` (not published, not current)."""
    _lock_kind(db, kind)
    latest = db.scalar(select(func.max(ConsentText.version)).where(ConsentText.kind == kind))
    row = ConsentText(
        kind=kind,
        version=int(latest or 0) + 1,
        body=body,
        checkbox_label=checkbox_label,
        created_by=actor.user_id,
    )
    db.add(row)
    db.flush()
    audit.record(
        db,
        action="consent_text.created",
        entity_type="consent_text",
        entity_id=row.id,
        actor_id=actor.user_id,
        ip=actor.ip,
        changes={"kind": [None, kind], "version": [None, row.version]},
    )
    db.commit()
    return row


def publish(db: Session, text_id: uuid.UUID, actor: Actor) -> ConsentText:
    """Make this version the current text of its kind. Already current: nothing changes.

    How it works:
      1. Lock the kind (advisory) and the row, so two publishes can't both end up current.
      2. In production, refuse a text that still carries the draft mark (D-017).
      3. Clear the previous current text of the kind, then mark this one current; set
         `published_at` and `published_by` on its first publish only. Audit and
         `consent_text.published` commit with it.
    """
    row = db.get(ConsentText, text_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise ApiProblem(404, NO_TEXT)
    _lock_kind(db, row.kind)  # 1
    db.refresh(row)
    if row.is_current:
        return row
    if get_settings().app_env == "production" and is_draft(row):  # 2
        raise ApiProblem(409, STILL_DRAFT)
    previous = current_text(db, row.kind)
    db.execute(  # 3
        update(ConsentText)
        .where(ConsentText.kind == row.kind, ConsentText.is_current.is_(True))
        .values(is_current=False)
    )
    db.flush()
    row.is_current = True
    if row.published_at is None:
        row.published_at = utcnow()
        row.published_by = actor.user_id
    db.flush()
    audit.record(
        db,
        action="consent_text.published",
        entity_type="consent_text",
        entity_id=row.id,
        actor_id=actor.user_id,
        ip=actor.ip,
        changes={
            "is_current": [False, True],
            "replaces_version": [None, previous.version if previous else None],
        },
    )
    outbox.emit(
        db,
        type_="consent_text.published",
        aggregate_type="consent_text",
        aggregate_id=row.id,
        actor_id=actor.user_id,
        data={"kind": row.kind, "version": row.version, "consent_text_id": str(row.id)},
    )
    db.commit()
    db.refresh(row)
    return row


def seed_consent_texts(db: Session) -> int:
    """Development and test only: a current, draft-marked text for each kind in DRAFT_TEXTS that
    has no text yet. Returns how many were added. Caller commits.

    COMPLIANCE: never in staging or production. There the owner publishes approved wording, and
    until then public intake is closed (503), so no lead is collected under unapproved words.
    """
    if get_settings().app_env not in ("development", "test"):
        return 0
    added = 0
    now = utcnow()
    for kind, (body, label) in DRAFT_TEXTS.items():
        if db.scalar(select(ConsentText.id).where(ConsentText.kind == kind).limit(1)):
            continue
        db.add(
            ConsentText(
                kind=kind,
                version=1,
                body=body,
                checkbox_label=label,
                published_at=now,
                is_current=True,
            )
        )
        added += 1
    db.flush()
    return added
