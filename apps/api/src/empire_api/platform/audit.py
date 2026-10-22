"""Audit-log writer (ARCHITECTURE §11: every create, update, delete, publish, export, login and
permission change writes a row).

Call `record()` with the request's session BEFORE committing, so the audit row and the change
commit together or not at all.

INVARIANT: never put passwords, tokens or full phone numbers in `changes`.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from empire_api.platform.crypto import mask_ip
from empire_api.platform.models import AuditLog


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, list[Any]]:
    """{'role': ['sales', 'admin']} for each key whose value changed."""
    return {k: [before.get(k), after.get(k)] for k in after if before.get(k) != after.get(k)}


def record(
    db: Session,
    *,
    action: str,
    entity_type: str,
    entity_id: str | uuid.UUID,
    actor_id: uuid.UUID | None,
    ip: str | None = None,
    changes: dict[str, Any] | None = None,
) -> AuditLog:
    row = AuditLog(
        actor_user_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id),
        changes=changes or {},
        ip=mask_ip(ip),
    )
    db.add(row)
    return row
