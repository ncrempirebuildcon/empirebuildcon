"""Public lead intake: an enquiry, a site-visit request (lead + visit) or a brochure request
(lead + the brochure's address). No session, no CSRF (SECURITY.md §3); rate limits and a
honeypot instead.

Collaborators: routes_public.py (HTTP), creation.py (row, consent, duplicate link),
routing.py (owner), effects.py (activity, events), content/consent.py (current texts),
projects/queries.py (public projects), media/queries.py (brochure), platform/rate_limit.py.
Implements: ARCHITECTURE §8 (intake, phone, consent, spam, assignment), §9, D-016, D-017,
SECURITY.md §8.

How it works (every check runs before anything is written):
  1. Normalise the phone (422 on `phone` with a message saying how to fix it).
  2. Count the attempt against the IP hash and the phone: 5 per 10 minutes each (429).
  3. Consent: no current lead-form text → 503 "Enquiries aren't open yet"; the form's text id
     or version isn't the current one → 409 "reload the page". The optional marketing box, when
     ticked, must name the current marketing text the same way.
  4. The project (published and visible), configuration, visit date and brochure.
  5. Honeypot filled → the same 201 with a look-alike reference, and nothing stored, so a bot
     can't tell it was caught. WHY last: any earlier answer would differ from a person's.
  6. In one transaction: the lead (duplicate check under a phone lock), its consent rows, the
     owner, the visit, the timeline, `lead.created` (+ `site_visit.requested`). Commit once.

DO NOT CHANGE: consent is stored in the same transaction as the lead (creation.py).
COMPLIANCE: marketing consent is recorded only when the visitor ticked it; never assumed.
WHY no audit row for a visitor's enquiry: the audit log is the staff trail (who changed what,
from which masked network). The enquiry is on the lead's own timeline and in `lead.created`;
an audit row would only add the visitor's network to a second table (SECURITY.md §8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Literal

from sqlalchemy.orm import Session

from empire_api.content import consent as consent_texts
from empire_api.content.models import ConsentText
from empire_api.errors import ApiProblem
from empire_api.leads import creation, effects, routing
from empire_api.leads.models import Lead, SiteVisit
from empire_api.leads.phone import PhoneError, normalise_phone
from empire_api.leads.reference import new_reference
from empire_api.leads.schemas_public import (
    ConsentGiven,
    LeadCreate,
    SiteVisitRequest,
)
from empire_api.leads.vocab import INTAKE_LIMIT, INTAKE_WINDOW_SECONDS, VISIT_MAX_DAYS_AHEAD
from empire_api.logs import get_logger
from empire_api.media import queries as media_queries
from empire_api.platform import rate_limit
from empire_api.platform.crypto import hash_ip, keyed_digest, network_key
from empire_api.projects import queries as project_queries
from empire_api.projects.queries import ProjectRef
from empire_api.timeutil import today_ist, utcnow

Intent = Literal["enquiry", "site_visit", "brochure"]

THANKS: Final[dict[str, str]] = {
    "enquiry": "Thank you. We have your enquiry, and our sales team will contact you.",
    "site_visit": (
        "Thank you. We have your site-visit request. Our sales team will call you to agree a time."
    ),
    "brochure": "Thank you. Your brochure is ready to open.",
}
NOT_OPEN: Final = (
    "Enquiries aren't open yet. Please call or WhatsApp us instead, or try again later."
)
CONSENT_CHANGED: Final = "The consent text changed — reload the page and tick the box again."
TOO_MANY: Final = "Too many enquiries in a short time. Please wait a few minutes and try again."
NO_PROJECT: Final = "We couldn't find this project on our website."
NO_CONFIGURATION: Final = "This floor plan isn't part of the project."
NO_BROCHURE: Final = "This project's brochure isn't available online yet."
VISIT_PAST: Final = "Choose today or a later day."
VISIT_TOO_FAR: Final = f"Choose a day within the next {VISIT_MAX_DAYS_AHEAD} days."

log = get_logger(__name__)


@dataclass(frozen=True)
class Accepted:
    reference: str
    message: str
    brochure_url: str | None = None


@dataclass(frozen=True)
class _Checked:
    phone_e164: str
    ip_hash: str
    lead_form: ConsentText
    marketing: ConsentText | None
    project: ProjectRef | None
    brochure_url: str | None


def _field_error(status: int, field: str, message: str) -> ApiProblem:
    return ApiProblem(status, message, errors=[{"field": field, "message": message}])


def _phone(raw: str) -> str:
    try:
        return normalise_phone(raw).e164
    except PhoneError as exc:
        raise _field_error(422, "phone", str(exc)) from exc


def _limit(ip_hash: str, phone_e164: str) -> None:
    """SECURITY: both counters always count; either one over its limit refuses (step 2).
    The phone is keyed (HMAC), so the rate-limit table never holds a phone number."""
    phone_key = keyed_digest("lead-intake-phone", phone_e164)
    results = [
        rate_limit.hit(key, limit=INTAKE_LIMIT, window_seconds=INTAKE_WINDOW_SECONDS)
        for key in (f"lead:ip:{ip_hash}", f"lead:phone:{phone_key}")
    ]
    refused = [r for r in results if not r.allowed]
    if refused:
        retry = max(r.retry_after for r in refused)
        raise ApiProblem(429, TOO_MANY, headers={"Retry-After": str(retry)})


def _matches(given: ConsentGiven, text: ConsentText | None) -> bool:
    return text is not None and given.consent_text_id == text.id and given.version == text.version


def _consent(db: Session, body: LeadCreate) -> tuple[ConsentText, ConsentText | None]:
    """Step 3. COMPLIANCE: a lead is never accepted under wording it wasn't shown."""
    lead_form = consent_texts.current_text(db, "lead_form")
    if lead_form is None:
        raise ApiProblem(503, NOT_OPEN, title="Enquiries aren't open yet")
    if not _matches(body.consent, lead_form):
        raise _field_error(409, "consent", CONSENT_CHANGED)
    if body.marketing_consent is None:
        return lead_form, None
    marketing = consent_texts.current_text(db, "marketing")
    if not _matches(body.marketing_consent, marketing):
        raise _field_error(409, "marketing_consent", CONSENT_CHANGED)
    return lead_form, marketing


