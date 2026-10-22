"""Staff administration: /api/v1/admin/users, /roles and /audit-log (design contract tag "Users").

All routes need `users.manage` (super-admin only) except the audit log (`audit.read`).
Admins never type a password for someone else: creating a user sends a one-time setup link.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.pagination import PageParams, page_params
from empire_api.platform.models import AuditLog
from empire_api.users import service
from empire_api.users.deps import require, staff
from empire_api.users.models import User as UserRow
from empire_api.users.roles import ROLE_NAMES, permissions_for
from empire_api.users.routes_auth import request_meta
from empire_api.users.schemas import (
    AuditEntry,
    AuditList,
    PageMeta,
    Role,
    User,
    UserInput,
    UserList,
    UserRef,
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


@router.get("/users", response_model=UserList, operation_id="list_users", **staff("users.manage"))
def list_users(
    actor: UsersManager,
    db: Db,
    paging: Paging,
    q: Annotated[str | None, Query(max_length=80)] = None,
) -> UserList:
    """Staff accounts, newest first. `q` matches name or email."""
    stmt = select(UserRow)
    if q:
        like = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            func.lower(UserRow.email).like(like) | func.lower(UserRow.name).like(like)
        )
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(UserRow.created_at.desc()).offset(paging.offset).limit(paging.per_page)
    ).all()
    return UserList(
        items=[User.model_validate(u) for u in rows], meta=PageMeta(**paging.meta(total))
    )


@router.post(
    "/users",
    status_code=201,
    response_model=User,
    operation_id="create_user",
    **staff("users.manage", write=True),
)
def create_user(body: UserInput, actor: UsersManager, request: Request, db: Db) -> User:
    """Invite a staff member. They get a one-time setup link to choose their own password."""
    user, _token = service.create_user(db, body.model_dump(), actor.user.id, request_meta(request))
    return User.model_validate(user)


@router.get("/users/{id}", response_model=User, operation_id="get_user", **staff("users.manage"))
def get_user(user_id: UserId, actor: UsersManager, db: Db) -> User:
    return User.model_validate(_get_user(db, user_id))


@router.patch(
    "/users/{id}",
    response_model=User,
    operation_id="update_user",
    **staff("users.manage", write=True),
)
def update_user(
    user_id: UserId, body: UserUpdate, actor: UsersManager, request: Request, db: Db
) -> User:
    """Edit name, email, phone, role or active state. Role changes sign the person out."""
    user = _get_user(db, user_id)
    updated = service.update_user(
        db, user, body.model_dump(exclude_unset=True), actor.user.id, request_meta(request)
    )
    return User.model_validate(updated)


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
def send_user_reset(user_id: UserId, actor: UsersManager, request: Request, db: Db) -> Response:
    """Send a reset link (or a fresh setup link if they never set a password)."""
    service.admin_send_reset(db, _get_user(db, user_id), actor.user.id, request_meta(request))
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


@router.get("/roles", response_model=list[Role], operation_id="list_roles", **staff("users.manage"))
def list_roles(actor: UsersManager) -> list[Role]:
    """The five roles and their permissions (ARCHITECTURE §11)."""
    return [
        Role(key=key, name=name, permissions=permissions_for(key))
        for key, name in ROLE_NAMES.items()
    ]


@router.get("/audit-log", response_model=AuditList, operation_id="audit_log", **staff("audit.read"))
def audit_log(
    actor: AuditReader,
    db: Db,
    paging: Paging,
    actor_id: uuid.UUID | None = None,
    entity_type: Annotated[str | None, Query(max_length=40)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    action: Annotated[str | None, Query(max_length=80)] = None,
    from_: Annotated[date | None, Query(alias="from")] = None,
    to: date | None = None,
) -> AuditList:
    """Audit log, newest first. Dates are whole days in UTC; `to` is inclusive."""
    stmt = select(AuditLog)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_user_id == actor_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == entity_id)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if from_:
        stmt = stmt.where(AuditLog.created_at >= datetime.combine(from_, time.min, tzinfo=UTC))
    if to:
        end = datetime.combine(to, time.min, tzinfo=UTC) + timedelta(days=1)
        stmt = stmt.where(AuditLog.created_at < end)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    actor_ids = {r.actor_user_id for r in rows if r.actor_user_id}
    names: dict[uuid.UUID, str] = {}
    if actor_ids:
        for user_id, name in db.execute(
            select(UserRow.id, UserRow.name).where(UserRow.id.in_(actor_ids))
        ):
            names[user_id] = name
    items = [
        AuditEntry(
            id=r.id,
            actor=UserRef(id=r.actor_user_id, name=names.get(r.actor_user_id, "Former user"))
            if r.actor_user_id
            else None,
            action=r.action,
            entity_type=r.entity_type,
            entity_id=r.entity_id,
            changes=r.changes,
            ip=r.ip,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return AuditList(items=items, meta=PageMeta(**paging.meta(total)))
