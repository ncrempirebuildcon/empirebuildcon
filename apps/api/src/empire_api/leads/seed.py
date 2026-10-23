"""Sample leads and site visits for development and demos (`empire-api seed --sample`).

Collaborators: cli.py; creation.py (row, reference, consent); projects/media_owners.py (the two
sample projects); content/consent.py (the draft texts, seeded first in development and test).
Implements: D-015 (sample data until real projects arrive), CODE_STYLE §7 (honest seeds).

COMPLIANCE (D-015, AGENTS.md "Honest content"):
  - Every row is `is_sample`, named "Sample Lead N", with an example.com address (RFC 2606
    keeps that domain for examples) and a phone number from +91 00000 000NN. No Indian number
    starts with the trunk prefix 0 (leads/phone.py rule 7), so these can never belong to anyone,
    and the public forms refuse them: a sample can't be confused with, or collide with, a lead.
  - Refused in production, like the sample projects.
  - No outbox events: seeding is not a visitor's enquiry, so nothing may alert sales or reach a
    webhook. The timeline says what happened, with no actor.
Idempotent: a sample lead that already exists (same name, `is_sample`) is skipped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content import consent as consent_texts
from empire_api.leads import creation, effects
from empire_api.leads.models import Lead, SiteVisit
from empire_api.leads.phone import SAMPLE_PREFIX
from empire_api.projects import queries as project_queries
from empire_api.projects.media_owners import sample_project_ids
from empire_api.timeutil import IST, today_ist, utcnow

SAMPLE_NOTE: Final = "Sample data: no real person and no real consent (D-015)."


class SampleLeadsRefusedError(RuntimeError):
    """Sample data is never added in production (D-015)."""


@dataclass(frozen=True)
class SampleLeadsResult:
    added: int
    skipped: int
    visits: int


@dataclass(frozen=True)
class _Sample:
    number: int
    project: int | None  # index into the sample projects; None = general enquiry
    source: str
    status: str
    days_ago: float
    utm: tuple[str, str, str] | None = None
    lost_reason: str | None = None
    marketing: bool = False
    duplicate_of: int | None = None


# Twelve leads across stages, sources and both sample projects (and two general enquiries).
SAMPLES: Final = (
    _Sample(1, 0, "project_form", "new", 0.1, ("google", "cpc", "sample-campaign-a")),
    _Sample(2, 1, "whatsapp", "new", 0.6),
    _Sample(
        3, 0, "brochure", "new", 1.2, ("facebook", "paid", "sample-campaign-b"), marketing=True
    ),
    _Sample(4, None, "contact_form", "contacted", 2.0),
    _Sample(5, 1, "project_form", "contacted", 3.5, ("google", "organic", "")),
    _Sample(6, 0, "campaign", "contacted", 4.0, ("instagram", "paid", "sample-campaign-b")),
    _Sample(7, 0, "site_visit", "site_visit", 5.0, ("google", "cpc", "sample-campaign-a")),
    _Sample(8, 1, "site_visit", "site_visit", 6.5),
    _Sample(9, 0, "project_form", "negotiation", 9.0, ("google", "cpc", "sample-campaign-a")),
    _Sample(10, 1, "phone", "booked", 13.0),
    _Sample(11, None, "manual", "lost", 16.0, lost_reason="bought_elsewhere"),
    _Sample(12, None, "contact_form", "lost", 15.8, lost_reason="duplicate", duplicate_of=11),
)


def sample_phone(number: int) -> str:
    return f"{SAMPLE_PREFIX}{number:05d}"


def _lead(sample: _Sample, projects: list[uuid.UUID], now: datetime) -> Lead:
    created = now - timedelta(days=sample.days_ago)
    phone_number = sample.duplicate_of or sample.number
    source, medium, campaign = sample.utm or (None, None, None)
    return Lead(
        name=f"Sample Lead {sample.number}",
        phone_e164=sample_phone(phone_number),
        email=f"sample.lead.{phone_number}@example.com",
        message="[Sample message: what the buyer asked about]" if sample.number % 3 else None,
        project_id=projects[sample.project] if sample.project is not None else None,
        source=sample.source,
        status=sample.status,
        lost_reason=sample.lost_reason,
        read_at=None if sample.status == "new" else created + timedelta(hours=2),
        page_url=None if sample.source in ("phone", "manual") else "/sample-page",
        utm_source=source,
        utm_medium=medium,
        utm_campaign=campaign or None,
        is_sample=True,
        created_at=created,
        last_activity_at=created,
    )


def _consent(db: Session, lead: Lead, sample: _Sample) -> None:
    """The draft texts when they exist (development, test), else an honest note."""
    text = consent_texts.current_text(db, "lead_form")
    shown = creation.ConsentShown(text, lead.page_url) if text and lead.page_url else None
    creation.add_consent(
        db, lead, "lead_form", lead.created_at, shown, None if shown else SAMPLE_NOTE
    )
    marketing = consent_texts.current_text(db, "marketing") if sample.marketing else None
    if marketing is not None:
        creation.add_consent(
            db, lead, "marketing", lead.created_at, creation.ConsentShown(marketing, lead.page_url)
        )


def _visits(db: Session, by_number: dict[int, Lead]) -> int:
    """Four visits: requested, confirmed, completed and one more request, all `is_sample`."""
    today = today_ist()
    plans = (
        (7, today + timedelta(days=2), "morning", "requested", None),
        (8, today + timedelta(days=1), "afternoon", "confirmed", time(11, 0)),
        (9, today - timedelta(days=3), "morning", "completed", time(10, 30)),
        (1, today + timedelta(days=5), "evening", "requested", None),
    )
    added = 0
    for number, day, slot, status, at in plans:
        lead = by_number.get(number)
        if lead is None or lead.project_id is None:
            continue
        visit = SiteVisit(
            lead_id=lead.id,
            project_id=lead.project_id,
            preferred_date=day,
            preferred_slot=slot,
            status=status,
            confirmed_for=datetime.combine(day, at, tzinfo=IST) if at else None,
            is_sample=True,
        )
        db.add(visit)
        db.flush()
        effects.activity(
            db, lead, "visit_requested", None, lead.created_at, visit_id=visit.id, sample=True
        )
        added += 1
    return added


def seed_sample_leads(db: Session) -> SampleLeadsResult:
    """Add the sample leads and visits (module header). Caller commits.

    Raises:
        SampleLeadsRefusedError: APP_ENV is production.
    """
    if get_settings().app_env == "production":
        raise SampleLeadsRefusedError("Sample data is never added in production (D-015).")
    refs = project_queries.project_refs(db, sample_project_ids(db))
    projects = [ref.id for ref in sorted(refs.values(), key=lambda ref: ref.slug)]
    if len(projects) < 2:
        return SampleLeadsResult(added=0, skipped=len(SAMPLES), visits=0)
    existing = set(
        db.scalars(
            select(Lead.name).where(Lead.is_sample.is_(True), Lead.name.like("Sample Lead %"))
        )
    )
    now = utcnow()
    by_number: dict[int, Lead] = {}
    added = 0
    for sample in SAMPLES:
        if f"Sample Lead {sample.number}" in existing:
            continue
        lead = _lead(sample, projects, now)
        original = by_number.get(sample.duplicate_of) if sample.duplicate_of else None
        lead.duplicate_of_id = original.id if original else None
        creation.insert_with_reference(db, lead)
        _consent(db, lead, sample)
        creation.record_created(db, lead, original, None, lead.created_at, "sample")
        if sample.status != "new":
            effects.activity(
                db,
                lead,
                "status_changed",
                None,
                lead.created_at + timedelta(hours=3),
                **{"from": "new", "to": sample.status},
                direction="forward",
                sample=True,
            )
        by_number[sample.number] = lead
        added += 1
    visits = _visits(db, by_number)
    return SampleLeadsResult(added=added, skipped=len(SAMPLES) - added, visits=visits)
