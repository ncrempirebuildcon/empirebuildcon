"""Feature-flag endpoints: /api/v1/admin/flags (design contract tag "Settings").

TODO(phase-4): settings groups (`/api/v1/admin/settings`, `/{group}`) and `/api/v1/public/site`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.platform.crypto import client_ip
from empire_api.site_settings import flags
from empire_api.site_settings.models import FeatureFlag as FlagRow
from empire_api.users.deps import require, staff
from empire_api.users.models import User as UserRow
from empire_api.users.schemas import UserRef
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Settings"], responses=problem_responses(401, 403, 404, 409, 422)
)
Db = Annotated[Session, Depends(get_db)]


class FeatureFlag(BaseModel):
    key: str
    enabled: bool
    description: str
    is_public: bool
    is_locked: bool
    updated_at: datetime | None
    updated_by: UserRef | None


class FlagSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


def _out(db: Session, row: FlagRow) -> FeatureFlag:
    by = db.get(UserRow, row.updated_by) if row.updated_by else None
    return FeatureFlag(
        key=row.key,
        enabled=row.enabled,
        description=row.description,
        is_public=row.is_public,
        is_locked=row.is_locked,
        updated_at=row.updated_at,
        updated_by=UserRef(id=by.id, name=by.name) if by else None,
    )


@router.get(
    "/flags", response_model=list[FeatureFlag], operation_id="list_flags", **staff("settings.read")
)
def list_flags(
    actor: Annotated[SessionInfo, Depends(require("settings.read"))], db: Db
) -> list[FeatureFlag]:
    rows = db.scalars(select(FlagRow).order_by(FlagRow.key)).all()
    return [_out(db, r) for r in rows]


@router.patch(
    "/flags/{key}",
    response_model=FeatureFlag,
    operation_id="set_flag",
    **staff("flags.manage", write=True),
)
def set_flag(
    key: str,
    body: FlagSwitch,
    actor: Annotated[SessionInfo, Depends(require("flags.manage"))],
    request: Request,
    db: Db,
) -> FeatureFlag:
    """Switch a feature on or off. Locked features (not built yet) answer 409."""
    row = flags.set_flag(db, key, body.enabled, actor_id=actor.user.id, ip=client_ip(request))
    return _out(db, row)
