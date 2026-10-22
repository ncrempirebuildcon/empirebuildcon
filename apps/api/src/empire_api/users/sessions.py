"""Staff sessions: a signed JWT in the `__Host-empire_session` cookie, backed by a database row.

How it works:
  1. Login creates a `user_session` row (sid) and a JWT {sub=user id, sid, iat, exp}.
  2. Each request verifies the JWT signature and expiry, then loads the row: it must exist,
     belong to `sub`, not be revoked, be within the 7-day absolute limit and the 8-hour idle
     limit. Only then is the user signed in.
  3. Sign-out, password change and "revoke sessions" set `revoked_at`, which takes effect on the
     very next request (the reason for the row; a bare JWT can't be revoked).

Implements: D-009, SECURITY.md §1 (cookie, lifetime, rotation), §3 (CSRF).

DO NOT CHANGE the cookie name or flags without owner approval: `__Host-` + Secure + Path=/ and no
Domain guarantee the cookie is first-party and can't be set by a sub-domain; HttpOnly keeps it
away from scripts; SameSite=Lax is the second CSRF layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt
from fastapi import Response
from sqlalchemy import update
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.db import rows_affected
from empire_api.platform.crypto import constant_time_equals, keyed_digest
from empire_api.timeutil import utcnow
from empire_api.users.models import User, UserSession

COOKIE_NAME = "__Host-empire_session"
IDLE_LIMIT = timedelta(hours=8)
ABSOLUTE_LIMIT = timedelta(days=7)
# PERF: refresh `last_seen_at` at most once a minute instead of writing on every request.
_TOUCH_EVERY = timedelta(minutes=1)
_ALGORITHM = "HS256"


@dataclass(frozen=True)
class SessionInfo:
    user: User
    session: UserSession

    @property
    def csrf_token(self) -> str:
        return csrf_token_for(self.session.id)


def csrf_token_for(sid: uuid.UUID) -> str:
    """CSRF token bound to one session: HMAC(SESSION_SECRET, sid). Nothing extra to store."""
    return keyed_digest("csrf", str(sid))


def csrf_matches(sid: uuid.UUID, presented: str | None) -> bool:
    return bool(presented) and constant_time_equals(csrf_token_for(sid), presented or "")


def start_session(
    db: Session, user: User, *, ip_hash: str | None, user_agent: str | None
) -> tuple[UserSession, str]:
    """Create a new session row and its signed token. Caller commits."""
    now = utcnow()
    row = UserSession(
        user_id=user.id,
        last_seen_at=now,
        expires_at=now + ABSOLUTE_LIMIT,
        ip_hash=ip_hash,
        user_agent=(user_agent or "")[:200] or None,
    )
    db.add(row)
    db.flush()
    token = jwt.encode(
        {
            "sub": str(user.id),
            "sid": str(row.id),
            "iat": int(now.timestamp()),
            "exp": int(row.expires_at.timestamp()),
            "typ": "session",
        },
        get_settings().session_secret.get_secret_value(),
        algorithm=_ALGORITHM,
    )
    return row, token


def resolve_session(db: Session, token: str | None) -> SessionInfo | None:
    """Validate a cookie token against the session table. None = not signed in."""
    if not token:
        return None
    try:
        claims = jwt.decode(
            token,
            get_settings().session_secret.get_secret_value(),
            algorithms=[_ALGORITHM],
            options={"require": ["exp", "iat", "sub", "sid"]},
        )
        sid = uuid.UUID(claims["sid"])
        sub = uuid.UUID(claims["sub"])
    except jwt.PyJWTError, ValueError, KeyError:
        return None
    row = db.get(UserSession, sid)
    now = utcnow()
    if (
        row is None
        or row.user_id != sub
        or row.revoked_at is not None
        or now >= row.expires_at
        or now - row.last_seen_at >= IDLE_LIMIT
    ):
        return None
    user = row.user
    if not user.is_active:
        return None
    if now - row.last_seen_at >= _TOUCH_EVERY:
        row.last_seen_at = now
        db.commit()
    return SessionInfo(user=user, session=row)


def revoke_sessions(
    db: Session, user_id: uuid.UUID, *, keep: uuid.UUID | None = None, now: datetime | None = None
) -> int:
    """Revoke every live session of a user (optionally keeping one). Caller commits."""
    stmt = (
        update(UserSession)
        .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
        .values(revoked_at=now or utcnow())
    )
    if keep is not None:
        stmt = stmt.where(UserSession.id != keep)
    return rows_affected(db.execute(stmt))


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        max_age=int(ABSOLUTE_LIMIT.total_seconds()),
        path="/",
        secure=True,
        httponly=True,
        samesite="lax",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/", secure=True, httponly=True, samesite="lax")
