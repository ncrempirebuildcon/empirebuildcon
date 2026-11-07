"""Outbox handlers for server-side conversions (task 6.2, D-057). The flow is in __init__.py.

Platforms: "meta" (Conversions API) and "google" (Data Manager API). Each is used only when its
settings are complete; nothing at all is sent while CONVERSIONS_CONSENT_MIN_VERSION is unset.
"""

from __future__ import annotations

import uuid
from typing import Final, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.config import Settings, get_settings
from empire_api.integrations.conversions import google, meta
from empire_api.integrations.conversions.meta import (
    ConversionRejectedError,
    ConversionRetryableError,
    LeadForAds,
)
from empire_api.integrations.handlers import PermanentDeliveryError, on
from empire_api.leads.models import Lead, LeadConsent
from empire_api.logs import get_logger
from empire_api.platform import outbox
from empire_api.platform.models import OutboxEvent
from empire_api.site_settings.groups import TrackingSettings
from empire_api.site_settings.service import read_typed

Platform = Literal["meta", "google"]
SEND_EVENT: Final = "conversion.send"

log = get_logger(__name__)


def _meta_pixel(db: Session) -> str | None:
    return read_typed(db, "tracking", TrackingSettings).meta_pixel_id


def configured_platforms(db: Session, settings: Settings) -> list[Platform]:
    """The platforms whose settings are complete. Empty while the consent version is unset."""
    if settings.conversions_consent_min_version is None:
        return []
    platforms: list[Platform] = []
    if settings.meta_conversions_ready and _meta_pixel(db):
        platforms.append("meta")
    if settings.google_conversions_ready:
        platforms.append("google")
    return platforms


def _marketing_version(db: Session, lead_id: uuid.UUID) -> int | None:
    return db.scalar(
        select(LeadConsent.version)
        .where(LeadConsent.lead_id == lead_id, LeadConsent.kind == "marketing")
        .order_by(LeadConsent.accepted_at.desc())
        .limit(1)
    )


def may_report(db: Session, lead: Lead | None, settings: Settings) -> bool:
    """COMPLIANCE: the one gate. A real, live web enquiry whose marketing consent was given on a
    text version the reviewer approved for ad platforms."""
    minimum = settings.conversions_consent_min_version
    if lead is None or minimum is None:
        return False
    if lead.is_sample or lead.is_spam or lead.erased_at is not None or lead.duplicate_of_id:
        return False
    version = _marketing_version(db, lead.id)
    return version is not None and version >= minimum


@on("lead.created")
def queue_conversions(db: Session, event: OutboxEvent) -> None:
    """Emit one `conversion.send` per configured platform. Never calls a platform."""
    payload = event.payload or {}
    if not payload.get("alert") or not payload.get("marketing_consent"):
        return  # duplicates, manual leads, samples, or no marketing consent
    settings = get_settings()
    platforms = configured_platforms(db, settings)
    if not platforms:
        return
    lead = db.get(Lead, uuid.UUID(str(payload.get("lead_id"))))
    if not may_report(db, lead, settings):
        return
    for platform in platforms:
        outbox.emit(
            db,
            type_=SEND_EVENT,
            aggregate_type="lead",
            aggregate_id=event.aggregate_id,
            # COMPLIANCE: the user agent is the only personal detail here (Meta needs it); the
            # event is scrubbed with the lead's other events on erasure.
            contains_personal_data=platform == "meta",
            data={
                "platform": platform,
                "lead_id": payload.get("lead_id"),
                **({"user_agent": payload.get("user_agent")} if platform == "meta" else {}),
            },
        )


def _lead_for_ads(lead: Lead, user_agent: str | None) -> LeadForAds:
    return LeadForAds(
        lead_id=str(lead.id),
        created_at=lead.created_at,
        phone_e164=lead.phone_e164,
        email=lead.email,
        page_url=lead.page_url,
        gclid=lead.gclid,
        gbraid=lead.gbraid,
        wbraid=lead.wbraid,
        fbclid=lead.fbclid,
        user_agent=user_agent,
    )


def meta_client(settings: Settings) -> meta.MetaClient:
    return meta.MetaClient(
        settings.meta_capi_access_token.get_secret_value().strip(), settings.meta_graph_version
    )


def google_client(settings: Settings) -> google.GoogleClient:
    return google.GoogleClient(
        settings.google_dm_client_id.strip(),
        settings.google_dm_client_secret.get_secret_value().strip(),
        settings.google_dm_refresh_token.get_secret_value().strip(),
    )


@on(SEND_EVENT)
def send_conversion(db: Session, event: OutboxEvent) -> None:
    """Send one lead to one platform. Retries on network or server errors; a refusal is final."""
    payload = event.payload or {}
    if payload.get("erased"):
        return
    platform = payload.get("platform")
    settings = get_settings()
    lead_id = payload.get("lead_id")
    lead = db.get(Lead, uuid.UUID(str(lead_id))) if lead_id else None
    if platform not in configured_platforms(db, settings) or not may_report(db, lead, settings):
        log.info("conversion_skipped", platform=platform, event_id=str(event.event_id))
        return
    assert lead is not None  # noqa: S101 — may_report checked it
    ads_lead = _lead_for_ads(lead, payload.get("user_agent"))
    try:
        if platform == "meta":
            pixel = _meta_pixel(db)
            body = meta.event_body(ads_lead, test_event_code=settings.meta_test_event_code.strip())
            if not pixel:
                log.info("conversion_not_sendable", platform="meta", reason="no_pixel")
                return
            if body is None:
                log.info("conversion_not_sendable", platform="meta", reason="no_user_agent_or_url")
                return
            meta_client(settings).send(pixel, body)
        else:
            body = google.event_body(
                ads_lead,
                customer_id=settings.google_ads_customer_id,
                login_customer_id=settings.google_ads_login_customer_id,
                conversion_action_id=settings.google_ads_conversion_action_id,
                validate_only=settings.google_dm_validate_only,
            )
            if body is None:
                log.info("conversion_not_sendable", platform="google", reason="nothing_to_match")
                return
            google_client(settings).send(body)
    except ConversionRejectedError as exc:
        raise PermanentDeliveryError(str(exc)) from None
    except ConversionRetryableError as exc:
        raise RuntimeError(str(exc)) from None
    log.info("conversion_sent", platform=platform, event_id=str(event.event_id))
