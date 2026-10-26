"""Signing in: the password step, and the two-factor step or forced set-up that may follow it.

Collaborators: users/lockout.py (counting), users/two_factor.py (codes, set-up),
users/sessions.py (the real session), users/passwords.py, users/routes_auth.py and
users/routes_two_factor.py (HTTP, cookies).
Implements: D-009, D-027 (lockout), SECURITY.md §1 (sessions, lockout, two-factor).

How a sign-in works:
  1. `login`: the network limit, then the account/network counter (counted BEFORE checking),
     then the password. Wrong → 401 with one generic message for unknown emails and wrong
     passwords alike.
  2. Correct, and two-factor isn't needed → the session starts (new sid), the counter clears.
  3. Correct, and two-factor is needed (two_factor.step_needed) → NO session. A sign-in
     challenge is stored (5 minutes, single use, bound to this account and network) and its
     token goes into the `__Host-empire_2fa` cookie. The answer says which step comes next:
     `verify` (enter a code) or `setup` (set two-factor up now: the `admin_2fa` flag is on and
     this admin has none yet).
  4. `verify_code` / `confirm_enrolment`: the challenge must still be open and come from the same
     network; the attempt is counted on the SAME account/network counter as passwords (and the
     per-account code cap) before the code is checked. A right code claims the challenge with
     one conditional UPDATE, and only then does the session start.

SECURITY: a correct password with a pending second step leaves the counter as it is (lockout.py
step 4). Challenge tokens are stored only as SHA-256 hashes; codes and secrets never reach logs,
audit rows or events.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Final, Literal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from empire_api.db import rows_affected
from empire_api.errors import ApiProblem
from empire_api.platform import audit
from empire_api.platform.crypto import hash_token, new_token
from empire_api.platform.rate_limit import RateResult
from empire_api.timeutil import utcnow
from empire_api.users import lockout, passwords, two_factor
from empire_api.users.models import SignInChallenge, User
from empire_api.users.service import (
    GENERIC_LOGIN_ERROR,
    RequestMeta,
    find_user_by_email,
)
from empire_api.users.sessions import revoke_sessions, start_session

CHALLENGE_TTL: Final = timedelta(minutes=5)
CHALLENGE_EXPIRED: Final = "Your sign-in timed out. Enter your email and password again."
Step = Literal["verify", "setup"]


@dataclass(frozen=True)
class SignedIn:
    """A completed sign-in: the session cookie's token and its id."""

    user: User
    token: str
    session_id: uuid.UUID


@dataclass(frozen=True)
class SecondStep:
    """A correct password that still needs a two-factor step (no session yet)."""

    user: User
    step: Step
    challenge_token: str
    expires_in_seconds: int


def login(db: Session, email: str, password: str, meta: RequestMeta) -> SignedIn | SecondStep:
    """Steps 1–3 of the module header."""
    ip_key = lockout.network_hash(meta.ip)
    lockout.guard_network(ip_key)
    attempt = lockout.guard_attempt(email, ip_key)
    user = find_user_by_email(db, email)
    ok = passwords.verify_password(user.password_hash if user else None, password)
    if user is None or not ok or not user.is_active:
        lockout.note_failure(db, user, attempt, meta.ip, action="auth.login_failed")
        db.commit()
        raise ApiProblem(401, GENERIC_LOGIN_ERROR)
    assert user.password_hash is not None  # noqa: S101 — verify_password returned True
    if passwords.needs_rehash(user.password_hash):
        user.password_hash = passwords.hash_password(password)
    step = two_factor.step_needed(db, user)
    if step == "none":
        return finish(db, user, meta, ip_key, method="password")
    token = _open_challenge(db, user, step, ip_key)
    audit.record(
        db,
        action="auth.two_factor_requested",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=meta.ip,
        changes={"step": [None, step]},
    )
    db.commit()
    return SecondStep(
        user=user,
        step=step,
        challenge_token=token,
        expires_in_seconds=int(CHALLENGE_TTL.total_seconds()),
    )


def finish(db: Session, user: User, meta: RequestMeta, ip_key: str, *, method: str) -> SignedIn:
    """Start the real session: counter cleared, new sid, audit row. Commits."""
    lockout.clear(user.email, ip_key)
    user.locked_until = None
    user.last_login_at = utcnow()
    session_row, token = start_session(db, user, ip_hash=ip_key, user_agent=meta.user_agent)
    audit.record(
        db,
        action="auth.login",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=meta.ip,
        changes={} if method == "password" else {"second_step": [None, method]},
    )
    db.commit()
    return SignedIn(user=user, token=token, session_id=session_row.id)


# --- The second step ------------------------------------------------------------------------


