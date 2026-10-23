"""Public lead intake: POST /api/v1/public/leads, /public/site-visits and /public/brochure-requests
(design contract tag "Lead intake").

HTTP only: the rules are in intake.py. No session and no CSRF (SECURITY.md §3: these routes
give a session's cookie no authority); rate limits and a honeypot instead.

SECURITY: the client IP comes from platform/crypto.client_ip (our proxy's header only behind
the edge key, never X-Forwarded-For) and is stored only as a salted hash.
"""

from __future__ import annotations

from typing import Annotated, Any, Final

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.integrations.outbox_drain import drain_soon
from empire_api.leads import intake
from empire_api.leads.schemas_public import (
    BrochureLink,
    BrochureRequest,
    LeadAccepted,
    LeadCreate,
    SiteVisitRequest,
)
from empire_api.leads.vocab import INTAKE_LIMIT, INTAKE_WINDOW_SECONDS
from empire_api.platform.crypto import client_ip
from empire_api.users.deps import PUBLIC

router = APIRouter(
    prefix="/api/v1/public",
    tags=["Lead intake"],
    responses=problem_responses(400, 409, 422, 429, 503),
)
Db = Annotated[Session, Depends(get_db)]
RATE: Final = f"{INTAKE_LIMIT} per {INTAKE_WINDOW_SECONDS // 60} minutes per IP and per phone"
CONSENT_RULES: Final = (
    "`consent` must name the CURRENT lead-form consent text (id and version): an older one "
    'answers 409 "reload the page"; with no published text the answer is 503. '
    "`marketing_consent` is optional and, when sent, must name the current marketing text. "
    "The phone is normalised to E.164 (+91…); anything else is 422 on `phone`. "
    "The same phone and project within 24 hours is saved as a duplicate of the earlier lead "
    "and doesn't alert sales again."
)


def _public(**extra: Any) -> dict[str, Any]:
    marker = dict(PUBLIC["openapi_extra"])
    return {"openapi_extra": {**marker, "x-rate-limit": RATE, **extra}}


@router.post(
    "/leads",
    status_code=201,
    response_model=LeadAccepted,
    operation_id="submit_lead",
    summary="Submit an enquiry (general or for a project)",
    description=CONSENT_RULES,
    **_public(),
)
def submit_lead(
    body: LeadCreate, request: Request, background: BackgroundTasks, db: Db
) -> LeadAccepted:
    result = intake.submit(db, body, client_ip(request), "enquiry")
    drain_soon(background)
    return LeadAccepted(reference=result.reference, message=result.message)


@router.post(
    "/site-visits",
    status_code=201,
    response_model=LeadAccepted,
    operation_id="request_site_visit",
    summary="Request a site visit (creates a lead and a visit request)",
    description=CONSENT_RULES
    + " The day must be today or within 120 days (IST); sales confirm the time by phone.",
    **_public(),
)
def request_site_visit(
    body: SiteVisitRequest, request: Request, background: BackgroundTasks, db: Db
) -> LeadAccepted:
    result = intake.submit(db, body, client_ip(request), "site_visit")
    drain_soon(background)
    return LeadAccepted(reference=result.reference, message=result.message)


@router.post(
    "/brochure-requests",
    status_code=201,
    response_model=BrochureLink,
    operation_id="request_brochure",
    summary="Get the brochure link (lead form first when gated)",
    description=CONSENT_RULES
    + " Only for a published project whose brochure is shown on the website (else 404). "
    "Honest note: this collects a lead before showing the link, but it is not access control; "
    "the PDF's address is public and doesn't expire, so `expires_at` is always null.",
    responses=problem_responses(404),
    **_public(),
)
def request_brochure(
    body: BrochureRequest, request: Request, background: BackgroundTasks, db: Db
) -> BrochureLink:
    result = intake.submit(db, body, client_ip(request), "brochure")
    drain_soon(background)
    assert result.brochure_url is not None  # noqa: S101 — intake refuses a missing brochure
    return BrochureLink(url=result.brochure_url, expires_at=None, reference=result.reference)
