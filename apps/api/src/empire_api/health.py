"""Health checks (ARCHITECTURE §20).

- `/api/health/live`: answers without touching the database, so uptime monitors don't wake the
  free database every 5 minutes (PERF, D-007).
- `/api/health`: also runs `select 1`; used after each deploy. Answers 503 when the database is
  down so a deploy check or monitor sees a failure, not a green 200.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from empire_api.config import get_settings
from empire_api.db import get_engine
from empire_api.logs import get_logger
from empire_api.timeutil import utcnow
from empire_api.users.deps import PUBLIC

router = APIRouter(tags=["System"])
log = get_logger(__name__)


class Live(BaseModel):
    status: Literal["ok"]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    database: Literal["ok", "down"]
    version: str
    time: datetime


@router.get("/api/health/live", response_model=Live, operation_id="health_live", **PUBLIC)
def health_live() -> Live:
    """Liveness only, no database."""
    return Live(status="ok")


@router.get(
    "/api/health",
    response_model=Health,
    operation_id="health",
    responses={503: {"model": Health, "description": "Database unreachable"}},
    **PUBLIC,
)
def health() -> JSONResponse:
    """Health check including the database."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        database: Literal["ok", "down"] = "ok"
    except Exception:  # WHY: any failure means "down"; details go to the log
        log.exception("health_database_down")
        database = "down"
    body = Health(
        status="ok" if database == "ok" else "degraded",
        database=database,
        version=get_settings().version,
        time=utcnow(),
    )
    return JSONResponse(body.model_dump(mode="json"), status_code=200 if database == "ok" else 503)
