"""Auth endpoints: /api/v1/auth/* (design contract tag "Auth"); the two-factor steps are in
routes_two_factor.py.

Collaborators: users/sign_in.py and users/service.py do the work; this module only maps HTTP to
service calls, sets and clears the cookies, and shapes responses.

Contract change (Phase 4 part 5): `login` answers 202 with a TwoFactorChallenge (and the
`__Host-empire_2fa` cookie, no session) when the account needs a second step; 200 with `Me` as
before otherwise.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.integrations.outbox_drain import drain_soon
from empire_api.platform.crypto import client_ip
from empire_api.users import schemas, service, sign_in, two_factor
from empire_api.users.deps import PUBLIC, CurrentSession, signed_in_route
from empire_api.users.models import User as UserRow
from empire_api.users.roles import permissions_for
from empire_api.users.schemas import (
    LoginRequest,
    Me,
    PasswordChange,
    PasswordForgot,
    PasswordReset,
    TwoFactorChallenge,
)
from empire_api.users.sessions import (
    SessionInfo,
    clear_session_cookie,
    csrf_token_for,
    set_session_cookie,
)
from empire_api.users.two_factor_cookie import set_challenge_cookie

router = APIRouter(
    prefix="/api/v1/auth", tags=["Auth"], responses=problem_responses(401, 403, 422, 429)
)
Db = Annotated[Session, Depends(get_db)]


def request_meta(request: Request) -> service.RequestMeta:
    return service.RequestMeta(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


def me_for(db: Session, user: UserRow, csrf_token: str) -> Me:
    """`Me` for a signed-in account (also the answer of every completed sign-in step)."""
    base = schemas.User.model_validate(user).model_dump()
    return Me(
        **base,
        permissions=permissions_for(user.role),
        csrf_token=csrf_token,
        can_use_two_factor=two_factor.can_use(user),
        two_factor_required=two_factor.required_by_flag(db, user),
        recovery_codes_left=two_factor.recovery_codes_left(db, user),
    )


def me_payload(db: Session, info: SessionInfo) -> Me:
    return me_for(db, info.user, info.csrf_token)


def signed_in_answer(db: Session, done: sign_in.SignedIn, response: Response) -> Me:
    """Set the session cookie on `response` and answer with `Me`."""
    set_session_cookie(response, done.token)
    return me_for(db, done.user, csrf_token_for(done.session_id))


@router.post(
    "/login",
    response_model=Me,
    operation_id="login",
    responses={
        202: {
            "model": TwoFactorChallenge,
            "description": "Password right; a two-factor step comes next (no session yet). Sets "
            "the __Host-empire_2fa cookie (HttpOnly, SameSite=Strict, 5 minutes).",
        }
    },
    **PUBLIC,
)
def login(body: LoginRequest, request: Request, response: Response, db: Db) -> Response | Me:
    """Sign in. 5 failed attempts (passwords or codes) lock the account for 15 minutes on that
    network. With two-factor, a right password answers 202 and the session starts only after
    the code (POST /auth/2fa/verify) or the forced set-up (/auth/2fa/enrol…)."""
    result = sign_in.login(db, body.email, body.password, request_meta(request))
    if isinstance(result, sign_in.SignedIn):
        return signed_in_answer(db, result, response)
    challenge = TwoFactorChallenge(
        step=result.step, email=result.user.email, expires_in_seconds=result.expires_in_seconds
    )
    answer = JSONResponse(challenge.model_dump(), status_code=202)
    set_challenge_cookie(answer, result.challenge_token)
    return answer


@router.post("/logout", status_code=204, operation_id="logout", **signed_in_route(write=True))
def logout(info: CurrentSession, request: Request, db: Db) -> Response:
    """Sign out (revokes this session)."""
    service.logout(db, info.user, info.session, request_meta(request))
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=Me, operation_id="me", **signed_in_route())
def me(info: CurrentSession, db: Db) -> Me:
    """Current user, permissions, two-factor state and CSRF token."""
    return me_payload(db, info)


@router.post("/password/forgot", status_code=204, operation_id="password_forgot", **PUBLIC)
def password_forgot(
    body: PasswordForgot, request: Request, background: BackgroundTasks, db: Db
) -> Response:
    """Email a reset link (same reply whether or not the email exists)."""
    service.forgot_password(db, body.email, request_meta(request))
    drain_soon(background)
    return Response(status_code=204)


@router.post("/password/reset", status_code=204, operation_id="password_reset", **PUBLIC)
def password_reset(
    body: PasswordReset, request: Request, background: BackgroundTasks, db: Db
) -> Response:
    """Set a new password with a reset or account-setup token. Signs out everywhere."""
    service.reset_password(db, body.token, body.new_password, request_meta(request))
    drain_soon(background)  # the "password was reset" notice
    return Response(status_code=204)


@router.post(
    "/password/change",
    status_code=204,
    operation_id="password_change",
    **signed_in_route(write=True),
)
def password_change(
    body: PasswordChange,
    info: CurrentSession,
    request: Request,
    background: BackgroundTasks,
    db: Db,
) -> Response:
    """Change own password (other sessions are signed out)."""
    service.change_password(
        db,
        info.user,
        info.session,
        body.current_password,
        body.new_password,
        request_meta(request),
    )
    drain_soon(background)  # the "password was changed" notice
    return Response(status_code=204)
