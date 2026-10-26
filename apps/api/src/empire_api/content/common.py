"""Helpers shared by the content module's services: who is acting and what their role allows,
audit rows and outbox events that also work for the schedule tick (no person acting), the
draft-text check and the production switch.

Collaborators: pages.py, page_blocks.py, posts.py, faqs.py, offers.py, testimonials.py,
schedule.py; projects/common.py (Actor, record helpers); users/roles.py (the matrix).
Implements: ARCHITECTURE §9 (events in the same transaction), §11 (permissions, audit).

INVARIANT: helpers here only add to the caller's session; the service commits once, so a change,
its audit row and its event are saved together or not at all.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.errors import ApiProblem
from empire_api.platform import audit, outbox
from empire_api.platform.crypto import client_ip
from empire_api.projects.common import Actor, jsonable
from empire_api.users.roles import has_permission, permissions_for
from empire_api.users.sessions import SessionInfo


@dataclass(frozen=True)
class Editor(Actor):
    """A signed-in staff member with every permission their role holds.

    WHY: one content request can need several permissions at once: a PATCH that archives a
    live legal page needs `content.write` (the route), `content.publish` (it leaves the site)
    and `legal.publish` (it is legal text). The route checks the first; services check the rest
    with `can()`, always against the same matrix (users/roles.py).
    """

    permissions: frozenset[str] = frozenset()

    def can(self, permission: str) -> bool:
        return permission in self.permissions

    def need(self, permission: str, message: str) -> None:
        """SECURITY: 403 unless the role holds `permission`."""
        if not self.can(permission):
            raise ApiProblem(403, message)


def editor_of(info: SessionInfo, request: Request) -> Editor:
    role = info.user.role
    return Editor(
        user_id=info.user.id,
        ip=client_ip(request),
        can_publish=has_permission(role, "content.publish"),
        permissions=frozenset(permissions_for(role)),
    )


def actor_id(actor: Actor | None) -> uuid.UUID | None:
    return actor.user_id if actor else None


def audit_row(
    db: Session,
    actor: Actor | None,
    *,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    changes: dict[str, Any],
) -> None:
    """An audit row; `actor` None means the schedule tick (no person acting)."""
    audit.record(
        db,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id(actor),
        ip=actor.ip if actor else None,
        changes=jsonable(changes),
    )


def event(
    db: Session,
    actor: Actor | None,
    type_: str,
    *,
    aggregate_type: str,
    aggregate_id: uuid.UUID,
    **data: Any,
) -> None:
    """An outbox event (ARCHITECTURE §9). Content events carry ids, slugs and paths only."""
    outbox.emit(
        db,
        type_=type_,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        actor_id=actor_id(actor),
        data=jsonable(data),
    )


def is_production() -> bool:
    return get_settings().app_env == "production"


def has_draft_mark(*texts: str | None) -> bool:
    """COMPLIANCE (D-017): the text still says it is a draft awaiting the owner's approval.

    Same test as consent texts (consent.is_draft): any "[draft" mark, in any case.
    """
    return any("[draft" in (text or "").lower() for text in texts)
