"""The schedule tick: scheduled page publish/unpublish and offer start/end (ARCHITECTURE §10).

Collaborators: integrations/outbox_drain.py and worker.py (run it before each drain, every 15
minutes on free hosting); pages.py (go_live, take_down), page_rules.py (blockers), offers.py
(announce).
Implements: ARCHITECTURE §9 (`page.published` / `page.unpublished`, `offer.started` /
`offer.ended`), §10; D-015, D-017.

How it works:
  1. Lock due pages with FOR UPDATE SKIP LOCKED, so two ticks (the worker loop and a scheduler
     call) never handle the same row twice.
  2. A draft whose `publish_at` has passed goes live, unless its window has already closed
     (`unpublish_at` passed too: both are cleared, nothing is published) or a blocker remains
     (sample data or draft legal text in production): then `publish_at` is cleared and the
     reason audited, so the CMS stops showing it as scheduled.
  3. A live page whose `unpublish_at` has passed goes back to draft.
  4. Offers switched on, or announced as live, get `offer.started` / `offer.ended` when their
     live state changed (offers.announce sends each once).
  5. One commit for the whole tick; events go out with the drain that follows.

INVARIANT: the person who scheduled a page had the permission to publish it when they saved the
schedule (pages._check_rights); the tick only carries out that decision, as nobody (`actor`
None in the audit log). For legal pages that holds for the wording too: while `publish_at` is
set, any change to a legal page needs `legal.publish` (page_rules.legal_guarded, review H2), so
what goes live is what a `legal.publish` holder scheduled. A take-down clears `publish_at`
(pages.take_down, review M2), so only a deliberate schedule ever brings a page back.
PERF: a handful of indexed-by-size tiny tables; one short transaction every 15 minutes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from empire_api.content import page_rules
from empire_api.content.common import audit_row
from empire_api.content.models import Offer, Page
from empire_api.content.offers import announce
from empire_api.content.pages import go_live, take_down
from empire_api.db import get_sessionmaker
from empire_api.logs import get_logger
from empire_api.timeutil import utcnow

log = get_logger(__name__)


@dataclass(frozen=True)
class TickResult:
    published: int
    unpublished: int
    skipped: int
    offers_started: int
    offers_ended: int


def _due_pages(db: Session, now: datetime) -> list[Page]:
    return list(
        db.scalars(
            select(Page)
            .where(
                or_(
                    (Page.publish_state == "draft") & (Page.publish_at <= now),
                    (Page.publish_state == "published") & (Page.unpublish_at <= now),
                )
            )
            .order_by(Page.id)
            .with_for_update(skip_locked=True)
        )
    )


def _skip(db: Session, page: Page, reason: str) -> None:
    """COMPLIANCE: a scheduled publish that can't happen is cancelled and recorded, never
    forced through."""
    page.publish_at = None
    if reason == "window_passed":
        page.unpublish_at = None
    audit_row(
        db,
        None,
        action="page.scheduled_publish_cancelled",
        entity_type="page",
        entity_id=page.id,
        changes={"publish_at": ["scheduled", None], "reason": [None, reason]},
    )


def run_pages(db: Session, now: datetime) -> tuple[int, int, int]:
    published = unpublished = skipped = 0
    for page in _due_pages(db, now):  # 1
        if page.publish_state == "draft":  # 2
            if page.unpublish_at is not None and page.unpublish_at <= now:
                _skip(db, page, "window_passed")
                skipped += 1
                continue
            blockers = page_rules.page_blockers(page)
            if blockers:
                _skip(db, page, "; ".join(blockers))
                skipped += 1
                continue
            go_live(db, None, page, scheduled=True)
            published += 1
        else:  # 3
            take_down(db, None, page, scheduled=True)
            unpublished += 1
    return published, unpublished, skipped


def run_offers(db: Session, now: datetime) -> tuple[int, int]:
    candidates = db.scalars(
        select(Offer)
        .where(or_(Offer.is_active.is_(True), Offer.is_live_announced.is_(True)))
        .order_by(Offer.id)
        .with_for_update(skip_locked=True)
    )
    started = ended = 0
    for offer in candidates:  # 4
        sent = announce(db, None, offer, now)
        started += sent == "offer.started"
        ended += sent == "offer.ended"
    return started, ended


def schedule_tick(now: datetime | None = None) -> TickResult:
    """Run the tick once (module header). Safe to run from several processes at once."""
    now = now or utcnow()
    with get_sessionmaker()() as db, db.begin():  # 5
        published, unpublished, skipped = run_pages(db, now)
        started, ended = run_offers(db, now)
    result = TickResult(published, unpublished, skipped, started, ended)
    if any((published, unpublished, skipped, started, ended)):
        log.info(
            "schedule_tick",
            pages_published=published,
            pages_unpublished=unpublished,
            pages_skipped=skipped,
            offers_started=started,
            offers_ended=ended,
        )
    return result
