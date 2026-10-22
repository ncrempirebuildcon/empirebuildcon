"""Staff accounts, their sessions and one-time password tokens (D-009, SECURITY.md §1).

INVARIANT: `password_hash` is NULL until the person sets a password through their one-time
setup link. No account ever has a password chosen by someone else.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empire_api.db import Base, created_at_column, uuid_pk


class User(Base):
    __tablename__ = "app_user"  # WHY: "user" is a reserved word in PostgreSQL

    id: Mapped[uuid.UUID] = uuid_pk()
    email: Mapped[str] = mapped_column(String(254))  # stored lower-case; unique index below
    name: Mapped[str] = mapped_column(String(80))
    phone: Mapped[str | None] = mapped_column(String(20))
    role: Mapped[str] = mapped_column(String(32))
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    password_changed_at: Mapped[datetime | None] = mapped_column()
    failed_login_count: Mapped[int] = mapped_column(server_default=text("0"))
    locked_until: Mapped[datetime | None] = mapped_column()
    last_login_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("uq_app_user_email_lower", func.lower(email), unique=True),
        CheckConstraint(
            "role IN ('super_admin', 'admin', 'sales', 'marketing', 'content_editor')",
            name="role_valid",
        ),
    )


class UserSession(Base):
    """A signed-in browser. The JWT in the cookie names this row (`sid`); revoking it signs out.

    Idle limit 8 h (`last_seen_at`), absolute limit 7 days (`expires_at`).
    """

    __tablename__ = "user_session"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = created_at_column()
    last_seen_at: Mapped[datetime] = mapped_column()
    expires_at: Mapped[datetime] = mapped_column(index=True)
    revoked_at: Mapped[datetime | None] = mapped_column()
    ip_hash: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(200))

    user: Mapped[User] = relationship(back_populates="sessions")


class PasswordResetToken(Base):
    """A single-use link to set a password: `reset` (30 min) or `setup` for new accounts (24 h).

    SECURITY: only the SHA-256 of the token is stored (platform/crypto.py hash_token).
    """

    __tablename__ = "password_reset_token"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    purpose: Mapped[str] = mapped_column(String(16))
    expires_at: Mapped[datetime] = mapped_column(index=True)
    used_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (CheckConstraint("purpose IN ('reset', 'setup')", name="purpose_valid"),)
