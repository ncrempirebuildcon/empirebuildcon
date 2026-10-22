"""Auth endpoints: /api/v1/auth/* (design contract tag "Auth").

Collaborators: users/service.py does the work; this module only maps HTTP to service calls,
sets and clears the session cookie, and shapes responses.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Request, Response
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.integrations.outbox_drain import drain_soon
from empire_api.platform.crypto import client_ip
from empire_api.users import schemas, service
from empire_api.users.deps import PUBLIC, CurrentSession, signed_in_route
from empire_api.users.roles import permissions_for
from empire_api.users.schemas import (
    LoginRequest,
    Me,
    PasswordChange,
    PasswordForgot,
    PasswordReset,
)
from empire_api.users.sessions import (
    SessionInfo,
    clear_session_cookie,
    csrf_token_for,
    set_session_cookie,
)

router = APIRouter(
    prefix="/api/v1/auth", tags=["Auth"], responses=problem_responses(401, 403, 422, 429)
)
Db = Annotated[Session, Depends(get_db)]


def request_meta(request: Request) -> service.RequestMeta:
    return service.RequestMeta(ip=client_ip(request), user_agent=request.headers.get("user-agent"))


def me_payload(info: SessionInfo) -> Me:
    base = schemas.User.model_validate(info.user).model_dump()
    return Me(**base, permissions=permissions_for(info.user.role), csrf_token=info.csrf_token)


@router.post("/login", response_model=Me, operation_id="login", **PUBLIC)
def login(body: LoginRequest, request: Request, response: Response, db: Db) -> Me:
    """Sign in. Sets the session cookie; 5 failed attempts lock the account for 15 minutes."""
    user, token, sid = service.login(db, body.email, body.password, request_meta(request))
    set_session_cookie(response, token)
    base = schemas.User.model_validate(user).model_dump()
    return Me(**base, permissions=permissions_for(user.role), csrf_token=csrf_token_for(sid))


@router.post("/logout", status_code=204, operation_id="logout", **signed_in_route(write=True))
def logout(info: CurrentSession, request: Request, db: Db) -> Response:
    """Sign out (revokes this session)."""
    service.logout(db, info.user, info.session, request_meta(request))
    response = Response(status_code=204)
    clear_session_cookie(response)
    return response


@router.get("/me", response_model=Me, operation_id="me", **signed_in_route())
def me(info: CurrentSession) -> Me:
    """Current user, permissions and CSRF token."""
    return me_payload(info)


@router.post("/password/forgot", status_code=204, operation_id="password_forgot", **PUBLIC)
def password_forgot(
    body: PasswordForgot, request: Request, background: BackgroundTasks, db: Db
) -> Response:
    """Email a reset link (same reply whether or not the email exists)."""
    service.forgot_password(db, body.email, request_meta(request))
    drain_soon(background)
    return Response(status_code=204)


@router.post("/password/reset", status_code=204, operation_id="password_reset", **PUBLIC)
def password_reset(body: PasswordReset, request: Request, db: Db) -> Response:
    """Set a new password with a reset or account-setup token. Signs out everywhere."""
    service.reset_password(db, body.token, body.new_password, request_meta(request))
    return Response(status_code=204)


@router.post(
    "/password/change",
    status_code=204,
    operation_id="password_change",
    **signed_in_route(write=True),
)
def password_change(
    body: PasswordChange, info: CurrentSession, request: Request, db: Db
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
    return Response(status_code=204)
