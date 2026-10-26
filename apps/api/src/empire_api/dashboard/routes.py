"""Dashboard endpoint: GET /api/v1/admin/dashboard (design contract tag "Dashboard").

HTTP only: service.py decides what each role sees. Permission: `dashboard.view` (every role).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from empire_api.dashboard import service
from empire_api.dashboard.schemas import Dashboard
from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.leads.access import Staff
from empire_api.users.deps import require, staff
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin",
    tags=["Dashboard"],
    responses=problem_responses(400, 401, 403, 404, 422),
)


@router.get(
    "/dashboard",
    response_model=Dashboard,
    operation_id="dashboard",
    summary="Counts that link to filtered lists, latest leads, upcoming visits, tasks",
    **staff("dashboard.view"),
)
def dashboard(
    actor: Annotated[SessionInfo, Depends(require("dashboard.view"))],
    request: Request,
    db: Annotated[Session, Depends(get_db)],
) -> Dashboard:
    return service.dashboard(db, Staff.of(actor, request))
