"""Tables of the leads module: `lead`, `lead_consent`, `lead_note`, `lead_activity` and
`site_visit`.

Collaborators: migrations/versions/0004_leads.py creates exactly these tables (tests/
test_migrations.py fails on any drift); intake.py, service.py, visits.py, erasure.py and seed.py
are the only writers.
Implements: ARCHITECTURE §6 (UUID v7, timestamptz, whole rupees, the four named lead indexes,
leads are never hard-deleted), §8, SECURITY.md §8 (salted IP hash only), D-015 (`is_sample`).

INVARIANT: every lead has exactly one `lead_form` consent row, written in the same transaction
as the lead (intake.py, service.create_manual_lead, seed.py); tests/test_leads_intake.py names
this invariant. A lead may also have one `marketing` row, never assumed.
INVARIANT: a lost lead has a reason and no other lead does (`ck_lead_lost_has_reason`).
INVARIANT: a confirmed visit has a time (`ck_site_visit_confirmed_has_time`).
COMPLIANCE: leads are never deleted (DPDP erasure replaces personal fields with a stub,
erasure.py). That is why project and lead foreign keys are RESTRICT, and why children cascade
only for completeness.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql
from sqlalchemy.orm import Mapped, mapped_column

from empire_api.db import Base, created_at_column, uuid_pk
from empire_api.leads.vocab import (
    ACTIVITY_KINDS,
    LANGUAGES,
    LEAD_CONSENT_KINDS,
    LEAD_SOURCES,
    LEAD_STATUSES,
    LOST_REASONS,
    VISIT_SLOTS,
    VISIT_STATUSES,
)
from empire_api.projects.vocab import check_in


class Lead(Base):
    """One enquiry (contract schema Lead). Personal fields: name, phone, email, message,
    page_url, referrer, click ids and ip_hash; erasure.py lists what it replaces."""

    __tablename__ = "lead"

    id: Mapped[uuid.UUID] = uuid_pk()
    reference: Mapped[str] = mapped_column(String(9), unique=True)
    name: Mapped[str] = mapped_column(String(80))
    phone_e164: Mapped[str] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(200))
    message: Mapped[str | None] = mapped_column(Text)
    # WHY RESTRICT (the default): a project with leads can't be deleted, only archived
    # (projects/service.delete_project answers 409 first; ARCHITECTURE §6).
    project_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("project.id"), index=True)
    # WHY SET NULL: removing a configuration is ordinary catalogue work; the lead keeps its
    # project and loses only the plan it clicked.
    configuration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("configuration.id", ondelete="SET NULL")
    )
    source: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(12), server_default=sql("'new'"))
    lost_reason: Mapped[str | None] = mapped_column(String(20))
    # Staff's own words when the code isn't enough (required for `other`); erased with the lead.
    lost_reason_note: Mapped[str | None] = mapped_column(String(200))
    owner_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    assigned_at: Mapped[datetime | None] = mapped_column()
    read_at: Mapped[datetime | None] = mapped_column()
    page_url: Mapped[str | None] = mapped_column(String(1000))
    referrer: Mapped[str | None] = mapped_column(String(1000))
    utm_source: Mapped[str | None] = mapped_column(String(200))
    utm_medium: Mapped[str | None] = mapped_column(String(200))
    utm_campaign: Mapped[str | None] = mapped_column(String(200))
    utm_term: Mapped[str | None] = mapped_column(String(200))
    utm_content: Mapped[str | None] = mapped_column(String(200))
    gclid: Mapped[str | None] = mapped_column(String(500))
    gbraid: Mapped[str | None] = mapped_column(String(500))
    wbraid: Mapped[str | None] = mapped_column(String(500))
    fbclid: Mapped[str | None] = mapped_column(String(500))
    msclkid: Mapped[str | None] = mapped_column(String(500))
    preferred_bhk: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    budget_max_inr: Mapped[int | None] = mapped_column(BigInteger)
    preferred_contact_time: Mapped[str | None] = mapped_column(String(60))
    language: Mapped[str] = mapped_column(String(2), server_default=sql("'en'"))
    # SECURITY.md §8: salted, keyed hash of the network (platform/crypto.hash_ip of network_key:
    # an IPv4 address or an IPv6 /64), never the address itself.
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    is_spam: Mapped[bool] = mapped_column(server_default=sql("false"))
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead.id", ondelete="SET NULL")
    )
    erased_at: Mapped[datetime | None] = mapped_column()
    # Work on the lead (not reads or exports); the retention clean-up counts from here.
    last_activity_at: Mapped[datetime] = created_at_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        # The four indexes ARCHITECTURE §6 names: the inbox, its status tabs, "mine", and the
        # duplicate check / phone search.
        Index("ix_lead_created_at", sql("created_at DESC")),
        Index("ix_lead_status_created_at", "status", sql("created_at DESC")),
        Index("ix_lead_owner_user_id_created_at", "owner_user_id", sql("created_at DESC")),
        Index("ix_lead_phone_e164", "phone_e164"),
        CheckConstraint(check_in("source", LEAD_SOURCES), name="source_valid"),
        CheckConstraint(check_in("status", LEAD_STATUSES), name="status_valid"),
        CheckConstraint(check_in("language", LANGUAGES), name="language_valid"),
        CheckConstraint("(status = 'lost') = (lost_reason IS NOT NULL)", name="lost_has_reason"),
        CheckConstraint(check_in("lost_reason", LOST_REASONS), name="lost_reason_valid"),
        CheckConstraint(
            "lost_reason_note IS NULL OR status = 'lost'", name="lost_reason_note_only_lost"
        ),
        CheckConstraint("COALESCE(budget_max_inr, 0) >= 0", name="budget_not_negative"),
        CheckConstraint(
            "preferred_bhk BETWEEN 0.5 AND 20 AND mod(preferred_bhk * 2, 1) = 0",
            name="preferred_bhk_half_steps",
        ),
        CheckConstraint("duplicate_of_id <> id", name="not_own_duplicate"),
    )


class LeadConsent(Base):
    """What the person agreed to, with the exact words shown (contract: Lead.consent).

    Public forms store the text id, version and checkbox label they showed; manual leads store
    staff's `consent_note` ("Verbal on phone call") instead.
    """

    __tablename__ = "lead_consent"

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(16))
    # WHY RESTRICT: a text someone agreed to can never disappear (texts are never deleted).
    consent_text_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("consent_text.id"), index=True
    )
    version: Mapped[int | None] = mapped_column()
    accepted_at: Mapped[datetime] = mapped_column()
    page_url: Mapped[str | None] = mapped_column(String(1000))
    checkbox_label: Mapped[str | None] = mapped_column(String(300))
    consent_note: Mapped[str | None] = mapped_column(String(500))

    __table_args__ = (
        # Also the index for the lead_id foreign key (leading column).
        UniqueConstraint("lead_id", "kind"),
        CheckConstraint(check_in("kind", LEAD_CONSENT_KINDS), name="kind_valid"),
        CheckConstraint("(consent_text_id IS NULL) = (version IS NULL)", name="text_has_version"),
        CheckConstraint(
            "consent_text_id IS NOT NULL OR consent_note IS NOT NULL", name="text_or_note"
        ),
    )


class LeadNote(Base):
    __tablename__ = "lead_note"

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id", ondelete="CASCADE"))
    # WHY no foreign key: authorship outlives any staff account row (like project.created_by).
    author_user_id: Mapped[uuid.UUID | None] = mapped_column()
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (Index("ix_lead_note_lead_id_created_at", "lead_id", "created_at"),)


class LeadActivity(Base):
    """One line of a lead's timeline.

    COMPLIANCE: `data` holds ids, enums and timestamps, plus one piece of staff free text: the
    `lost_reason_note` of a stage change. Never a name, number, email, message or note body.
    Erasure replaces every key in effects.PERSONAL_ACTIVITY_KEYS with "[erased]" (tests scan
    the whole database for the person's details afterwards).
    """

    __tablename__ = "lead_activity"

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("lead.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(20))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column()
    data: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        Index("ix_lead_activity_lead_id_created_at", "lead_id", "created_at"),
        CheckConstraint(check_in("kind", ACTIVITY_KINDS), name="kind_valid"),
    )


class SiteVisit(Base):
    """A visit request: the buyer's preferred day and time of day; sales confirms the exact
    time by phone and records it here (D-016)."""

    __tablename__ = "site_visit"

    id: Mapped[uuid.UUID] = uuid_pk()
    lead_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("lead.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id"), index=True)
    preferred_date: Mapped[date] = mapped_column(index=True)
    preferred_slot: Mapped[str] = mapped_column(String(10))
    confirmed_for: Mapped[datetime | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(12), server_default=sql("'requested'"))
    handled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("app_user.id", ondelete="SET NULL")
    )
    notes: Mapped[str | None] = mapped_column(Text)
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint(check_in("status", VISIT_STATUSES), name="status_valid"),
        CheckConstraint(check_in("preferred_slot", VISIT_SLOTS), name="preferred_slot_valid"),
        CheckConstraint(
            "status <> 'confirmed' OR confirmed_for IS NOT NULL", name="confirmed_has_time"
        ),
    )
