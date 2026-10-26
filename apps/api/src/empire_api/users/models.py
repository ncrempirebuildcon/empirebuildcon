"""Staff accounts, their sessions, one-time password tokens, and two-factor sign-in (D-009,
SECURITY.md §1).

INVARIANT: `password_hash` is NULL until the person sets a password through their one-time
setup link. No account ever has a password chosen by someone else.

Two-factor (Phase 4 part 5, users/two_factor.py): `user_two_factor` holds the encrypted TOTP
secret, `two_factor_recovery_code` the hashed single-use recovery codes, and `sign_in_challenge`
the short-lived second step of a sign-in (the `__Host-empire_2fa` cookie names one row).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empire_api.db import Base, created_at_column, uuid_pk
from empire_api.timeutil import utcnow


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
    locked_until: Mapped[datetime | None] = mapped_column()
    last_login_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    sessions: Mapped[list[UserSession]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    # PERF: loaded on first access; lists use selectinload (users/directory.py) to avoid N+1.
    two_factor: Mapped[UserTwoFactor | None] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        Index("uq_app_user_email_lower", func.lower(email), unique=True),
        CheckConstraint(
            "role IN ('super_admin', 'admin', 'sales', 'marketing', 'content_editor')",
            name="role_valid",
        ),
    )

    @property
    def status(self) -> str:
        """For the CMS list: deactivated, invited (no password yet), locked (from at least one
        network, until `locked_until`) or active, in that order of precedence."""
        if not self.is_active:
            return "deactivated"
        if self.password_hash is None:
            return "invited"
        if self.locked_until is not None and self.locked_until > utcnow():
            return "locked"
        return "active"

    @property
    def two_factor_enabled(self) -> bool:
        """Two-factor is on: set up AND confirmed with a code (a started set-up doesn't count)."""
        return self.two_factor is not None and self.two_factor.confirmed_at is not None


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


class UserTwoFactor(Base):
    """An account's authenticator-app secret (RFC 6238 TOTP, users/totp.py). One row per account.

    SECURITY:
      - `secret_encrypted` is the base32 secret encrypted with Fernet (DATA_ENCRYPTION_KEY). It is
        shown once, at set-up, and never logged or returned again.
      - `confirmed_at` NULL means set-up was started but not confirmed with a code: sign-in
        doesn't ask for it yet, and starting again replaces the secret.
      - INVARIANT: `last_used_step` is the newest 30-second step whose code was accepted. A code is
        accepted only for a LATER step, so a code someone saw (shoulder, screen share, log) can't
        be used again, even within its validity window. Claimed with one conditional UPDATE.
    """

    __tablename__ = "user_two_factor"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), primary_key=True
    )
    secret_encrypted: Mapped[str] = mapped_column(Text)
    confirmed_at: Mapped[datetime | None] = mapped_column()
    last_used_step: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TwoFactorRecoveryCode(Base):
    """One single-use recovery code (ten are issued at once, shown once).

    SECURITY: only a keyed hash is stored (platform/crypto.py data_digest), so a database copy
    doesn't reveal working codes. `used_at` is set with one conditional UPDATE, so a code can't be
    used twice, even by two requests at the same moment.
    """

    __tablename__ = "two_factor_recovery_code"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    used_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()


class SignInChallenge(Base):
    """The second step of a sign-in: a correct password that still needs a two-factor code
    (`verify`) or a forced two-factor set-up (`setup`). Named by the `__Host-empire_2fa` cookie.

    SECURITY: only the SHA-256 of the cookie's token is stored. A challenge lives 5 minutes, is
    bound to the network the password came from (`network_hash`), and is claimed once (`used_at`,
    one conditional UPDATE) when the real session starts.
    """

    __tablename__ = "sign_in_challenge"

    id: Mapped[uuid.UUID] = uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("app_user.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    step: Mapped[str] = mapped_column(String(8))
    network_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(index=True)
    used_at: Mapped[datetime | None] = mapped_column()
    created_at: Mapped[datetime] = created_at_column()

    __table_args__ = (CheckConstraint("step IN ('verify', 'setup')", name="step_valid"),)