def open_challenge(
    db: Session, token: str | None, step: Step, meta: RequestMeta
) -> SignInChallenge:
    """The challenge this cookie names, if it is open, of this step and from this network.

    Raises:
        ApiProblem: 401 CHALLENGE_EXPIRED otherwise: also for an account deactivated meanwhile,
            and for a challenge opened before the account's last password change.
    """
    if not token:
        raise ApiProblem(401, CHALLENGE_EXPIRED)
    row = db.scalar(select(SignInChallenge).where(SignInChallenge.token_hash == hash_token(token)))
    now = utcnow()
    if (
        row is None
        or row.step != step
        or row.used_at is not None
        or row.expires_at <= now
        or row.network_hash != lockout.network_hash(meta.ip)
    ):
        raise ApiProblem(401, CHALLENGE_EXPIRED)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise ApiProblem(401, CHALLENGE_EXPIRED)
    if user.password_changed_at is not None and row.created_at < user.password_changed_at:
        # SECURITY (review M1, belt and braces): a challenge opened with an older password never
        # finishes, even if a path forgot to close it (users/sessions.revoke_sessions).
        raise ApiProblem(401, CHALLENGE_EXPIRED)
    return row


def verify_code(
    db: Session,
    token: str | None,
    *,
    code: str | None,
    recovery_code: str | None,
    meta: RequestMeta,
) -> SignedIn:
    """Step 4 for `verify`: a code or recovery code completes the sign-in."""
    challenge = open_challenge(db, token, "verify", meta)
    user = _challenge_user(db, challenge)
    attempt = _count(user, challenge)
    proof = two_factor.check_proof(db, user, code=code, recovery_code=recovery_code)
    if proof is None:
        lockout.note_failure(db, user, attempt, meta.ip, action="auth.two_factor_failed")
        db.commit()
        raise ApiProblem(401, two_factor.WRONG_CODE)
    _claim(db, challenge)
    if proof == "recovery_code":
        two_factor.recovery_code_used(db, user)
    return finish(db, user, meta, challenge.network_hash, method=proof)


def start_enrolment(db: Session, token: str | None, meta: RequestMeta) -> two_factor.SetupDetails:
    """Forced set-up at sign-in, part 1: a new secret for the account. Commits."""
    challenge = open_challenge(db, token, "setup", meta)
    user = _challenge_user(db, challenge)
    details = two_factor.start_setup(db, user, meta.ip)
    db.commit()
    return details


def confirm_enrolment(
    db: Session, token: str | None, code: str, meta: RequestMeta
) -> tuple[SignedIn, list[str]]:
    """Forced set-up at sign-in, part 2: a right code turns two-factor on and completes the
    sign-in. Returns the session and the ten recovery codes (shown once)."""
    challenge = open_challenge(db, token, "setup", meta)
    user = _challenge_user(db, challenge)
    attempt = _count(user, challenge)
    codes = two_factor.confirm_setup(db, user, code, meta.ip)
    if codes is None:
        lockout.note_failure(db, user, attempt, meta.ip, action="auth.two_factor_failed")
        db.commit()
        raise ApiProblem(401, two_factor.WRONG_CODE)
    _claim(db, challenge)
    # SECURITY (part 5 review L1): like My account's set-up, a session someone else may hold
    # doesn't outlive the stronger sign-in. Revoked before `finish` makes the new one.
    revoke_sessions(db, user.id)
    return finish(db, user, meta, challenge.network_hash, method="totp_setup"), codes


def _challenge_user(db: Session, challenge: SignInChallenge) -> User:
    user = db.get(User, challenge.user_id)
    assert user is not None  # noqa: S101 — open_challenge checked it
    return user


def _count(user: User, challenge: SignInChallenge) -> RateResult:
    """Count the attempt BEFORE checking the code (lockout.py steps 2 and 5)."""
    attempt = lockout.guard_attempt(user.email, challenge.network_hash)
    lockout.guard_code_rate(user)
    return attempt


def _open_challenge(db: Session, user: User, step: Step, ip_key: str) -> str:
    token = new_token(32)
    db.add(
        SignInChallenge(
            user_id=user.id,
            token_hash=hash_token(token),
            step=step,
            network_hash=ip_key,
            expires_at=utcnow() + CHALLENGE_TTL,
        )
    )
    return token


def _claim(db: Session, challenge: SignInChallenge) -> None:
    """SECURITY: one conditional UPDATE, so two right codes sent at once start one session."""
    claimed = db.execute(
        update(SignInChallenge)
        .where(SignInChallenge.id == challenge.id, SignInChallenge.used_at.is_(None))
        .values(used_at=utcnow())
    )
    if rows_affected(claimed) != 1:
        db.rollback()
        raise ApiProblem(401, CHALLENGE_EXPIRED)
