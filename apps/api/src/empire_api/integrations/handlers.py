"""Outbox event handlers: who reacts to which event (ARCHITECTURE §9 consumer column).

Register with the decorator; handlers receive the open session and the event row:

    @on("lead.created")
    def email_sales(db: Session, event: OutboxEvent) -> None: ...

INVARIANT: delivery is at-least-once (a crash after a handler ran but before the row was marked
delivered runs it again), so every handler must be idempotent, e.g. keyed on `event.event_id`.

Phase 3 has one handler: a structured log line per event, so delivery can be watched.
TODO(phase-4): email for `user.setup_link_issued` / `user.password_reset_requested`.
TODO(phase-4): part 5 emails the sales inbox (or the owner) on `lead.created`, but ONLY when
`data.alert` is true: duplicates (same phone and project within 24 h), manual leads and samples
carry `alert: false` and must not alert again (ARCHITECTURE §8). Also email the new owner on
`lead.assigned`, and sales on `site_visit.requested`.
TODO(phase-5): web revalidation on publish events. TODO(phase-6): webhooks and WhatsApp.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from sqlalchemy.orm import Session

from empire_api.logs import get_logger
from empire_api.platform.models import OutboxEvent

Handler = Callable[[Session, OutboxEvent], None]
WILDCARD = "*"

_registry: defaultdict[str, list[Handler]] = defaultdict(list)
log = get_logger(__name__)


def on(event_type: str) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        _registry[event_type].append(fn)
        return fn

    return decorator


def handlers_for(event_type: str) -> list[Handler]:
    return [*_registry.get(WILDCARD, []), *_registry.get(event_type, [])]


@on(WILDCARD)
def log_event(db: Session, event: OutboxEvent) -> None:
    """Log that an event was delivered. COMPLIANCE: ids only, never the payload (personal data)."""
    log.info(
        "outbox_event_delivered",
        event_type=event.type,
        event_id=str(event.event_id),
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        attempt=event.attempts + 1,
    )
