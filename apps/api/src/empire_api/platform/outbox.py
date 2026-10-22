"""Outbox writer: record an event in the caller's transaction (ARCHITECTURE §9, D-010).

Delivery (claiming, retries, handlers) lives in integrations/outbox_drain.py.

INVARIANT: `emit()` only adds to the given session; it never commits. The event exists if and
only if the change that caused it was committed. That is the whole point of an outbox.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from empire_api.platform.models import OutboxEvent


def emit(
    db: Session,
    *,
    type_: str,
    aggregate_type: str,
    aggregate_id: str | uuid.UUID,
    data: dict[str, Any] | None = None,
    actor_id: uuid.UUID | None = None,
    contains_personal_data: bool = False,
) -> OutboxEvent:
    event = OutboxEvent(
        type=type_,
        aggregate_type=aggregate_type,
        aggregate_id=str(aggregate_id),
        payload=data or {},
        actor_id=actor_id,
        contains_personal_data=contains_personal_data,
    )
    db.add(event)
    return event
