"""Two-factor sign-in for admin and super-admin accounts: set-up, codes, recovery codes, turning
it off, and the super-admin's reset (SECURITY.md §1, flag `admin_2fa`).

Collaborators: users/totp.py (the RFC 6238 codes), users/qr.py (the QR image), users/lockout.py
(every code attempt counts), users/sign_in.py (the sign-in steps), site_settings/flags.py
(`admin_2fa`), platform/crypto.py (Fernet, keyed hashes), platform/audit.py, platform/outbox.py.
Implements: SECURITY.md §1 "Two-factor", D-027 (lockout applies to codes too).

Rules:
  - Who: admin and super-admin accounts can turn it on (TWO_FACTOR_ROLES).
  - When it is asked at sign-in (`step_needed`): whenever the account has it on; and when the
    `admin_2fa` flag is on, an admin or super-admin without it must set it up before the
    session starts. WHY asked even with the flag off: someone who turned two-factor on expects
    it to protect them, and the super-admin must have it on (and so have tried it) before they
    may switch the flag on (site_settings/routes.py).
  - Set-up: a new secret is stored encrypted and unconfirmed; it counts only once a code from
    the app is confirmed. Then ten single-use recovery codes are made and shown ONCE.
  - Proof: a 6-digit code from the app (each 30-second step accepted once: replays are refused)
    or one recovery code (each works once).
  - Turning it off needs the password and a proof; new recovery codes need a proof.

SECURITY: secrets, codes and recovery codes are never logged, put in audit rows or events, or
returned after the one response that shows them.
INVARIANT: each write records an audit row; callers commit once, with it.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from typing import Final, Literal

from cryptography.fernet import InvalidToken
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.db import rows_affected
from empire_api.errors import ApiProblem
from empire_api.logs import get_logger
from empire_api.platform import audit, outbox
from empire_api.platform.crypto import data_digest
from empire_api.site_settings import flags
from empire_api.timeutil import utcnow
from empire_api.users import qr, totp
from empire_api.users.models import TwoFactorRecoveryCode, User, UserTwoFactor

TWO_FACTOR_ROLES: Final = frozenset({"super_admin", "admin"})
FLAG: Final = "admin_2fa"
RECOVERY_CODE_COUNT: Final = 10
# No 0/O, 1/I: easy to read off paper. 32 symbols = 5 bits each; 10 symbols = 50 bits.
_RECOVERY_ALPHABET: Final = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_RECOVERY_LENGTH: Final = 10
_DIGEST_PURPOSE: Final = "two_factor_recovery_code"

ROLE_NOT_ALLOWED: Final = "Two-factor sign-in is for admin and super-admin accounts."
ALREADY_ON: Final = "Two-factor sign-in is already on. Turn it off first to move it to a new phone."
NOT_ON: Final = "Two-factor sign-in isn't on for this account."
NO_SETUP: Final = "Start the set-up again: scan the new QR code, then enter its code."
WRONG_CODE: Final = "That code isn't right. Check your authenticator app and try again."
UNREADABLE: Final = (
    "Two-factor sign-in can't be checked for this account. Ask the super-admin to reset it."
)

log = get_logger(__name__)
Proof = Literal["totp", "recovery_code"]


@dataclass(frozen=True)
class SetupDetails:
    """What the person needs to add the account to an authenticator app. Shown once."""

    otpauth_uri: str
    secret: str
    qr_svg_data_url: str


def can_use(user: User) -> bool:
    return user.role in TWO_FACTOR_ROLES


def required_by_flag(db: Session, user: User) -> bool:
    """The `admin_2fa` flag is on and this account's role must use two-factor."""
    return can_use(user) and flags.is_enabled(db, FLAG)


def step_needed(db: Session, user: User) -> Literal["none", "verify", "setup"]:
    """What a correct password leads to (module header, "When it is asked")."""
    if user.two_factor_enabled:
        return "verify"
    if required_by_flag(db, user):
        return "setup"
    return "none"


