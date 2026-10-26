"""Tables of the content module. Part 3: `consent_text`, the versioned wording a form shows next to
its consent checkbox (ARCHITECTURE §4, §8).

Collaborators: migrations/versions/0004_leads.py creates this table (tests/test_migrations.py
fails on any drift); content/consent.py is the only writer; leads/models.py `lead_consent`
points at the version a visitor accepted.

INVARIANT: at most one current text per kind (`uq_consent_text_current_kind`), a current text is
always published (`ck_consent_text_current_is_published`), and versions are unique per kind.
COMPLIANCE: a text is never edited once written; a change is a new version (DPDP: the lead's
consent record must keep pointing at the exact words the visitor saw). No code path updates
`body` or `checkbox_label`.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, Index, String, Text, UniqueConstraint, func
from sqlalchemy import text as sql
from sqlalchemy.orm import Mapped, mapped_column

from empire_api.content.vocab import CONSENT_KINDS
from empire_api.db import Base, created_at_column, uuid_pk
from empire_api.projects.vocab import check_in


class ConsentText(Base):
    """One version of one kind of consent wording (contract schema ConsentText)."""

    __tablename__ = "consent_text"

    id: Mapped[uuid.UUID] = uuid_pk()
    kind: Mapped[str] = mapped_column(String(16))
    version: Mapped[int] = mapped_column()
    body: Mapped[str] = mapped_column(Text)
    checkbox_label: Mapped[str] = mapped_column(String(300))
    published_at: Mapped[datetime | None] = mapped_column()
    is_current: Mapped[bool] = mapped_column(server_default=sql("false"))
    # WHY no foreign key: like project.created_by, authorship outlives any staff account row.
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("kind", "version"),
        Index(
            "uq_consent_text_current_kind",
            "kind",
            unique=True,
            postgresql_where=sql("is_current"),
        ),
        CheckConstraint(check_in("kind", CONSENT_KINDS), name="kind_valid"),
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint("NOT is_current OR published_at IS NOT NULL", name="current_is_published"),
    )
