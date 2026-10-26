"""Two-factor endpoints: /api/v1/auth/2fa/* (design contract tag "Auth"; part 5 additions).

Two groups:
  - The second step of a sign-in (public: the `__Host-empire_2fa` cookie from `login`'s 202 is
    the only authority): `verify` (a code or recovery code), and the forced set-up when the
    `admin_2fa` flag is on, `enrol` then `enrol/confirm`.
  - My account (signed in, CSRF): `setup` (needs the password) then `setup/confirm`, `disable`
    (password and a proof), `recovery-codes` (a proof).

Collaborators: users/sign_in.py and users/my_account.py do the work (lockout counting included).
SECURITY: answers that hold a secret or recovery codes are `no-store` (all of /api/v1/auth is,
middleware/security_headers.py); nothing here logs a code, secret or token.
"""

from __future__ import annotations

from typing import Annotated, Any, Final

from fastapi import APIRouter, BackgroundTasks, Cookie, Depends, Request, Response
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.integrations.outbox_drain import drain_soon
from empire_api.users import my_account, sign_in
from empire_api.users.deps import PUBLIC, CurrentSession, signed_in_route
from empire_api.users.routes_auth import request_meta, signed_in_answer
from empire_api.users.schemas import (
    Me,
    PasswordConfirm,
    RecoveryCodes,
    TwoFactorCode,
    TwoFactorDisable,
    TwoFactorEnrolled,
    TwoFactorProof,
    TwoFactorSetup,
)
from empire_api.users.two_factor import SetupDetails
from empire_api.users.two_factor_cookie import CHALLENGE_COOKIE, clear_challenge_cookie

router = APIRouter(
    prefix="/api/v1/auth/2fa",
    tags=["Auth"],
    responses=problem_responses(400, 401, 403, 409, 422, 429),
)
Db = Annotated[Session, Depends(get_db)]
ChallengeToken = Annotated[str | None, Cookie(alias=CHALLENGE_COOKIE, include_in_schema=False)]
RATE: Final = (
    "Counts toward the sign-in lockout: 5 passwords or codes per account and network per 15 "
    "minutes (429 after), and 20 codes per account per hour across networks."
)


def _second_step() -> dict[str, Any]:
    marker = dict(PUBLIC["openapi_extra"])
    return {"openapi_extra": {**marker, "x-rate-limit": RATE, "x-cookie": CHALLENGE_COOKIE}}


def _setup_out(details: SetupDetails) -> TwoFactorSetup:
    return TwoFactorSetup(
        otpauth_uri=details.otpauth_uri,
        secret=details.secret,
        qr_svg_data_url=details.qr_svg_data_url,
    )


# --- The second step of a sign-in ------------------------------------------------------------


@router.post(
    "/verify",
    response_model=Me,
    operation_id="two_factor_verify",
    summary="Sign-in step 2: a code from the app, or a recovery code",
    **_second_step(),
)
def verify(
    body: TwoFactorProof,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Db,
    challenge: ChallengeToken = None,
) -> Me:
    """Completes the sign-in started by `login`'s 202 (`step: verify`): sets the session cookie
    and clears the challenge cookie. A wrong code answers 401 and counts toward the lockout."""
    done = sign_in.verify_code(
        db,
        challenge,
        code=body.code,
        recovery_code=body.recovery_code,
        meta=request_meta(request),
    )
    clear_challenge_cookie(response)
    drain_soon(background)  # a used recovery code sends a security notice
    return signed_in_answer(db, done, response)


@router.post(
    "/enrol",
    response_model=TwoFactorSetup,
    operation_id="two_factor_enrol_start",
    summary="Forced set-up at sign-in, part 1: the key and QR code",
    **_second_step(),
)
def enrol_start(request: Request, db: Db, challenge: ChallengeToken = None) -> TwoFactorSetup:
    """For `login`'s 202 with `step: setup` (the admin_2fa flag is on and this admin has no
    two-factor yet). Each call makes a new key; only the newest one can be confirmed."""
    return _setup_out(sign_in.start_enrolment(db, challenge, request_meta(request)))


@router.post(
    "/enrol/confirm",
    response_model=TwoFactorEnrolled,
    operation_id="two_factor_enrol_confirm",
    summary="Forced set-up at sign-in, part 2: confirm a code, get recovery codes, sign in",
    **_second_step(),
)
def enrol_confirm(
    body: TwoFactorCode,
    request: Request,
    response: Response,
    background: BackgroundTasks,
    db: Db,
    challenge: ChallengeToken = None,
) -> TwoFactorEnrolled:
    """A right code turns two-factor on, starts the session (cookie) and returns the ten
    recovery codes, shown only this once."""
    done, codes = sign_in.confirm_enrolment(db, challenge, body.code, request_meta(request))
    clear_challenge_cookie(response)
    drain_soon(background)  # "two-factor was turned on" notice
    return TwoFactorEnrolled(recovery_codes=codes, me=signed_in_answer(db, done, response))


# --- My account ------------------------------------------------------------------------------


@router.post(
    "/setup",
    response_model=TwoFactorSetup,
    operation_id="two_factor_setup_start",
    summary="Turn two-factor on, part 1 (needs your password)",
    **signed_in_route(write=True),
)
def setup_start(
    body: PasswordConfirm, info: CurrentSession, request: Request, db: Db
) -> TwoFactorSetup:
    """Admins and super-admins only (403 otherwise); 409 when it is already on."""
    details = my_account.start_setup(db, info, body.current_password, request_meta(request))
    return _setup_out(details)


@router.post(
    "/setup/confirm",
    response_model=RecoveryCodes,
    operation_id="two_factor_setup_confirm",
    summary="Turn two-factor on, part 2: confirm a code, get recovery codes",
    **signed_in_route(write=True),
)
def setup_confirm(
    body: TwoFactorCode,
    info: CurrentSession,
    request: Request,
    background: BackgroundTasks,
    db: Db,
) -> RecoveryCodes:
    """Other sessions of this account are signed out. The codes are shown only this once."""
    codes = my_account.confirm_setup(db, info, body.code, request_meta(request))
    drain_soon(background)
    return RecoveryCodes(recovery_codes=codes)


@router.post(
    "/disable",
    status_code=204,
    operation_id="two_factor_disable",
    summary="Turn two-factor off (password and a code or recovery code)",
    **signed_in_route(write=True),
)
def disable(
    body: TwoFactorDisable,
    info: CurrentSession,
    request: Request,
    background: BackgroundTasks,
    db: Db,
) -> Response:
    my_account.disable(
        db, info, body.current_password, body.code, body.recovery_code, request_meta(request)
    )
    drain_soon(background)
    return Response(status_code=204)


@router.post(
    "/recovery-codes",
    response_model=RecoveryCodes,
    operation_id="two_factor_recovery_codes",
    summary="New recovery codes (a code or recovery code); the old ones stop working",
    **signed_in_route(write=True),
)
def regenerate(
    body: TwoFactorProof, info: CurrentSession, request: Request, db: Db
) -> RecoveryCodes:
    codes = my_account.regenerate_codes(
        db, info, body.code, body.recovery_code, request_meta(request)
    )
    return RecoveryCodes(recovery_codes=codes)