def _project(db: Session, body: LeadCreate, intent: Intent) -> ProjectRef | None:
    """Step 4: a project visitors can see, and a floor plan that belongs to it."""
    if body.project_slug is None:
        if body.configuration_id is not None:
            raise _field_error(422, "configuration_id", NO_CONFIGURATION)
        return None
    project = project_queries.public_project(db, body.project_slug)
    if project is None:
        # The contract gives brochure requests a 404; the forms show a field error.
        raise _field_error(404 if intent == "brochure" else 422, "project_slug", NO_PROJECT)
    if body.configuration_id is not None and not project_queries.configuration_in_project(
        db, body.configuration_id, project.id
    ):
        raise _field_error(422, "configuration_id", NO_CONFIGURATION)
    return project


def _check_visit_day(body: SiteVisitRequest) -> None:
    today = today_ist()
    if body.preferred_date < today:
        raise _field_error(422, "preferred_date", VISIT_PAST)
    if body.preferred_date > today + timedelta(days=VISIT_MAX_DAYS_AHEAD):
        raise _field_error(422, "preferred_date", VISIT_TOO_FAR)


def _check(db: Session, body: LeadCreate, ip: str, intent: Intent) -> _Checked:
    phone = _phone(body.phone)  # 1
    # SECURITY: one counter per network, an IPv6 /64 counting as one (crypto.network_key).
    ip_hash = hash_ip(network_key(ip))
    _limit(ip_hash, phone)  # 2
    lead_form, marketing = _consent(db, body)  # 3
    project = _project(db, body, intent)  # 4
    if isinstance(body, SiteVisitRequest):
        _check_visit_day(body)
    brochure_url = None
    if intent == "brochure":
        assert project is not None  # noqa: S101 — BrochureRequest requires project_slug
        brochure_url = media_queries.visible_brochure_url(db, project.id)
        if brochure_url is None:
            raise _field_error(404, "project_slug", NO_BROCHURE)
    return _Checked(phone, ip_hash, lead_form, marketing, project, brochure_url)