def recovery_codes_left(db: Session, user: User) -> int | None:
    if not user.two_factor_enabled:
        return None
    return int(
        db.scalar(
            select(func.count())
            .select_from(TwoFactorRecoveryCode)
            .where(
                TwoFactorRecoveryCode.user_id == user.id, TwoFactorRecoveryCode.used_at.is_(None)
            )
        )
        or 0
    )


# --- Set-up ------------------------------------------------------------------------------------


def start_setup(db: Session, user: User, ip: str | None) -> SetupDetails:
    """Store a new, unconfirmed secret (replacing an unfinished one). Caller commits.

    Raises:
        ApiProblem: 403 for roles that can't use two-factor, 409 when it is already on.
    """
    if not can_use(user):
        raise ApiProblem(403, ROLE_NOT_ALLOWED)
    if user.two_factor_enabled:
        raise ApiProblem(409, ALREADY_ON)
    secret = totp.new_secret()
    encrypted = get_settings().fernet().encrypt(secret.encode()).decode()
    row = user.two_factor
    if row is None:
        row = UserTwoFactor(user_id=user.id, secret_encrypted=encrypted)
        db.add(row)
        user.two_factor = row
    else:
        row.secret_encrypted = encrypted
        row.confirmed_at = None
        row.last_used_step = None
    audit.record(
        db,
        action="user.two_factor_setup_started",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
    )
    uri = totp.provisioning_uri(secret, user.email)
    return SetupDetails(otpauth_uri=uri, secret=totp.grouped(secret), qr_svg_data_url=qr.svg(uri))


def confirm_setup(db: Session, user: User, code: str, ip: str | None) -> list[str] | None:
    """Turn two-factor on if `code` matches the unconfirmed secret. Returns the ten recovery
    codes (shown once), or None for a wrong code. Caller commits (also on None: audit trail).

    Raises:
        ApiProblem: 409 when it is already on or set-up wasn't started.
    """
    row = _locked(db, user)
    if row is not None and row.confirmed_at is not None:
        raise ApiProblem(409, ALREADY_ON)
    if row is None:
        raise ApiProblem(409, NO_SETUP)
    now = utcnow()
    step = totp.matching_step(_secret(row), code, now)
    if step is None:
        return None
    row.confirmed_at = now
    row.last_used_step = step
    codes = _new_recovery_codes(db, user)
    audit.record(
        db,
        action="user.two_factor_enabled",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
        changes={"two_factor_enabled": [False, True]},
    )
    _event(db, "user.two_factor_enabled", user, actor_id=user.id)
    return codes


# --- Proofs ------------------------------------------------------------------------------------


def check_proof(
    db: Session, user: User, *, code: str | None, recovery_code: str | None
) -> Proof | None:
    """Which proof was accepted (and is now used up), or None. Exactly one should be given.

    How it works:
      - App code: find the matching step within ±30 s, then claim it with one conditional UPDATE
        (`last_used_step < step`): a replayed code, or the same code sent twice in parallel,
        matches no row the second time.
      - Recovery code: claim it with one conditional UPDATE (`used_at IS NULL`).
    Caller commits.
    """
    row = user.two_factor
    if row is None or row.confirmed_at is None:
        return None
    if code:
        step = totp.matching_step(_secret(row), code, utcnow())
        if step is None:
            return None
        claimed = db.execute(
            update(UserTwoFactor)
            .where(
                UserTwoFactor.user_id == user.id,
                (UserTwoFactor.last_used_step.is_(None)) | (UserTwoFactor.last_used_step < step),
            )
            .values(last_used_step=step)
        )
        return "totp" if rows_affected(claimed) == 1 else None
    if recovery_code:
        claimed = db.execute(
            update(TwoFactorRecoveryCode)
            .where(
                TwoFactorRecoveryCode.user_id == user.id,
                TwoFactorRecoveryCode.code_hash == _recovery_hash(recovery_code),
                TwoFactorRecoveryCode.used_at.is_(None),
            )
            .values(used_at=utcnow())
        )
        return "recovery_code" if rows_affected(claimed) == 1 else None
    return None


def recovery_code_used(db: Session, user: User) -> None:
    """After a recovery code is used: tell the person (security email) how many are left."""
    _event(db, "user.recovery_code_used", user, remaining=recovery_codes_left(db, user) or 0)


