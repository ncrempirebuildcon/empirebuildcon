"""Business rules for signing in, passwords and staff accounts.

Collaborators: users/sessions.py (session rows, tokens), users/passwords.py (hashing, policy),
users/lockout.py (sign-in counters), platform/audit.py, platform/outbox.py,
platform/rate_limit.py. Signing in itself lives in users/sign_in.py, two-factor in
users/two_factor.py.
Implements: D-009 and SECURITY.md §1; ARCHITECTURE §11 (audit on login and permission changes).

INVARIANT: every function that changes data records an audit row in the same transaction and
commits once at the end, so the change and its audit trail succeed or fail together.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Final
from urllib.parse import parse_qs, urlsplit

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.errors import ApiProblem
from empire_api.logs import mask_phone
from empire_api.platform import audit, outbox, rate_limit
from empire_api.platform.crypto import hash_ip, hash_token, network_key, new_token
from empire_api.timeutil import utcnow
from empire_api.users import lockout, passwords, two_factor
from empire_api.users.lockout import clear_every_network
from empire_api.users.models import PasswordResetToken, User, UserSession
from empire_api.users.sessions import revoke_sessions

# SECURITY: one message for "no such email" and "wrong password" so the login form can't be
# used to discover which emails have staff accounts.
GENERIC_LOGIN_ERROR = "The email or password is incorrect."
INVALID_LINK = "This link is invalid or has expired. Ask for a new one."
CURRENT_PASSWORD_WRONG = "Your current password is not correct."  # noqa: S105 — a message
# The lockout's limits and message, kept here too for callers that read them from the service.
LOCKED_MESSAGE = lockout.LOCKED_MESSAGE
MAX_FAILED_LOGINS = lockout.MAX_FAILED_LOGINS
LOCK_WINDOW_SECONDS = lockout.LOCK_WINDOW_SECONDS

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


# --- Sign out ----------------------------------------------------------------------------------


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
    """Change own password; every other session is signed out (SECURITY.md §1).

    SECURITY (part 5 review M2): the current password is counted on the sign-in lockout BEFORE
    it is checked (users/lockout.py), like My account's checks: otherwise a stolen session
    could guess it here without limit, then use it to put its own phone on the account. A
    miss is audited (`auth.password_check_failed`); a completed change clears the counter.
    """
    ip_key = lockout.network_hash(meta.ip)
    attempt = lockout.guard_attempt(user.email, ip_key)
    if not passwords.verify_password(user.password_hash, current):
        lockout.note_failure(db, user, attempt, meta.ip, action="auth.password_check_failed")
        db.commit()
        raise ApiProblem(
            400,
            CURRENT_PASSWORD_WRONG,
            errors=[{"field": "current_password", "message": CURRENT_PASSWORD_WRONG}],
        )
    _policy_or_422(new, user.email)
    now = utcnow()
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = now
    _burn_open_tokens(db, user.id, now)  # SECURITY: old reset emails stop working
    revoke_sessions(db, user.id, keep=session.id, now=now)
    audit.record(
        db,
        action="user.password_changed",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=meta.ip,
    )
    _password_changed_event(db, user, how="changed")
    db.commit()
    lockout.clear(user.email, ip_key)


def _password_changed_event(db: Session, user: User, *, how: str) -> None:
    """`user.password_changed`: the security email to the account (ids only)."""
    outbox.emit(
        db,
        type_="user.password_changed",
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=user.id,
        data={"user_id": str(user.id), "how": how},
    )


def issue_password_token(
    db: Session, user: User, *, purpose: str, actor_id: uuid.UUID | None
) -> str:
    """Create a single-use link token (every older open link of the account stops working) and
    queue the email event. Returns the raw token.

    COMPLIANCE/SECURITY: the link goes into the outbox payload encrypted (Fernet), so the queue
    table never holds a working link in plain text. Caller commits.
    """
    ttl = SETUP_TOKEN_TTL if purpose == "setup" else RESET_TOKEN_TTL
    token = new_token(32)
    # SECURITY (part 5 review M4): only the newest link works. An earlier one may have gone to a
    # mistyped address, and the CMS tells the super-admin that older links stop working.
    _burn_open_tokens(db, user.id, utcnow())
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
    # The mail module's handler decrypts and emails the link (mail/handlers.py); it is never
    # logged there either.
    return token


def password_link_open(db: Session, token: str) -> bool:
    """Whether a setup or reset token can still be used (not used, burned or expired). The mail
    handler checks this before sending, so a retried event never emails a dead link."""
    row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    )
    return row is not None and row.used_at is None and row.expires_at > utcnow()


def setup_link(token: str) -> str:
    """`<SITE_URL>/admin/setup#token=…`.

    SECURITY (part 5 review L10): the token is in the fragment, which browsers never send to a
    server, so it can't land in the web host's request logs (a third party keeps those for the
    link's whole lifetime). The CMS page reads it from `location.hash` and sends it in the body.
    """
    return f"{get_settings().site_url.rstrip('/')}/admin/setup#token={token}"


def reset_link(token: str) -> str:
    """`<SITE_URL>/admin/reset#token=…` (fragment, as setup_link explains)."""
    return f"{get_settings().site_url.rstrip('/')}/admin/reset#token={token}"


def token_of_link(link: str) -> str:
    """The token in a setup or reset link: the fragment, or (links queued before part 5's
    review) the query string."""
    parts = urlsplit(link)
    for source in (parts.fragment, parts.query):
        found = parse_qs(source).get("token")
        if found:
            return found[0]
    return ""


RESET_PER_HOUR: Final = 3
RESET_PER_DAY: Final = 5
DAY_SECONDS: Final = 24 * 3600


def forgot_password(db: Session, email: str, meta: RequestMeta) -> None:
    """Queue a reset email if the account exists. Same answer either way (no enumeration).

    Limits, all counted BEFORE the account is looked up, so a real and an unknown email get
    exactly the same answers (204, then the same 429s):
      1. 10 per hour per network;
      2. 3 per hour per email address (keyed hash);
      3. 5 per UTC day per email address. WHY: the hourly limit alone still lets someone spread
         72 requests a day over many networks at one address, most of the Resend Free plan's
         100 emails a day (D-007), and lead alerts would stop for the rest of the day. The
         window is a fixed day from midnight UTC, when Resend's daily quota resets too. Only
         requests the hourly limit let through count here, so a burst of refused ones doesn't
         use up the owner's own resets for the day.
    """
    rate_limit.enforce(
        f"reset:ip:{hash_ip(network_key(meta.ip))}",
        limit=10,
        window_seconds=3600,
        message="Too many reset requests from this network. Try again in an hour.",
    )
    email_key = hash_token(normalise_email(email))
    rate_limit.enforce(
        f"reset:email:{email_key}",
        limit=RESET_PER_HOUR,
        window_seconds=3600,
        message="Too many reset requests for this email. Try again in an hour.",
    )
    rate_limit.enforce(
        f"reset:email-day:{email_key}",
        limit=RESET_PER_DAY,
        window_seconds=DAY_SECONDS,
        message="Too many reset requests for this email today. Try again tomorrow.",
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
    """Use a reset or setup token: set the password, burn the token, sign out everywhere.

    SECURITY: the token is claimed with one conditional UPDATE (`used_at IS NULL`), so two
    parallel requests can't both use it; every other unused link for the account is burned too,
    so an older email can't be used after a newer reset.
    """
    now = utcnow()
    _policy_or_422(new, _email_for_token(db, token) or "")
    claimed = db.execute(
        update(PasswordResetToken)
        .where(
            PasswordResetToken.token_hash == hash_token(token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > now,
        )
        .values(used_at=now)
        .returning(PasswordResetToken.user_id, PasswordResetToken.purpose)
    ).first()
    if claimed is None:
        db.rollback()
        raise ApiProblem(400, INVALID_LINK)
    user = db.get(User, claimed.user_id)
    if user is None or not user.is_active:
        db.rollback()
        raise ApiProblem(400, INVALID_LINK)
    user.password_hash = passwords.hash_password(new)
    user.password_changed_at = now
    user.locked_until = None
    clear_every_network(user.email, user.id)
    _burn_open_tokens(db, user.id, now)
    revoke_sessions(db, user.id, now=now)
    audit.record(
        db,
        action=f"user.password_{'set' if claimed.purpose == 'setup' else 'reset'}",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=meta.ip,
    )
    if claimed.purpose == "reset":
        # The first password of a new account needs no notice; a reset does (security email).
        _password_changed_event(db, user, how="reset")
    db.commit()
    return user


def _email_for_token(db: Session, token: str) -> str | None:
    """The email of a token's account, only to check the new password doesn't contain it."""
    row = db.scalar(
        select(PasswordResetToken).where(PasswordResetToken.token_hash == hash_token(token))
    )
    user = db.get(User, row.user_id) if row else None
    return user.email if user else None


def _burn_open_tokens(db: Session, user_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(PasswordResetToken)
        .where(PasswordResetToken.user_id == user_id, PasswordResetToken.used_at.is_(None))
        .values(used_at=now)
    )


# --- Staff accounts (users.manage) ------------------------------------------------------------


def _snapshot(user: User) -> dict[str, Any]:
    """Fields recorded in audit diffs. SECURITY: phone numbers are masked (audit.py rule)."""
    return {
        "email": user.email,
        "name": user.name,
        "phone": mask_phone(user.phone) if user.phone else None,
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


def _usable_super_admin_count(db: Session) -> int:
    """Active super-admins who can actually sign in (password set), with their rows locked.

    WHY FOR UPDATE: two admins demoting the last two super-admins at the same moment would
    each see "one other is left" without the lock; with it, the second waits and sees zero.
    """
    rows = db.scalars(
        select(User.id)
        .where(
            User.role == "super_admin",
            User.is_active.is_(True),
            User.password_hash.is_not(None),
        )
        .with_for_update()
    ).all()
    return len(rows)


def update_user(
    db: Session, user: User, changes: dict[str, Any], actor_id: uuid.UUID, meta: RequestMeta
) -> User:
    """Edit a staff account. A role change or deactivation signs the person out everywhere.

    INVARIANT: there is always at least one active super-admin who can sign in (the owner).
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
    usable = user.is_active and user.password_hash is not None
    if (demoting or deactivating) and usable and _usable_super_admin_count(db) <= 1:
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
    if "email" in delta or "is_active" in delta:
        # SECURITY (part 5 review M4): a link sent to the old address, or before a deactivation,
        # must not work afterwards (reactivating would otherwise bring it back).
        _burn_open_tokens(db, user.id, utcnow())
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
    """Clear the lock note and every network's sign-in counter for this account."""
    user.locked_until = None
    clear_every_network(user.email, user.id)
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


def admin_reset_two_factor(
    db: Session, user: User, actor_id: uuid.UUID | None, meta: RequestMeta | None
) -> None:
    """Super-admin: remove someone's two-factor (lost phone) and sign them out everywhere.

    They get a security email (`user.two_factor_reset`). With the `admin_2fa` flag on, their
    next sign-in asks them to set it up again; otherwise they sign in with the password.
    """
    two_factor.admin_reset(db, user, actor_id, meta.ip if meta else None)
    revoke_sessions(db, user.id)
    db.commit()


def sign_out_admins_without_two_factor(db: Session, actor_id: uuid.UUID, ip: str | None) -> int:
    """`admin_2fa` was just switched on: sign out every admin and super-admin whose account has
    no two-factor yet (never the person switching, who has it by rule), so their next sign-in
    meets the forced set-up instead of a 7-day-old password-only session carrying on (part 5
    review L1). One audit row per account signed out. Returns how many accounts. Caller commits.
    """
    accounts = db.scalars(
        select(User).where(
            User.is_active.is_(True),
            User.role.in_(sorted(two_factor.TWO_FACTOR_ROLES)),
            User.id != actor_id,
        )
    ).all()
    signed_out = 0
    for user in accounts:
        if user.two_factor_enabled:
            continue
        count = revoke_sessions(db, user.id)
        if count:
            signed_out += 1
            audit.record(
                db,
                action="user.sessions_revoked",
                entity_type="user",
                entity_id=user.id,
                actor_id=actor_id,
                ip=ip,
                changes={"sessions": [count, 0], "reason": [None, "admin_2fa switched on"]},
            )
    return signed_out
