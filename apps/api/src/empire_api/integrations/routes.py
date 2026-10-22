"""Internal endpoints called by Cloud Scheduler on free hosting (D-010):
POST /api/v1/internal/outbox/drain.

SECURITY: guarded by the `X-Internal-Key` header (env INTERNAL_API_KEY), compared in constant
time. Never call this from the browser; the web app does not proxy `/api/v1/internal/*` keys.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Header
from pydantic import BaseModel

from empire_api.config import get_settings
from empire_api.errors import ApiProblem, problem_responses
from empire_api.integrations.outbox_drain import drain_with_lock
from empire_api.platform.crypto import constant_time_equals
from empire_api.users.deps import INTERNAL

router = APIRouter(
    prefix="/api/v1/internal", tags=["Internal"], responses=problem_responses(401, 429)
)


class DrainResult(BaseModel):
    processed: int
    failed: int
    remaining: int


@router.post("/outbox/drain", response_model=DrainResult, operation_id="drain_outbox", **INTERNAL)
def drain_outbox(
    x_internal_key: Annotated[str | None, Header()] = None,
) -> DrainResult:
    """Process pending events (and the daily clean-up). One run at a time; others get 429."""
    expected = get_settings().internal_api_key.get_secret_value()
    if not x_internal_key or not constant_time_equals(x_internal_key, expected):
        raise ApiProblem(401, "Missing or wrong internal key.")
    result = drain_with_lock()
    if result is None:
        raise ApiProblem(
            429, "A drain is already running. Try again shortly.", headers={"Retry-After": "30"}
        )
    return DrainResult(processed=result.processed, failed=result.failed, remaining=result.remaining)