# --- Turn off, new codes, reset -----------------------------------------------------------------


def disable(db: Session, user: User, ip: str | None) -> None:
    """Turn two-factor off (the caller checked the password and a proof). Caller commits."""
    _remove(db, user)
    audit.record(
        db,
        action="user.two_factor_disabled",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
        changes={"two_factor_enabled": [True, False]},
    )
    _event(db, "user.two_factor_disabled", user, actor_id=user.id)


def regenerate_recovery_codes(db: Session, user: User, ip: str | None) -> list[str]:
    """Ten new codes; the old ones stop working (the caller checked a proof). Caller commits."""
    _locked(db, user)
    codes = _new_recovery_codes(db, user)
    audit.record(
        db,
        action="user.two_factor_recovery_codes_regenerated",
        entity_type="user",
        entity_id=user.id,
        actor_id=user.id,
        ip=ip,
    )
    return codes


def admin_reset(db: Session, user: User, actor_id: uuid.UUID | None, ip: str | None) -> bool:
    """Super-admin: remove someone's two-factor (lost phone). Returns whether it was on.

    The person's sessions are revoked by the caller, and they get a security email. With the
    flag on, their next sign-in asks them to set it up again. `actor_id` None: the break-glass
    CLI on the server (`empire-api reset-two-factor`). Caller commits.
    """
    was_on = user.two_factor_enabled
    _remove(db, user)
    audit.record(
        db,
        action="user.two_factor_reset",
        entity_type="user",
        entity_id=user.id,
        actor_id=actor_id,
        ip=ip,
        changes={"two_factor_enabled": [was_on, False]},
    )
    by = {"by_user_id": str(actor_id)} if actor_id else {"by": "server_cli"}
    _event(db, "user.two_factor_reset", user, actor_id=actor_id, **by)
    return was_on


# --- Helpers -----------------------------------------------------------------------------------


def _secret(row: UserTwoFactor) -> str:
    try:
        return get_settings().fernet().decrypt(row.secret_encrypted.encode()).decode()
    except InvalidToken:
        # WHY a clear error, not a quiet "wrong code": DATA_ENCRYPTION_KEY changed since set-up,
        # so no code can ever match. Log the account id only (never the stored value).
        log.error("two_factor_secret_unreadable", user_id=str(row.user_id))
        raise ApiProblem(409, UNREADABLE) from None


def _locked(db: Session, user: User) -> UserTwoFactor | None:
    """The account's two-factor row, locked until commit. WHY: two confirmations (or two
    "new recovery codes") at the same moment would otherwise both write a set of codes, and
    both sets would work."""
    return db.get(UserTwoFactor, user.id, with_for_update=True, populate_existing=True)


def normalise_recovery_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())


def _recovery_hash(code: str) -> str:
    return data_digest(_DIGEST_PURPOSE, normalise_recovery_code(code))


def _new_recovery_codes(db: Session, user: User) -> list[str]:
    """Replace the account's recovery codes with ten new ones; returns them as "ABCDE-FGHJK"."""
    db.execute(delete(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user.id))
    codes = []
    for _ in range(RECOVERY_CODE_COUNT):
        raw = "".join(secrets.choice(_RECOVERY_ALPHABET) for _ in range(_RECOVERY_LENGTH))
        db.add(TwoFactorRecoveryCode(user_id=user.id, code_hash=_recovery_hash(raw)))
        codes.append(f"{raw[:5]}-{raw[5:]}")
    return codes


def _remove(db: Session, user: User) -> None:
    db.execute(delete(TwoFactorRecoveryCode).where(TwoFactorRecoveryCode.user_id == user.id))
    if user.two_factor is not None:
        db.delete(user.two_factor)
        user.two_factor = None
    db.flush()


def _event(
    db: Session,
    type_: str,
    user: User,
    *,
    actor_id: uuid.UUID | None = None,
    **data: str | int,
) -> None:
    """A user.* event for the security email. Ids only: no secret, code or address."""
    outbox.emit(
        db,
        type_=type_,
        aggregate_type="user",
        aggregate_id=user.id,
        actor_id=actor_id,
        data={"user_id": str(user.id), **data},
    )
