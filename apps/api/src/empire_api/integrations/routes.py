"""Internal endpoints called by Cloud Scheduler on free hosting (D-010):
POST /api/v1/internal/outbox/drain; and by the web server (task 5.6, D-047):
POST /api/v1/internal/redirects/hit.

SECURITY: guarded by the `X-Internal-Key` header (env INTERNAL_API_KEY), compared in constant
time. Never call this from the browser; the web app does not proxy `/api/v1/internal/*` keys.
The redirect hit is signed instead (seo/hits.py): the web host has REVALIDATE_SECRET, not the
internal key.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, Response
from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.integrations.outbox_drain import drain_with_lock
from empire_api.platform.crypto import constant_time_equals
from empire_api.seo import hits
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


class RedirectHit(BaseModel):
    from_path: str = Field(min_length=1, max_length=500)


async def _signed_body(
    request: Request,
    x_redirect_hit_signature: Annotated[str | None, Header()] = None,
    x_redirect_hit_timestamp: Annotated[str | None, Header()] = None,
) -> bytes:
    """The body of a correctly signed hit; 401/413 before anything large is read.

    SECURITY: the headers are checked first, the declared and the actual size are capped, and
    only then is the signature computed (seo/hits.py).
    """
    if not x_redirect_hit_signature or hits.fresh_timestamp(x_redirect_hit_timestamp) is None:
        raise ApiProblem(401, "Missing or wrong signature.")
    declared = request.headers.get("content-length", "")
    if declared and (not declared.isdigit() or int(declared) > hits.MAX_BODY_BYTES):
        raise ApiProblem(413, "Too large.")
    body = b""
    async for chunk in request.stream():
        body += chunk
        if len(body) > hits.MAX_BODY_BYTES:
            raise ApiProblem(413, "Too large.")
    if not hits.signature_ok(x_redirect_hit_signature, x_redirect_hit_timestamp, body):
        raise ApiProblem(401, "Missing or wrong signature.")
    return body


@router.post(
    "/redirects/hit",
    status_code=204,
    operation_id="record_redirect_hit",
    summary="Count one redirect the website answered (signed by the web server)",
    responses=problem_responses(413, 422),
    **INTERNAL,
)
def record_redirect_hit(
    body: Annotated[bytes, Depends(_signed_body)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    """204 whether or not the address has a redirect (nothing to learn from the answer)."""
    try:
        hit = RedirectHit.model_validate_json(body)
    except ValidationError:
        raise ApiProblem(422, "Send the redirect's from_path.") from None
    hits.record_hit(db, hit.from_path)
    return Response(status_code=204)
