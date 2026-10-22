"""Business rules for signing in, passwords and staff accounts.

Collaborators: users/sessions.py (session rows, tokens), users/passwords.py (hashing, policy),
platform/audit.py, platform/outbox.py, platform/rate_limit.py.
Implements: D-009 and SECURITY.md §1; ARCHITECTURE §11 (audit on login and permission changes).

INVARIANT: every function that changes data records an audit row in the same transaction and
commits once at the end, so the change and its audit trail succeed or fail together.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.errors import ApiProblem
from empire_api.platform import audit, outbox, rate_limit
from empire_api.platform.crypto import hash_ip, hash_token, new_token
from empire_api.timeutil import utcnow
from empire_api.users import passwords
from empire_api.users.models import PasswordResetToken, User, UserSession
from empire_api.users.sessions import revoke_sessions, start_session

# SECURITY: one message for "no such email" and "wrong password" so the login form can't be
# used to discover which emails have staff accounts.
GENERIC_LOGIN_ERROR = "The email or password is incorrect."
LOCKED_MESSAGE = "Too many attempts. Try again in 15 minutes."
INVALID_LINK = "This link is invalid or has expired. Ask for a new one."

MAX_FAILED_LOGINS = 5
LOCK_DURATION = timedelta(minutes=15)
RESET_TOKEN_TTL = timedelta(minutes=30)
SETUP_TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class RequestMeta:
    """What a service needs to know about the HTTP request (for rate limits and audit)."""

    ip: str
    user_agent: str | None = None


def normalise_email(email: str) -> str:
    return email.strip().lower()


def find_user_by_email(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(func.lower(User.email) == normalise_email(email)))


# --- Sign in / out -------------------------------------------------------------------------------


def login(db: Session, email: str, password: str, meta: RequestMeta) -> tuple[User, str, uuid.UUID]:
    """Check credentials and start a session. Returns (user, signed token, session id).

    How it works:
      1. Per-IP rate limit (10 per 15 minutes), counted even when the attempt fails.
      2. Locked accounts get 429 until `locked_until` passes; unknown emails get the same 429
         after the same number of failures (no enumeration).
      3. Wrong password → failed count + 1; the 5th failure locks the account for 15 minutes.
      4. Success → counters reset, a new session (new sid), audit row.
    """
    ip_key = hash_ip(meta.ip)
    rate_limit.enforce(
        f"login:ip:{ip_key}",
        limit=10,
        window_seconds=15 * 60,
        message="Too many sign-in attempts from this network. Try again in 15 minutes.",
    )
    now = utcnow()
    user = find_user_by_email(db, email)
    # SECURITY: unknown emails "lock" too, after the same number of failures, so the 429 answer
    # can't be used to discover which emails have staff accounts (no account enumeration).
    unknown_key = f"login:unknown:{hash_token(normalise_email(email))}"

    if user is not None and user.locked_until is not None and user.locked_until > now:
        retry = max(1, int((user.locked_until - now).total_seconds()))
        raise ApiProblem(429, LOCKED_MESSAGE, headers={"Retry-After": str(retry)})
    if user is None:
        seen = rate_limit.current(unknown_key, window_seconds=int(LOCK_DURATION.total_seconds()))
        if seen.count >= MAX_FAILED_LOGINS:
            raise ApiProblem(429, LOCKED_MESSAGE, headers={"Retry-After": str(seen.retry_after)})

    ok = passwords.verify_password(user.password_hash if user else None, password)
    if user is None or not ok or not user.is_active:
        if user is not None and not ok:
            _register_failure(db, user, meta)
        elif user is None:
            rate_limit.hit(
                unknown_key,
                limit=MAX_FAILED_LOGINS,
                window_seconds=int(LOCK_DURATION.total_seconds()),
            )
        audit.record(
            db,
            action="auth.login_failed",
            entity_type="user",
            entity_id=user.id if user else "unknown",
            actor_id=None,
            ip=meta.ip,
        )
        db.commit()
        raise ApiProblem(401, GENERIC_LOGIN_ERROR)

    assert user.password_hash is not None  # noqa: S101 — verify_password returned True
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session_row, token = start_session(db, user, ip_hash=ip_key, user_agent=meta.user_agent)
    audit.record(
        db, action="auth.login", entity_type="user", entity_id=user.id, actor_id=user.id, ip=meta.ip
    )
    db.commit()
    return user, token, session_row.id


def _register_failure(db: Session, user: User, meta: RequestMeta) -> None:
    user.failed_login_count += 1
    if user.failed_login_count >= MAX_FAILED_LOGINS:
        user.failed_login_count = 0
        user.locked_until = utcnow() + LOCK_DURATION
        audit.record(
            db,
            action="user.locked",
            entity_type="user",
            entity_id=user.id,
            actor_id=None,
            ip=meta.ip,
            changes={"locked_until": user.locked_until.isoformat()},
        )
        outbox.emit(
            db,
            type_="user.locked",
            aggregate_type="user",
            aggregate_id=user.id,
            data={"user_id": str(user.id), "locked_until": user.locked_until.isoformat()},
        )


def logout(db: Session, user: User, session: UserSession, meta: RequestMeta) -> None:
    session.revoked_at = utcnow()
    audit.record(
        db,
        action="auth.logout",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=meta.ip,
    )
    db.commit()


# --- Passwords -----------------------------------------------------------------------------------


def _policy_or_422(password: str, email: str) -> None:
    errors = passwords.policy_errors(password, email=email)
    if errors:
        raise ApiProblem(
            422,
            "Choose a different password.",
            errors=[{"field": "new_password", "message": e} for e in errors],
        )


def change_password(
    db: Session, user: User, session: UserSession, current: str, new: str, meta: RequestMeta
) -> None:
    """Change own password; every other session is signed out (SECURITY.md §1)."""
    if not passwords.verify_password(user.password_hash, current):
        raise ApiProblem(400, "Your current password is not correct.")
    _policy_or_422(new, user.email)
    now = utcnow()
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = now
    revoke_sessions(db, user.id, keep=session.id, now=now)
    audit.record(
        db,
        action="user.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=meta.ip,
    )
    db.commit()


def issue_password_token(
    db: Session, user: User, *, purpose: str, actor_id: uuid.UUID | None
) -> str:
    """Create a single-use link token and queue the email event. Returns the raw token.

    COMPLIANCE/SECURITY: the link goes into the outbox payload encrypted (Fernet), so the queue
    table never holds a working link in plain text. Caller commits.
    """
    ttl = SETUP_TOKEN_TTL if purpose == "setup" else RESET_TOKEN_TTL
    token = new_token(32)
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hash_token(token),
            purpose=purpose,
            expires_at=utcnow() + ttl,
        )
    )
    link = setup_link(token) if purpose == "setup" else reset_link(token)
    event_type = "user.setup_link_issued" if purpose == "setup" else "user.password_reset_requested"
    outbox.emit(
        db,
        type_=event_type,
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        data={
            "user_id": str(user.id),
            "link_encrypted": get_settings().fernet().encrypt(link.encode()).decode(),
            "expires_in_minutes": int(ttl.total_seconds() // 60),
        },
        contains_personal_data=True,
    )
    # TODO(phase-4): an outbox handler emails this link through Resend (o-30 in the tracker).
    return token


def setup_link(token: str) -> str:
    return f"{get_settings().site_url.rstrip('/')}/admin/setup?token={token}"


def reset_link(token: str) -> str:
    return f"{get_settings().site_url.rstrip('/')}/admin/reset?token={token}"


def forgot_password(db: Session, email: str, meta: RequestMeta) -> None:
    """Queue a reset email if the account exists. Same answer either way (no enumeration)."""
    rate_limit.enforce(
        f"reset:ip:{hash_ip(meta.ip)}",
        limit=10,
        window_seconds=3600,
        message="Too many reset requests from this network. Try again in an hour.",
    )
    rate_limit.enforce(
        f"reset:email:{hash_token(normalise_email(email))}",
        limit=3,
        window_seconds=3600,
        message="Too many reset requests for this email. Try again in an hour.",
    )
    user = find_user_by_email(db, email)
    if user is None or not user.is_active:
        return
    issue_password_token(db, user, purpose="reset", actor_id=None)
    audit.record(
        db,
        action="user.password_reset_requested",
        entity_type="user",
        entity_id=user.id,
        actor_id=None,
        ip=meta.ip,
    )
    db.commit()


def reset_password(db: Session, token: str, new: str, meta: RequestMeta) -> User:
    """Use a reset or setup token: set the password, burn the token, sign out everywhere."""
    row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    )
    now = utcnow()
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise ApiProblem(400, INVALID_LINK)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ApiProblem(400, INVALID_LINK)
    _policy_or_422(new, user.email)
    row.used_at = now
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = now
    user.failed_login_count = 0
    user.locked_until = None
    revoke_sessions(db, user.id, now=now)
    audit.record(
        db,
        action=f"user.password_{'set' if row.purpose == 'setup' else 'reset'}",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=meta.ip,
    )
    db.commit()
    return user


# --- Staff accounts (users.manage) ------------------------------------------------------------


def _snapshot(user: User) -> dict[str, Any]:
    return {
        "email": user.email,
        "name": user.name,
        "phone": user.phone,
        "role": user.role,
        "is_active": user.is_active,
    }


def create_user(
    db: Session, data: dict[str, Any], actor_id: uuid.UUID | None, meta: RequestMeta | None
) -> tuple[User, str]:
    """Invite a staff member: account without a password + a 24-hour setup link."""
    email = normalise_email(data["email"])
    if find_user_by_email(db, email) is not None:
        raise ApiProblem(409, "A staff account with this email already exists.")
    user = User(
        email=email,
        name=data["name"],
        phone=data.get("phone"),
        role=data["role"],
        is_active=data.get("is_active", True),
    )
    db.add(user)
    db.flush()
    token = issue_password_token(db, user, purpose="setup", actor_id=actor_id)
    audit.record(
        db,
        action="user.created",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=meta.ip if meta else None,
        changes=audit.diff({}, _snapshot(user)),
    )
    outbox.emit(
        db,
        type_="user.created",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        data={"user_id": str(user.id), "role": user.role},
    )
    db.commit()
    return user, token


def _super_admin_count(db: Session) -> int:
    return int(
        db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == "super_admin", User.is_active.is_(True))
        )
        or 0
    )


def update_user(
    db: Session, user: User, changes: dict[str, Any], actor_id: uuid.UUID, meta: RequestMeta
) -> User:
    """Edit a staff account. A role change or deactivation signs the person out everywhere.

    INVARIANT: there is always at least one active super-admin (the owner).
    """
    before = _snapshot(user)
    if "email" in changes and changes["email"] is not None:
        email = normalise_email(changes["email"])
        other = find_user_by_email(db, email)
        if other is not None and other.id != user.id:
            raise ApiProblem(409, "A staff account with this email already exists.")
        changes["email"] = email
    demoting = changes.get("role") not in (None, "super_admin") and user.role == "super_admin"
    deactivating = changes.get("is_active") is False and user.role == "super_admin"
    if (demoting or deactivating) and user.is_active and _super_admin_count(db) <= 1:
        raise ApiProblem(409, "There must always be at least one active super-admin.")
    for field in ("email", "name", "phone", "role", "is_active"):
        if field in changes and (changes[field] is not None or field == "phone"):
            setattr(user, field, changes[field])
    after = _snapshot(user)
    delta = audit.diff(before, after)
    if not delta:
        return user
    if "role" in delta or ("is_active" in delta and not user.is_active):
        # SECURITY: privilege change → new session required (SECURITY.md §1 "rotated on
        # privilege change"). Revoking forces a fresh login, which issues a new sid.
        revoke_sessions(db, user.id)
    action = "user.role_changed" if "role" in delta else "user.updated"
    audit.record(
        db,
        action=action,
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=meta.ip,
        changes=delta,
    )
    outbox.emit(
        db,
        type_="user.updated",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        data={"user_id": str(user.id), "changed": sorted(delta)},
    )
    db.commit()
    return user


def unlock_user(db: Session, user: User, actor_id: uuid.UUID, meta: RequestMeta) -> None:
    user.locked_until = None
    user.failed_login_count = 0
    audit.record(
        db,
        action="user.unlocked",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=meta.ip,
    )
    db.commit()


def admin_revoke_sessions(db: Session, user: User, actor_id: uuid.UUID, meta: RequestMeta) -> None:
    count = revoke_sessions(db, user.id)
    audit.record(
        db,
        action="user.sessions_revoked",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=meta.ip,
        changes={"sessions": [count, 0]},
    )
    db.commit()


def admin_send_reset(db: Session, user: User, actor_id: uuid.UUID, meta: RequestMeta) -> None:
    purpose = "setup" if user.password_hash is None else "reset"
    issue_password_token(db, user, purpose=purpose, actor_id=actor_id)
    audit.record(
        db,
        action="user.reset_link_sent",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=meta.ip,
    )
    db.commit()
