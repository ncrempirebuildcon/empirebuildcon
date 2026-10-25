"""Business rules for offers and banners: list, create, update, delete, and announcing when an
offer goes live or ends (here on edits, in schedule.py on the tick).

Collaborators: offers_state.py (state and wording checks), common.py (audit, events),
page_blocks.py (an offer a block shows can't be deleted), media/content_links.py (the image is
a library image), projects/queries.py, routes_marketing.py.
Implements: ARCHITECTURE §9 (`offer.started` / `offer.ended` / `offer.changed`), §10, §11
(`offers.manage`); AGENTS.md "No fake urgency"; D-015.

Rules:
  - Placement is banner, home or project; a project placement names its project.
  - COMPLIANCE (D-033, review L11): the image is a library image with an honest label (offer
    images often show renders); sample placeholders are exempt (D-015).
  - `ends_at` after `starts_at`; a button needs both its label and its link.
  - COMPLIANCE: no countdown field exists; pressure wording ("only N left", "hurry") is
    refused; an offer that mentions a price or discount needs a terms line or a T&C link
    (offers_state.py explains the light check).
  - D-015: a sample offer can't be switched on in production.
  - Announcing: when an edit (or the tick) makes the offer live, `offer.started`; when it stops
    being live (ended, switched off, dates moved), `offer.ended`. `is_live_announced` makes each
    happen once. `offer.changed` follows any edit while the offer is live (before or after).
  - An offer that has been live stays for the record (switch it off instead); one a page block
    shows can't be deleted until the block changes.

INVARIANT: every function commits once, after its audit row and events.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, Final

from sqlalchemy import ColumnElement, and_, func, or_, select
from sqlalchemy.orm import Session

from empire_api.content import offers_state
from empire_api.content.block_refs import LABEL_FIRST
from empire_api.content.common import Editor, audit_row, event, is_production
from empire_api.content.models import Offer
from empire_api.content.page_blocks import pages_naming
from empire_api.content.page_rules import SAMPLE_ON_LIVE_SITE
from empire_api.content.schemas_marketing import OfferInput, OfferUpdate
from empire_api.errors import ApiProblem
from empire_api.media.content_links import library_facts
from empire_api.pagination import PageParams
from empire_api.platform import audit
from empire_api.projects import queries as project_queries
from empire_api.projects.common import Actor, FieldError, conflict, invalid, snapshot
from empire_api.timeutil import IST, utcnow

NO_OFFER: Final = "No offer with this id."
WAS_LIVE: Final = (
    "This offer has been on the website, so it stays for the record. Switch it off instead."
)
CHOOSE_PROJECT: Final = "Choose the project whose page shows this offer."
IMAGE: Final = "Choose an image from the media library."
CTA_PAIR: Final = "A button needs both its label and its link."
ENDS_AFTER: Final = "The end must be after the start."
_AUDIT_SKIP: Final = ("updated_by", "is_live_announced")


@dataclass(frozen=True)
class OfferFilters:
    active_on: date | None = None
    placement: str | None = None
    state: str | None = None
    project_id: uuid.UUID | None = None


def _state_condition(state: str, now: datetime) -> ColumnElement[bool]:
    """SQL twin of offers_state.state_of, for the list filter."""
    ended = and_(Offer.ends_at.is_not(None), Offer.ends_at <= now)
    if state == "ended":
        return ended
    if state == "inactive":
        return and_(~ended, Offer.is_active.is_(False))
    started = or_(Offer.starts_at.is_(None), Offer.starts_at <= now)
    if state == "scheduled":
        return and_(~ended, Offer.is_active.is_(True), ~started)
    return and_(~ended, Offer.is_active.is_(True), started)


def list_offers(
    db: Session, paging: PageParams, filters: OfferFilters, now: datetime
) -> tuple[list[Offer], int]:
    """Highest priority first, then the latest start. `active_on` is an IST day: offers switched
    on whose dates overlap that day."""
    stmt = select(Offer)
    if filters.active_on is not None:
        day_start = datetime.combine(filters.active_on, time.min, IST)
        day_end = day_start + timedelta(days=1)
        stmt = stmt.where(
            Offer.is_active.is_(True),
            or_(Offer.starts_at.is_(None), Offer.starts_at < day_end),
            or_(Offer.ends_at.is_(None), Offer.ends_at > day_start),
        )
    if filters.placement is not None:
        stmt = stmt.where(Offer.placement == filters.placement)
    if filters.project_id is not None:
        stmt = stmt.where(Offer.project_id == filters.project_id)
    if filters.state is not None:
        stmt = stmt.where(_state_condition(filters.state, now))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(
            Offer.priority.desc(),
            Offer.starts_at.desc().nulls_last(),
            Offer.created_at.desc(),
            Offer.id,
        )
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


# --- Validation on merged values -------------------------------------------------------------


def _errors(db: Session, state: Mapping[str, Any], sent: Mapping[str, Any]) -> list[FieldError]:
    errors: list[FieldError] = []
    starts, ends = state.get("starts_at"), state.get("ends_at")
    if starts is not None and ends is not None and ends <= starts:
        errors.append(FieldError("ends_at", ENDS_AFTER))
    if (state.get("cta_label") is None) != (state.get("cta_url") is None):
        field = "cta_url" if state.get("cta_url") is None else "cta_label"
        errors.append(FieldError(field, CTA_PAIR))
    project_id = state.get("project_id")
    if state.get("placement") == "project" and project_id is None:
        errors.append(FieldError("project_id", CHOOSE_PROJECT))
    unknown_project = project_id is not None and project_queries.project_ref(db, project_id) is None
    if "project_id" in sent and unknown_project:
        errors.append(FieldError("project_id", "No project with this id."))
    image_id = state.get("image_media_id")
    if "image_media_id" in sent and image_id is not None:
        found = library_facts(db, [image_id]).get(image_id)
        if found is None or found.kind != "image":
            errors.append(FieldError("image_media_id", IMAGE))
        elif not found.has_label and not found.is_sample:
            errors.append(FieldError("image_media_id", LABEL_FIRST))
    words = (state.get("title"), state.get("body"), state.get("cta_label"), state.get("terms"))
    if offers_state.has_urgency(*words):
        errors.append(FieldError("body", offers_state.NO_URGENCY))
    has_terms = state.get("terms") or state.get("terms_url")
    if offers_state.mentions_money(*words[:3]) and not has_terms:
        errors.append(FieldError("terms", offers_state.TERMS_NEEDED))
    if state.get("is_active") and state.get("is_sample") and is_production():
        errors.append(FieldError("is_active", SAMPLE_ON_LIVE_SITE))
    return errors


def offer_event(
    db: Session, actor: Actor | None, offer: Offer, type_: str, now: datetime, **data: Any
) -> None:
    event(
        db,
        actor,
        type_,
        aggregate_type="offer",
        aggregate_id=offer.id,
        offer_id=offer.id,
        placement=offer.placement,
        project_id=offer.project_id,
        state=offers_state.state_of(offer, now),
        **data,
    )


def announce(db: Session, actor: Actor | None, offer: Offer, now: datetime) -> str | None:
    """Send `offer.started` or `offer.ended` if the offer's live state changed since the last
    announcement. Returns the event type sent, if any. No commit."""
    live = offers_state.is_live(offer, now)
    if live and not offer.is_live_announced:
        offer.is_live_announced = True
        offer.went_live_at = offer.went_live_at or now
        offer_event(db, actor, offer, "offer.started", now)
        return "offer.started"
    if not live and offer.is_live_announced:
        offer.is_live_announced = False
        offer_event(db, actor, offer, "offer.ended", now)
        return "offer.ended"
    return None


# --- Create, update, delete ------------------------------------------------------------------


def create_offer(db: Session, editor: Editor, body: OfferInput) -> Offer:
    values = body.model_dump()
    errors = _errors(db, values, values)
    if errors:
        raise invalid(errors)
    offer = Offer(**values, created_by=editor.user_id, updated_by=editor.user_id)
    db.add(offer)
    db.flush()
    now = utcnow()
    audit_row(
        db,
        editor,
        action="offer.created",
        entity_type="offer",
        entity_id=offer.id,
        changes=audit.diff({}, snapshot(offer, _AUDIT_SKIP)),
    )
    announce(db, editor, offer, now)
    db.commit()
    return offer


def _locked(db: Session, offer_id: uuid.UUID) -> Offer:
    offer = db.get(Offer, offer_id, with_for_update=True, populate_existing=True)
    if offer is None:
        raise ApiProblem(404, NO_OFFER)
    return offer


def update_offer(db: Session, editor: Editor, offer_id: uuid.UUID, body: OfferUpdate) -> Offer:
    offer = _locked(db, offer_id)
    sent = body.model_dump(exclude_unset=True)
    state = {column.key: getattr(offer, column.key) for column in Offer.__table__.columns}
    state |= sent
    errors = _errors(db, state, sent)
    if errors:
        raise invalid(errors)
    now = utcnow()
    was_live = offers_state.is_live(offer, now)
    before = snapshot(offer, _AUDIT_SKIP)
    for key, value in sent.items():
        setattr(offer, key, value)
    db.flush()
    diff = audit.diff(before, snapshot(offer, _AUDIT_SKIP))
    if not diff:
        db.rollback()
        return _locked(db, offer_id)
    offer.updated_by = editor.user_id
    audit_row(
        db, editor, action="offer.updated", entity_type="offer", entity_id=offer.id, changes=diff
    )
    announce(db, editor, offer, now)
    if was_live or offers_state.is_live(offer, now):
        offer_event(db, editor, offer, "offer.changed", now)
    db.commit()
    return offer


def delete_offer(db: Session, editor: Editor, offer_id: uuid.UUID) -> None:
    """Delete an offer that was never on the website and that no page block shows."""
    offer = _locked(db, offer_id)
    if offer.went_live_at is not None or offer.is_live_announced:
        raise conflict(WAS_LIVE)
    blocks = pages_naming(db, "offer_id", offer.id)
    if blocks:
        raise conflict(
            "A page shows this offer in a block. Change or remove that block first.",
            "offer_id",
        )
    audit_row(
        db,
        editor,
        action="offer.deleted",
        entity_type="offer",
        entity_id=offer.id,
        changes={k: [v, None] for k, v in snapshot(offer, _AUDIT_SKIP).items()},
    )
    db.delete(offer)
    db.commit()
