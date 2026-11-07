"""Outbox handlers that keep the knowledge index fresh (task 7.1, D-059).

Each content event re-indexes the one item it names; the indexer skips unchanged text, so the
many events one save can emit cost one embedding at most. Project, FAQ, offer and testimonial
events also re-check every page, since pages show them (unchanged pages cost nothing), and the
daily clean-up queues everything once as a backstop.

Two steps: a content event queues one `ai.reindex` event per item (no network), and that
event does the work. Nothing happens while AI is off (`AI_PROVIDER` unset) or where pgvector
isn't installed. A busy provider retries `ai.reindex` on the outbox schedule; a refused request
is dead at once. Neither touches the content event, so revalidation never waits for the AI.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.ai import indexer, knowledge, store
from empire_api.ai.providers import get_provider
from empire_api.ai.providers.base import ProviderBusyError, ProviderError
from empire_api.content.models import Page
from empire_api.integrations.handlers import PermanentDeliveryError, on
from empire_api.logs import get_logger
from empire_api.platform import outbox
from empire_api.platform.models import OutboxEvent

log = get_logger(__name__)
REINDEX_EVENT: Final = "ai.reindex"

PROJECT_EVENTS: Final = (
    "project.published",
    "project.updated",
    "project.unpublished",
    "project.archived",
    "project.restored",
    "project.deleted",
    "project.amenities_set",
    "configuration.changed",
    "construction_update.published",
)
# Pages show projects (grids, map), FAQs, offers and testimonials, so these re-check every page
# too. Unchanged pages cost no neurons (content hashes).
PAGE_WIDE_EVENTS: Final = ("offer.started", "offer.ended", "offer.changed", "testimonial.changed")
PAGE_EVENTS: Final = (
    "page.published",
    "page.updated",
    "page.unpublished",
    "page.archived",
    "page.restored",
    "page.deleted",
    "page.blocks_saved",
)
POST_EVENTS: Final = (
    "post.published",
    "post.updated",
    "post.unpublished",
    "post.archived",
    "post.restored",
    "post.deleted",
)


def _uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _pages(db: Session) -> list[tuple[str, uuid.UUID]]:
    return [("page", page_id) for page_id in db.scalars(select(Page.id).order_by(Page.id))]


def _targets(db: Session, event: OutboxEvent) -> list[tuple[str, uuid.UUID]]:
    # WHY the payload for projects and FAQs: child events (a configuration, an FAQ) carry the
    # child as their aggregate, and the project's id in `project_id`.
    project_id = _uuid(event.payload.get("project_id"))
    if event.type in PROJECT_EVENTS or event.type == "faq.changed":
        own = [("project", project_id)] if project_id else []
        return own + _pages(db)
    if event.type in PAGE_WIDE_EVENTS:
        return _pages(db)
    source_id = _uuid(event.aggregate_id)
    if event.aggregate_type in ("page", "post") and source_id:
        return [(event.aggregate_type, source_id)]
    return []


def queue_reindex(db: Session, event: OutboxEvent) -> None:
    """Emit one `ai.reindex` per item the content event names. Never calls the provider.

    WHY a separate event: a busy provider must not fail the content event itself, or the
    website's revalidation and the other handlers on it would wait for the retry (up to a day).
    """
    if get_provider() is None or not store.available(db):
        return
    for source_type, source_id in _targets(db, event):
        _queue(db, source_type, source_id)


def _queue(db: Session, source_type: str, source_id: uuid.UUID) -> None:
    outbox.emit(
        db,
        type_=REINDEX_EVENT,
        aggregate_type=source_type,
        aggregate_id=source_id,
        data={"source_type": source_type, "source_id": str(source_id)},
    )


@on(REINDEX_EVENT)
def reindex(db: Session, event: OutboxEvent) -> None:
    provider = get_provider()
    source_type = str(event.payload.get("source_type", ""))
    source_id = _uuid(event.payload.get("source_id"))
    if provider is None or source_id is None or not store.available(db):
        return  # AI switched off since the event was queued: nothing to do
    try:
        indexer.reindex_source(db, provider, source_type, source_id)
    except ProviderBusyError as exc:
        # WHY a plain error: the drain retries it later; the message is a code only.
        raise RuntimeError(f"ai_busy_{exc}") from None
    except ProviderError as exc:
        log.warning("ai.index_refused", event_type=event.type, code=str(exc))
        raise PermanentDeliveryError(f"ai_refused_{exc}") from None


def queue_everything(db: Session) -> int:
    """The daily backstop (outbox_drain.cleanup): one `ai.reindex` per item, including items
    that are gone, for what no event announces (a city or amenity renamed, a sample hidden by
    a setting). Unchanged items cost no neurons. Returns how many were queued."""
    if get_provider() is None or not store.available(db):
        return 0
    targets = {(kind, item.id) for kind, item in knowledge.all_sources(db)}
    targets.update(store.sources(db))
    for source_type, source_id in sorted(targets, key=str):
        _queue(db, source_type, source_id)
    return len(targets)


for _event_type in (
    *PROJECT_EVENTS,
    *PAGE_EVENTS,
    *POST_EVENTS,
    *PAGE_WIDE_EVENTS,
    "faq.changed",
):
    on(_event_type)(queue_reindex)
