"""Outbox events of the media module (ARCHITECTURE §9).

- `media.added`: a file entered the library (upload or confirmed direct upload), maybe attached.
- `media.updated`: an existing file or one of its links changed: attached, detached, shown,
  hidden, pinned as cover, reordered, renamed, alt text or label.
- `media.removed`: the file left the library; integrations runs media/handlers.py, which
  destroys it at the store (with the outbox's retries).
- `media.upload_discarded`: a direct upload that was refused or never confirmed; the same
  handler destroys it under every resource type, now and again once its signature has died.
Plus, when the owner's project is on the website, the event the projects module uses for that
owner: `configuration.changed` for a configuration's floor plan, `project.updated` otherwise.

INVARIANT: events only join the caller's session (platform/outbox.py); nothing here commits.
No personal data is ever included.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.orm import Session

from empire_api.media.models import Media, MediaLink, UploadIntent
from empire_api.media.rules import CHANGED_FIELD, Owner
from empire_api.media.vocab import CLOCK_SKEW_SECONDS, INTENT_TTL_SECONDS
from empire_api.platform import outbox
from empire_api.projects.common import Actor, emit
from empire_api.projects.models import Project
from empire_api.timeutil import utcnow


def media_event(
    db: Session,
    actor: Actor,
    type_: str,
    media: Media,
    change: str,
    *,
    link: MediaLink | None = None,
    project: Project | None = None,
) -> None:
    data: dict[str, Any] = {"media_id": str(media.id), "kind": media.kind, "change": change}
    if link is not None:
        owner = Owner.of(link)
        data |= {
            "link_id": str(link.id),
            "role": link.role,
            "owner_type": owner.type,
            "owner_id": str(owner.id),
        }
    if project is not None:
        data |= {"project_id": str(project.id), "slug": project.slug}
    outbox.emit(
        db,
        type_=type_,
        aggregate_type="media",
        aggregate_id=media.id,
        actor_id=actor.user_id,
        data=data,
    )


def list_reordered(db: Session, actor: Actor, owner: Owner, role: str, project: Project) -> None:
    """One `media.updated` for a whole list's new order (the aggregate is the owner)."""
    outbox.emit(
        db,
        type_="media.updated",
        aggregate_type=owner.type,
        aggregate_id=owner.id,
        actor_id=actor.user_id,
        data={
            "change": "reordered",
            "role": role,
            "owner_type": owner.type,
            "owner_id": str(owner.id),
            "project_id": str(project.id),
            "slug": project.slug,
        },
    )


def owner_changed(
    db: Session, actor: Actor, project: Project, owner: Owner, role: str, change: str
) -> None:
    """The owner's own event, only while its project is published (revalidate its pages)."""
    if project.publish_state != "published":
        return
    if owner.type == "configuration":
        emit(
            db,
            actor,
            project,
            "configuration.changed",
            aggregate_type="configuration",
            aggregate_id=owner.id,
            change=f"media_{change}",
        )
        return
    emit(
        db,
        actor,
        project,
        "project.updated",
        changed=[CHANGED_FIELD[(owner.type, role)]],
        change=f"media_{change}",
    )


def removed(db: Session, actor: Actor, media: Media) -> None:
    """The file was deleted from the library: the handler destroys it at the store."""
    outbox.emit(
        db,
        type_="media.removed",
        aggregate_type="media",
        aggregate_id=media.id,
        actor_id=actor.user_id,
        data=destroy_payload(media.store, media.resource_type, media.public_id)
        | {"media_id": str(media.id), "kind": media.kind},
    )


def upload_discarded(
    db: Session,
    intent: UploadIntent,
    store: str,
    reason: str,
    actor_id: uuid.UUID | None,
    now: datetime | None = None,
) -> None:
    """A direct upload that won't be saved: the handler destroys whatever reached the store.

    SECURITY: while the intent's signature is still alive at the store (an hour after it was
    signed), the browser could upload the file again after the first destroy. A second
    destroy is therefore scheduled for when the signature has died (plus clock skew); the
    outbox sweep runs it.
    """
    data = destroy_payload(store, intent.resource_type, intent.public_id) | {"reason": reason}
    outbox.emit(
        db,
        type_="media.upload_discarded",
        aggregate_type="upload_intent",
        aggregate_id=intent.id,
        actor_id=actor_id,
        data=data,
    )
    signature_dead = intent.created_at + timedelta(seconds=INTENT_TTL_SECONDS + CLOCK_SKEW_SECONDS)
    if signature_dead > (now or utcnow()):
        again = outbox.emit(
            db,
            type_="media.upload_discarded",
            aggregate_type="upload_intent",
            aggregate_id=intent.id,
            actor_id=actor_id,
            data=data | {"second_pass": True},
        )
        again.available_at = signature_dead


def destroy_payload(store: str, resource_type: str, public_id: str) -> dict[str, str]:
    return {"store": store, "resource_type": resource_type, "public_id": public_id}
