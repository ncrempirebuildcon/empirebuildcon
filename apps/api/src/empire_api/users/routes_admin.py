"""Staff administration: /api/v1/admin/users, /roles, /permissions and /audit-log (design contract
tag "Users").

All routes need `users.manage` (super-admin only) except the audit log (`audit.read`).
Admins never type a password for someone else: creating a user sends a one-time setup link, and
the API never returns that link (it goes only to the person's inbox).

Contract additions (Phase 4 part 5): `role` and `status` filters on the list,
`POST /users/{id}/reset-2fa`, `GET /permissions` (the role table's rows), and on the audit log
the `system`, `action_prefix` filters and IST dates.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, Request, Response
from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session, selectinload

from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.integrations.outbox_drain import drain_soon
from empire_api.pagination import PageParams, page_params
from empire_api.timeutil import utcnow
from empire_api.users import service
from empire_api.users.audit_log import AuditFilters, audit_page
from empire_api.users.deps import require, staff
from empire_api.users.models import User as UserRow
from empire_api.users.present import user_out, users_out
from empire_api.users.role_docs import PERMISSION_GROUPS, ROLE_SUMMARIES
from empire_api.users.roles import PERMISSIONS, ROLE_KEYS, ROLE_NAMES, RoleKey, permissions_for
from empire_api.users.routes_auth import request_meta
from empire_api.users.schemas import (
    AuditList,
    PageMeta,
    Permission,
    Role,
    User,
    UserInput,
    UserList,
    UserStatus,
    UserUpdate,
)
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Users"], responses=problem_responses(401, 403, 404, 409, 422)
)
Db = Annotated[Session, Depends(get_db)]
UsersManager = Annotated[SessionInfo, Depends(require("users.manage"))]
AuditReader = Annotated[SessionInfo, Depends(require("audit.read"))]
Paging = Annotated[PageParams, Depends(page_params)]
# The contract names the path parameter `id`; `user_id` in Python avoids shadowing id().
UserId = Annotated[uuid.UUID, Path(alias="id")]


def _get_user(db: Session, user_id: uuid.UUID) -> UserRow:
    user = db.get(UserRow, user_id)
    if user is None:
        raise ApiProblem(404, "No staff account with this id.")
    return user


def _with_status(stmt: Select[UserRow], status: UserStatus) -> Select[UserRow]:
    """The same precedence as User.status (users/models.py): deactivated, invited, locked."""
    if status == "deactivated":
        return stmt.where(UserRow.is_active.is_(False))
    stmt = stmt.where(UserRow.is_active.is_(True))
    if status == "invited":
        return stmt.where(UserRow.password_hash.is_(None))
    stmt = stmt.where(UserRow.password_hash.is_not(None))
    locked = UserRow.locked_until.is_not(None) & (UserRow.locked_until > utcnow())
    return stmt.where(locked) if status == "locked" else stmt.where(~locked)


@router.get("/users", response_model=UserList, operation_id="list_users", **staff("users.manage"))
def list_users(
    actor: UsersManager,
    db: Db,
    paging: Paging,
    q: Annotated[str | None, Query(max_length=80)] = None,
    role: RoleKey | None = None,
    status: UserStatus | None = None,
) -> UserList:
    """Staff accounts, newest first. `q` matches name or email; `role` and `status` filter."""
    stmt = select(UserRow)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(UserRow.email).like(like) | func.lower(UserRow.name).like(like)
        )
    if role:
        stmt = stmt.where(UserRow.role == role)
    if status:
        stmt = _with_status(stmt, status)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.options(selectinload(UserRow.two_factor))
        .order_by(UserRow.created_at.desc(), UserRow.id)
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return UserList(items=users_out(db, rows), meta=PageMeta(**paging.meta(total)))


@router.post(
    "/users",
    status_code=201,
    response_model=User,
    operation_id="create_user",
    **staff("users.manage", write=True),
)
def create_user(
    body: UserInput,
    actor: UsersManager,
    request: Request,
    background: BackgroundTasks,
    db: Db,
) -> User:
    """Invite a staff member. They get a one-time setup link by email to choose their own
    password. SECURITY: the link is never in this answer (or any other)."""
    user, _token = service.create_user(db, body.model_dump(), actor.user.id, request_meta(request))
    drain_soon(background)
    return user_out(db, user)


@router.get("/users/{id}", response_model=User, operation_id="get_user", **staff("users.manage"))
def get_user(user_id: UserId, actor: UsersManager, db: Db) -> User:
    return user_out(db, _get_user(db, user_id))


@router.patch(
    "/users/{id}",
    response_model=User,
    operation_id="update_user",
    **staff("users.manage", write=True),
)
def update_user(
    user_id: UserId, body: UserUpdate, actor: UsersManager, request: Request, db: Db
) -> User:
    """Edit name, email, phone, role or active state (deactivate: `is_active: false`;
    reactivate: `true`). Role changes and deactivation sign the person out."""
    user = _get_user(db, user_id)
    updated = service.update_user(
        db, user, body.model_dump(exclude_unset=True), actor.user.id, request_meta(request)
    )
    return user_out(db, updated)


@router.post(
    "/users/{id}/unlock",
    status_code=204,
    operation_id="unlock_user",
    **staff("users.manage", write=True),
)
def unlock_user(user_id: UserId, actor: UsersManager, request: Request, db: Db) -> Response:
    service.unlock_user(db, _get_user(db, user_id), actor.user.id, request_meta(request))
    return Response(status_code=204)


@router.post(
    "/users/{id}/send-reset",
    status_code=204,
    operation_id="send_user_reset",
    **staff("users.manage", write=True),
)
def send_user_reset(
    user_id: UserId,
    actor: UsersManager,
    request: Request,
    background: BackgroundTasks,
    db: Db,
) -> Response:
    """Send a reset link (or a fresh setup link if they never set a password)."""
    service.admin_send_reset(db, _get_user(db, user_id), actor.user.id, request_meta(request))
    drain_soon(background)
    return Response(status_code=204)


@router.post(
    "/users/{id}/revoke-sessions",
    status_code=204,
    operation_id="revoke_user_sessions",
    **staff("users.manage", write=True),
)
def revoke_user_sessions(
    user_id: UserId, actor: UsersManager, request: Request, db: Db
) -> Response:
    service.admin_revoke_sessions(db, _get_user(db, user_id), actor.user.id, request_meta(request))
    return Response(status_code=204)


@router.post(
    "/users/{id}/reset-2fa",
    status_code=204,
    operation_id="reset_user_two_factor",
    summary="Remove someone's two-factor (lost phone); signs them out everywhere",
    **staff("users.manage", write=True),
)
def reset_user_two_factor(
    user_id: UserId,
    actor: UsersManager,
    request: Request,
    background: BackgroundTasks,
    db: Db,
) -> Response:
    """Audited, and the person gets a security email. With the admin_2fa flag on, their next
    sign-in asks them to set it up again. Not for your own account (409): My account turns it
    off with your password and a code, which this route doesn't ask for."""
    user = _get_user(db, user_id)
    if user.id == actor.user.id:
        # SECURITY (part 5 review L5): otherwise a stolen super-admin session could drop the
        # second factor without the password and a code that My account demands.
        raise ApiProblem(409, "Use My account to turn two-factor off for your own account.")
    service.admin_reset_two_factor(db, user, actor.user.id, request_meta(request))
    drain_soon(background)
    return Response(status_code=204)