def submit(db: Session, body: LeadCreate, ip: str, intent: Intent) -> Accepted:
    """Run the module's steps for one public form. Returns what the visitor is told."""
    checked = _check(db, body, ip, intent)
    if body.website.strip():  # 5
        log.info("lead_honeypot", intent=intent, ip_hash=checked.ip_hash[:8])
        return Accepted(new_reference(), THANKS[intent], checked.brochure_url)
    lead = _create(db, body, checked, intent)  # 6
    db.commit()
    log.info(
        "lead_received",
        lead_id=str(lead.id),
        intent=intent,
        source=lead.source,
        duplicate=lead.duplicate_of_id is not None,
    )
    return Accepted(lead.reference, THANKS[intent], checked.brochure_url)


def _new_row(body: LeadCreate, checked: _Checked) -> Lead:
    return Lead(
        name=body.name,
        phone_e164=checked.phone_e164,
        email=body.email,
        message=body.message,
        project_id=checked.project.id if checked.project else None,
        configuration_id=body.configuration_id,
        source=body.source,
        status="new",
        page_url=body.page_url,
        referrer=body.referrer,
        utm_source=body.utm.source,
        utm_medium=body.utm.medium,
        utm_campaign=body.utm.campaign,
        utm_term=body.utm.term,
        utm_content=body.utm.content,
        gclid=body.click_ids.gclid,
        gbraid=body.click_ids.gbraid,
        wbraid=body.click_ids.wbraid,
        fbclid=body.click_ids.fbclid,
        msclkid=body.click_ids.msclkid,
        preferred_bhk=body.preferred_bhk,
        budget_max_inr=body.budget_max_inr,
        preferred_contact_time=body.preferred_contact_time,
        language=body.language,
        ip_hash=checked.ip_hash,
    )


def _create(db: Session, body: LeadCreate, checked: _Checked, intent: Intent) -> Lead:
    """Step 6 (module header). Nothing is committed here."""
    now = utcnow()
    lead = _new_row(body, checked)
    creation.lock_phone(db, lead.phone_e164)
    original = creation.find_original(db, lead.phone_e164, lead.project_id, now)
    lead.duplicate_of_id = original.id if original else None
    lead.owner_user_id = routing.owner_for_new_lead(db, original)
    lead.assigned_at = now if lead.owner_user_id else None
    creation.insert_with_reference(db, lead)
    shown = creation.ConsentShown(checked.lead_form, body.page_url)
    creation.add_consent(db, lead, "lead_form", now, shown)
    if checked.marketing is not None:
        creation.add_consent(
            db, lead, "marketing", now, creation.ConsentShown(checked.marketing, body.page_url)
        )
    creation.record_created(db, lead, original, None, now, intent)
    visit = _add_visit(db, lead, body, now) if isinstance(body, SiteVisitRequest) else None
    effects.lead_created(
        db,
        lead,
        intent=intent,
        alert=original is None,
        marketing_consent=checked.marketing is not None,
        project_slug=checked.project.slug if checked.project else None,
    )
    if visit is not None:
        effects.visit_event(db, visit, "site_visit.requested", None, reference=lead.reference)
    return lead


def _add_visit(db: Session, lead: Lead, body: SiteVisitRequest, now: datetime) -> SiteVisit:
    assert lead.project_id is not None  # noqa: S101 — SiteVisitRequest requires a project
    visit = SiteVisit(
        lead_id=lead.id,
        project_id=lead.project_id,
        preferred_date=body.preferred_date,
        preferred_slot=body.preferred_slot,
        status="requested",
    )
    db.add(visit)
    db.flush()
    effects.activity(
        db,
        lead,
        "visit_requested",
        None,
        now,
        visit_id=visit.id,
        preferred_date=visit.preferred_date,
        preferred_slot=visit.preferred_slot,
    )
    return visit
