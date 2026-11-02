"""Outbox event handlers: who reacts to which event (ARCHITECTURE §9 consumer column).

Register with the decorator; handlers receive the open session and the event row:

    @on("lead.created")
    def email_sales(db: Session, event: OutboxEvent) -> None: ...

INVARIANT: delivery is at-least-once (a crash after a handler ran but before the row was marked
delivered runs it again), so every handler must be idempotent, e.g. keyed on `event.event_id`.

A handler that fails raises: any exception is retried on the drain's schedule, except
`PermanentDeliveryError`, which marks the event dead at once with an alert log line (a retry
can't help, e.g. the email provider refused the message as invalid).

Handlers: a structured log line per event (here), media clean-up (media/handlers.py),
emails (mail/handlers.py: password links, security notices, lead and visit alerts; a lead alert
only when `data.alert` is true, ARCHITECTURE §8), and web cache revalidation (revalidation.py).
TODO(phase-6): webhooks and WhatsApp.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable

from sqlalchemy.orm import Session

from empire_api.integrations.revalidation import REVALIDATION_EVENTS, handle_revalidation
from empire_api.logs import get_logger
from empire_api.platform.models import OutboxEvent

Handler = Callable[[Session, OutboxEvent], None]


class PermanentDeliveryError(Exception):
    """A failure no retry can fix. SECURITY: the message is stored in `last_error` and logged,
    so it must name a reason only (an error code), never an address, link or personal data."""


WILDCARD = "*"

_registry: defaultdict[str, list[Handler]] = defaultdict(list)
log = get_logger(__name__)


def on(event_type: str) -> Callable[[Handler], Handler]:
    def decorator(fn: Handler) -> Handler:
        _registry[event_type].append(fn)
        return fn

    return decorator


def handlers_for(event_type: str) -> list[Handler]:
    all_handlers = [*_registry.get(WILDCARD, []), *_registry.get(event_type, [])]
    # Ensure revalidation runs after domain handlers (e.g. media destruction) (M2)
    domain_handlers = [h for h in all_handlers if h is not handle_revalidation]
    reval_handlers = [h for h in all_handlers if h is handle_revalidation]
    return [*domain_handlers, *reval_handlers]


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


for _ev in REVALIDATION_EVENTS:
    on(_ev)(handle_revalidation)
