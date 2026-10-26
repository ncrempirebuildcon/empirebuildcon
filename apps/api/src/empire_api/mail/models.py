"""The sent-mail log: one row per email the system handed to a transport (mail/delivery.py).

COMPLIANCE (SECURITY.md §8): no address, name, subject or text is stored here. `recipient_key`
is a keyed hash of the address (platform/crypto.py data_digest), enough to answer "was this
event's email to this person already sent?" and "did this person get a lock notice in the last
hour?", and nothing more.

INVARIANT: at most one row per (event, template, recipient): the unique constraint is what makes
a retried event skip the people it already reached (mail/delivery.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from empire_api.db import Base, created_at_column, uuid_pk


class EmailMessage(Base):
    __tablename__ = "email_message"

    id: Mapped[uuid.UUID] = uuid_pk()
    # The outbox event that caused the email (platform/models.OutboxEvent.event_id).
    event_id: Mapped[uuid.UUID] = mapped_column()
    template: Mapped[str] = mapped_column(String(40))
    recipient_key: Mapped[str] = mapped_column(String(64))
    transport: Mapped[str] = mapped_column(String(10))
    # Resend's id for the message (support questions), or the dev mailbox file's id.
    provider_message_id: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (
        UniqueConstraint("event_id", "template", "recipient_key"),
        Index("ix_email_message_recipient_template", "recipient_key", "template", "created_at"),
    )
