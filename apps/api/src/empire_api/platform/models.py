"""Tables for the shared platform: audit log, outbox events, rate-limit counters.

Implements: ARCHITECTURE §6 (bigint identity for high-volume append tables), §9 (outbox),
§11 (audit log), D-010 (queue and rate limits in PostgreSQL).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, CheckConstraint, Identity, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from empire_api.db import Base, created_at_column
from empire_api.ids import new_id

OUTBOX_STATUSES = ("pending", "processing", "delivered", "dead")


class AuditLog(Base):
    """Who did what to which record, with a before/after diff. Append-only.

    INVARIANT: rows are never updated or deleted by application code (audit board: "can't be
    edited or deleted"). Retention clean-up, if ever added, needs owner approval.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    # WHY: no foreign key. The audit trail must outlive any user row (and erasure requests).
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(index=True)
    action: Mapped[str] = mapped_column(String(80))
    entity_type: Mapped[str] = mapped_column(String(40))
    entity_id: Mapped[str] = mapped_column(String(64))
    changes: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    # Masked network (203.0.113.0/24), never the full address (platform/crypto.py mask_ip).
    ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        Index("ix_audit_log_created_at", text("created_at DESC")),
        Index("ix_audit_log_entity", "entity_type", "entity_id"),
    )


class OutboxEvent(Base):
    """An event written in the same transaction as the change that caused it (ARCHITECTURE §9).

    The worker claims pending rows with FOR UPDATE SKIP LOCKED and delivers them to handlers.
    """

    __tablename__ = "outbox_event"

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    event_id: Mapped[uuid.UUID] = mapped_column(default=new_id, unique=True)
    type: Mapped[str] = mapped_column(String(80))
    aggregate_type: Mapped[str] = mapped_column(String(40))
    aggregate_id: Mapped[str] = mapped_column(String(64))
    payload: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    actor_id: Mapped[uuid.UUID | None] = mapped_column()
    # COMPLIANCE: events carrying personal data go only to webhooks marked "may receive personal
    # data" (ARCHITECTURE §9, DPDP). Writers must set this honestly.
    contains_personal_data: Mapped[bool] = mapped_column(server_default=text("false"))
    occurred_at: Mapped[datetime] = created_at_column()
    status: Mapped[str] = mapped_column(String(16), server_default=text("'pending'"))
    attempts: Mapped[int] = mapped_column(server_default=text("0"))
    available_at: Mapped[datetime] = created_at_column()
    last_error: Mapped[str | None] = mapped_column(Text)
    delivered_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'dead')", name="status_valid"
        ),
        Index("ix_outbox_event_status_available_at", "status", "available_at"),
    )


class RateLimitBucket(Base):
    """One fixed-window counter per key (e.g. `login:ip:<hash>`), shared by every API instance."""

    __tablename__ = "rate_limit_bucket"

    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    window_start: Mapped[datetime] = mapped_column(primary_key=True)
    count: Mapped[int] = mapped_column(server_default=text("0"))
    expires_at: Mapped[datetime] = mapped_column(index=True)
