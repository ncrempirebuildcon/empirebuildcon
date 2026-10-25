"""Redirect endpoints: /api/v1/admin/redirects (design contract tag "SEO").

HTTP only: the rules are in redirects.py. Permission (ARCHITECTURE §11): `seo.manage` for all.
TODO(phase-5): `/api/v1/public/redirects` and `/api/v1/public/sitemap`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.pagination import PageParams, page_params
from empire_api.platform.crypto import client_ip
from empire_api.projects.common import Actor
from empire_api.seo import redirects
from empire_api.seo.models import Redirect as RedirectRow
from empire_api.seo.schemas import Redirect, RedirectInput, RedirectList, RedirectUpdate
from empire_api.seo.vocab import RedirectOrigin
from empire_api.users.deps import require, staff
from empire_api.users.schemas import PageMeta
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["SEO"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]
Manager = Annotated[SessionInfo, Depends(require("seo.manage"))]
RedirectId = Annotated[uuid.UUID, Path(alias="id")]
CONFLICT = problem_responses(409)


def _actor(info: SessionInfo, request: Request) -> Actor:
    return Actor(user_id=info.user.id, ip=client_ip(request))


def redirect_out(row: RedirectRow, notices: list[str] | None = None) -> Redirect:
    return Redirect(
        id=row.id,
        from_path=row.from_path,
        to_path=row.to_path,
        status_code="301" if row.status_code == 301 else "308",
        is_active=row.is_active,
        origin=row.origin,
        hits=row.hits,
        last_hit_at=row.last_hit_at,
        notices=notices or [],
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get(
    "/redirects",
    response_model=RedirectList,
    operation_id="list_redirects",
    summary="List redirects",
    **staff("seo.manage"),
)
def list_redirects(
    actor: Manager,
    db: Db,
    paging: Paging,
    q: Annotated[str | None, Query(max_length=100, description="Either path contains")] = None,
    origin: RedirectOrigin | None = None,
    is_active: bool | None = None,
) -> RedirectList:
    """Newest first. `origin` and `is_active` are additions (Phase 4 part 4)."""
    rows, total = redirects.list_redirects(db, paging, q, origin, is_active)
    return RedirectList(items=[redirect_out(r) for r in rows], meta=PageMeta(**paging.meta(total)))


@router.post(
    "/redirects",
    status_code=201,
    response_model=Redirect,
    operation_id="create_redirect",
    summary="Create redirect",
    responses=CONFLICT,
    **staff("seo.manage", write=True),
)
def create_redirect(body: RedirectInput, actor: Manager, request: Request, db: Db) -> Redirect:
    """409 for a loop or an address that already redirects. A chain is collapsed instead, and
    `notices` says what changed."""
    saved = redirects.create_redirect(db, _actor(actor, request), body)
    db.refresh(saved.row)
    return redirect_out(saved.row, saved.notices)


@router.patch(
    "/redirects/{id}",
    response_model=Redirect,
    operation_id="update_redirect",
    summary="Update redirect",
    responses=CONFLICT,
    **staff("seo.manage", write=True),
)
def update_redirect(
    redirect_id: RedirectId, body: RedirectUpdate, actor: Manager, request: Request, db: Db
) -> Redirect:
    saved = redirects.update_redirect(db, _actor(actor, request), redirect_id, body)
    db.refresh(saved.row)
    return redirect_out(saved.row, saved.notices)


@router.delete(
    "/redirects/{id}",
    status_code=204,
    operation_id="delete_redirect",
    summary="Delete redirect",
    **staff("seo.manage", write=True),
)
def delete_redirect(redirect_id: RedirectId, actor: Manager, request: Request, db: Db) -> Response:
    redirects.delete_redirect(db, _actor(actor, request), redirect_id)
    return Response(status_code=204)
