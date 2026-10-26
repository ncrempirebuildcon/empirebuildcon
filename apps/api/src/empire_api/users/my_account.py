"""My account: a signed-in admin's own two-factor set-up, turning it off, and new recovery codes.

Collaborators: users/two_factor.py (the rules), users/lockout.py (counting), users/passwords.py,
users/sessions.py; users/routes_two_factor.py (HTTP).
Implements: SECURITY.md §1 (two-factor), D-027 (wrong passwords and codes count).

SECURITY (why each step asks for proof even though the person is signed in): a session can be
stolen or left open on a shared computer. Without the password, whoever holds it could put their
own phone on the account (and lock the owner out); without a code, they could turn two-factor off.
Every password or code checked here is counted on the same account/network counter as sign-in
attempts, BEFORE it is checked. Only a whole operation that succeeds clears the counter (like a
completed sign-in): turning two-factor off checks the password AND a code, and clearing after
the password alone would let "password, wrong code, password, wrong code…" guess forever.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.platform.rate_limit import RateResult
from empire_api.users import lockout, passwords, two_factor
from empire_api.users.service import RequestMeta
from empire_api.users.sessions import SessionInfo, revoke_sessions

CURRENT_WRONG: Final = "Your current password is not correct."


def _counted(info: SessionInfo, meta: RequestMeta) -> RateResult:
    return lockout.guard_attempt(info.user.email, lockout.network_hash(meta.ip))


def _done(info: SessionInfo, meta: RequestMeta) -> None:
    """The whole operation succeeded: clear the counter for this network (module header)."""
    lockout.clear(info.user.email, lockout.network_hash(meta.ip))


def _check_password(db: Session, info: SessionInfo, password: str, meta: RequestMeta) -> None:
    attempt = _counted(info, meta)
    if not passwords.verify_password(info.user.password_hash, password):
        lockout.note_failure(db, info.user, attempt, meta.ip, action="auth.password_check_failed")
        db.commit()
        raise ApiProblem(
            400, CURRENT_WRONG, errors=[{"field": "current_password", "message": CURRENT_WRONG}]
        )


def _check_proof(
    db: Session, info: SessionInfo, code: str | None, recovery_code: str | None, meta: RequestMeta
) -> two_factor.Proof:
    attempt = _counted(info, meta)
    lockout.guard_code_rate(info.user)
    proof = two_factor.check_proof(db, info.user, code=code, recovery_code=recovery_code)
    if proof is None:
        lockout.note_failure(db, info.user, attempt, meta.ip, action="auth.two_factor_failed")
        db.commit()
        field = "code" if code else "recovery_code"
        raise ApiProblem(
            400, two_factor.WRONG_CODE, errors=[{"field": field, "message": two_factor.WRONG_CODE}]
        )
    return proof


def start_setup(
    db: Session, info: SessionInfo, current_password: str, meta: RequestMeta
) -> two_factor.SetupDetails:
    """Part 1: check the password, then a new secret to scan. Commits."""
    if not two_factor.can_use(info.user):
        raise ApiProblem(403, two_factor.ROLE_NOT_ALLOWED)
    if info.user.two_factor_enabled:
        raise ApiProblem(409, two_factor.ALREADY_ON)
    _check_password(db, info, current_password, meta)
    details = two_factor.start_setup(db, info.user, meta.ip)
    db.commit()
    _done(info, meta)
    return details


def confirm_setup(db: Session, info: SessionInfo, code: str, meta: RequestMeta) -> list[str]:
    """Part 2: a right code turns two-factor on. Every OTHER session is signed out, so a session
    someone else may hold doesn't outlive the stronger sign-in. Returns the recovery codes."""
    attempt = _counted(info, meta)
    lockout.guard_code_rate(info.user)
    codes = two_factor.confirm_setup(db, info.user, code, meta.ip)
    if codes is None:
        lockout.note_failure(db, info.user, attempt, meta.ip, action="auth.two_factor_failed")
        db.commit()
        raise ApiProblem(
            400, two_factor.WRONG_CODE, errors=[{"field": "code", "message": two_factor.WRONG_CODE}]
        )
    revoke_sessions(db, info.user.id, keep=info.session.id)
    db.commit()
    _done(info, meta)
    return codes


def disable(
    db: Session,
    info: SessionInfo,
    current_password: str,
    code: str | None,
    recovery_code: str | None,
    meta: RequestMeta,
) -> None:
    """Turn two-factor off: the password AND a code (or recovery code). Commits.

    With the `admin_2fa` flag on, the next sign-in asks the person to set it up again.
    """
    if not info.user.two_factor_enabled:
        raise ApiProblem(409, two_factor.NOT_ON)
    _check_password(db, info, current_password, meta)
    _check_proof(db, info, code, recovery_code, meta)
    two_factor.disable(db, info.user, meta.ip)
    db.commit()
    _done(info, meta)


def regenerate_codes(
    db: Session, info: SessionInfo, code: str | None, recovery_code: str | None, meta: RequestMeta
) -> list[str]:
    """Ten new recovery codes after a code (or recovery code); the old ones stop working."""
    if not info.user.two_factor_enabled:
        raise ApiProblem(409, two_factor.NOT_ON)
    _check_proof(db, info, code, recovery_code, meta)
    codes = two_factor.regenerate_recovery_codes(db, info.user, meta.ip)
    db.commit()
    _done(info, meta)
    return codes