@router.get("/roles", response_model=list[Role], operation_id="list_roles", **staff("users.manage"))
def list_roles(actor: UsersManager, db: Db) -> list[Role]:
    """The five roles, what each is for, their permissions and how many active accounts have
    each (ARCHITECTURE §11)."""
    counts = Counter(
        dict(
            db.execute(
                select(UserRow.role, func.count())
                .where(UserRow.is_active.is_(True))
                .group_by(UserRow.role)
            ).all()
        )
    )
    return [
        Role(
            key=key,
            name=name,
            permissions=permissions_for(key),
            summary=ROLE_SUMMARIES[key],
            user_count=int(counts.get(key, 0)),
        )
        for key, name in ROLE_NAMES.items()
    ]


@router.get(
    "/permissions",
    response_model=list[Permission],
    operation_id="list_permissions",
    summary="The role table: each permission, what it allows and which roles have it",
    **staff("users.manage"),
)
def list_permissions(actor: UsersManager) -> list[Permission]:
    """In the order of ARCHITECTURE §11, grouped as on the users and roles board."""
    return [
        Permission(
            key=key,
            group=PERMISSION_GROUPS[key],
            allows=allows,
            roles=[role for role in ROLE_KEYS if role in roles],
        )
        for key, (allows, roles) in PERMISSIONS.items()
    ]


@router.get("/audit-log", response_model=AuditList, operation_id="audit_log", **staff("audit.read"))
def audit_log(
    actor: AuditReader,
    db: Db,
    paging: Paging,
    actor_id: Annotated[uuid.UUID | None, Query(description="One person")] = None,
    system: Annotated[
        bool, Query(description="Only entries made by the system (no person)")
    ] = False,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=80, description="Exact action")] = None,
    action_prefix: Annotated[
        str | None,
        Query(max_length=80, description="Actions starting with this, e.g. auth. or user."),
    ] = None,
    from_: Annotated[date | None, Query(alias="from", description="First IST day")] = None,
    to: Annotated[date | None, Query(description="Last IST day (inclusive)")] = None,
) -> AuditList:
    """Audit log, newest first. Dates are whole days in India time (IST); `to` is inclusive.
    IP addresses are masked; the actor comes with their name and current role."""
    if from_ and to and to < from_:
        raise ApiProblem(
            422,
            "Some fields need attention.",
            errors=[{"field": "to", "message": "The last day can't be before the first day."}],
        )
    filters = AuditFilters(
        actor_id=actor_id,
        system=system,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        action_prefix=action_prefix,
        date_from=from_,
        date_to=to,
    )
    return audit_page(db, filters, paging)
