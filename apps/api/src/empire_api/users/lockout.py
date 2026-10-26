"""Sign-in lockout and limits: counting every password and two-factor attempt per account AND
network before checking it (D-027, SECURITY.md §1).

Collaborators: users/sign_in.py (password step, two-factor step, forced set-up),
users/two_factor.py (My account's set-up, turn off, new recovery codes), users/service.py
(unlock, password reset clear the counters).
Implements: D-027 "Lockout", extended in Phase 4 part 5 to the two-factor step.

How it works:
  1. Per network: 10 password attempts per 15 minutes across all accounts (`guard_network`).
  2. Per account AND network: every attempt (password, two-factor code or recovery code) is
     counted with one atomic UPSERT BEFORE it is checked; the 6th within the 15-minute window
     gets 429 until the window ends (`guard_attempt`).
  3. The 5th failure notes a lock on the account (`note_failure`): an audit row, `locked_until`
     for the CMS, and a `user.locked` event (the security email).
  4. Only a COMPLETED sign-in (the session exists) clears the account/network counter. A correct
     password that still needs a code does not, otherwise "password, 4 wrong codes, password,
     4 wrong codes…" would give unlimited guesses at the code.
  5. Two-factor codes also have a per-account cap across all networks (`guard_code_rate`):
     20 per hour. WHY: per-network counting alone lets someone who already has the password
     spread code guesses over many networks; only someone with the password can reach this cap.

SECURITY (why this shape):
  - INVARIANT: at most 5 checks (password or code) per account, per network, per 15 minutes.
  - Counting before checking means parallel requests can't squeeze in extra guesses.
  - A stranger can't lock the owner out from another network: only the stranger's network is
    blocked. Unknown emails go through the same counting and get the same answers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Final

from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.platform import audit, outbox, rate_limit
from empire_api.platform.crypto import hash_ip, hash_token, network_key
from empire_api.platform.rate_limit import RateResult
from empire_api.timeutil import utcnow
from empire_api.users.models import User

MAX_FAILED_LOGINS: Final = 5
LOCK_WINDOW_SECONDS: Final = 15 * 60
NETWORK_LIMIT: Final = 10
CODE_LIMIT_PER_HOUR: Final = 20
LOCKED_MESSAGE: Final = "Too many attempts. Try again in 15 minutes."
CODE_CAP_MESSAGE: Final = "Too many two-factor codes were tried. Try again in about an hour."
NETWORK_MESSAGE: Final = "Too many sign-in attempts from this network. Try again in 15 minutes."


def network_hash(ip: str) -> str:
    """The keyed hash of the request's network (an IPv6 /64 is one network)."""
    return hash_ip(network_key(ip))


def attempt_key(email: str, ip_key: str) -> str:
    """The account/network counter's key. `ip_key=""` gives the prefix of every network."""
    return f"login:acct:{hash_token(email.strip().lower())}:{ip_key}"


def guard_network(ip_key: str) -> None:
    """Step 1: the per-network limit on password attempts."""
    rate_limit.enforce(
        f"login:ip:{ip_key}",
        limit=NETWORK_LIMIT,
        window_seconds=LOCK_WINDOW_SECONDS,
        message=NETWORK_MESSAGE,
    )


def guard_attempt(email: str, ip_key: str) -> RateResult:
    """Step 2: count this attempt for the account and network; 429 once over the limit."""
    attempt = rate_limit.hit(
        attempt_key(email, ip_key), limit=MAX_FAILED_LOGINS, window_seconds=LOCK_WINDOW_SECONDS
    )
    if not attempt.allowed:
        raise ApiProblem(429, LOCKED_MESSAGE, headers={"Retry-After": str(attempt.retry_after)})
    return attempt


def _code_cap_key(user_id: uuid.UUID) -> str:
    return f"2fa:acct:{user_id}"


def guard_code_rate(user: User) -> None:
    """Step 5: two-factor codes per account across all networks (an hour's window, so its
    message says an hour, matching Retry-After; part 5 review L6)."""
    result = rate_limit.hit(_code_cap_key(user.id), limit=CODE_LIMIT_PER_HOUR, window_seconds=3600)
    if not result.allowed:
        raise ApiProblem(429, CODE_CAP_MESSAGE, headers={"Retry-After": str(result.retry_after)})


def note_failure(
    db: Session, user: User | None, attempt: RateResult, ip: str | None, *, action: str
) -> None:
    """An audit row for a failed attempt, and step 3 on the 5th. Caller commits."""
    if user is not None and attempt.count == MAX_FAILED_LOGINS:
        _record_lock(db, user, ip, until=utcnow() + timedelta(seconds=attempt.retry_after))
    audit.record(
        db,
        action=action,
        entity_type="user",
        entity_id=user.id if user else "unknown",
        actor_id=None,
        ip=ip,
    )


def clear(email: str, ip_key: str) -> None:
    """Step 4: a completed sign-in clears this account's counter for this network."""
    rate_limit.clear(attempt_key(email, ip_key))


def clear_every_network(email: str, user_id: uuid.UUID | None = None) -> None:
    """Unlock and password reset: forget this account's counters on every network, and its
    two-factor code cap when the account is given (part 5 review L6: otherwise the person's
    right code could still get 429 for up to an hour after the super-admin unlocked them)."""
    rate_limit.clear_prefix(attempt_key(email, ""))
    if user_id is not None:
        rate_limit.clear(_code_cap_key(user_id))


def _record_lock(db: Session, user: User, ip: str | None, *, until: datetime) -> None:
    """Note a lockout for the CMS and the security email (the 429 itself comes from the counter).

    `locked_until` is informational: "locked from at least one network until …". Unlock in the
    CMS clears it and every network's counter for this account.
    """
    user.locked_until = until
    audit.record(
        db,
        action="user.locked",
        entity_type="user",
        entity_id=user.id,
        actor_id=None,
        ip=ip,
        changes={"locked_until": until.isoformat()},
    )
    outbox.emit(
        db,
        type_="user.locked",
        aggregate_type="user",
        aggregate_id=user.id,
        data={"user_id": str(user.id), "locked_until": until.isoformat()},
    )
