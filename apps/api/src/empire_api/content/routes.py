"""Consent-text endpoints: /api/v1/admin/consent-texts (design contract tag "Settings").

HTTP only: the rules are in consent.py. Permissions (ARCHITECTURE §11): reading needs
`settings.read`; writing a draft and publishing need `legal.publish`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.content import consent
from empire_api.content.models import ConsentText as ConsentRow
from empire_api.content.schemas import ConsentText, ConsentTextInput
from empire_api.content.vocab import ConsentKind
from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.platform.crypto import client_ip
from empire_api.projects.common import Actor
from empire_api.users.deps import require, staff
from empire_api.users.models import User
from empire_api.users.schemas import UserRef
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Settings"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[SessionInfo, Depends(require("settings.read"))]
Publisher = Annotated[SessionInfo, Depends(require("legal.publish"))]
TextId = Annotated[uuid.UUID, Path(alias="id")]


def _out(db: Session, rows: list[ConsentRow]) -> list[ConsentText]:
    author_ids = {row.created_by for row in rows if row.created_by}
    names = (
        dict(db.execute(select(User.id, User.name).where(User.id.in_(author_ids))).all())
        if author_ids
        else {}
    )
    return [
        ConsentText(
            id=row.id,
            kind=row.kind,
            version=row.version,
            body=row.body,
            checkbox_label=row.checkbox_label,
            published_at=row.published_at,
            is_current=row.is_current,
            is_draft=consent.is_draft(row),
            created_at=row.created_at,
            created_by=(
                UserRef(id=row.created_by, name=names[row.created_by])
                if row.created_by in names
                else None
            ),
        )
        for row in rows
    ]


@router.get(
    "/consent-texts",
    response_model=list[ConsentText],
    operation_id="list_consent_texts",
    summary="All versions",
    **staff("settings.read"),
)
def list_consent_texts(actor: Reader, db: Db, kind: ConsentKind | None = None) -> list[ConsentText]:
    """Every version of every kind (or of one `kind`), newest version first."""
    return _out(db, consent.list_texts(db, kind))


@router.post(
    "/consent-texts",
    status_code=201,
    response_model=ConsentText,
    operation_id="create_consent_text",
    summary="New draft version",
    **staff("legal.publish", write=True),
)
def create_consent_text(
    body: ConsentTextInput, actor: Publisher, request: Request, db: Db
) -> ConsentText:
    """A new, unpublished version. It takes effect only when published."""
    row = consent.create_draft(
        db,
        body.kind,
        body.body,
        body.checkbox_label,
        Actor(user_id=actor.user.id, ip=client_ip(request)),
    )
    return _out(db, [row])[0]


@router.post(
    "/consent-texts/{id}/publish",
    response_model=ConsentText,
    operation_id="publish_consent_text",
    summary="Make this version current",
    responses=problem_responses(409),
    **staff("legal.publish", write=True),
)
def publish_consent_text(
    text_id: TextId, actor: Publisher, request: Request, db: Db
) -> ConsentText:
    """Forms must send this version's id from now on; older versions get 409 "reload".
    In production a text still marked as a draft is refused (409)."""
    row = consent.publish(db, text_id, Actor(user_id=actor.user.id, ip=client_ip(request)))
    return _out(db, [row])[0]
