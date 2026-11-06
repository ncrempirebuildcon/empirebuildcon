"""CMS changes reach the website at once, not at the next 15-minute sweep (task L7a)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.platform.models import OutboxEvent
from projects_support import create_project, make_ready, ok, publish


def _events(db: Session, project_id: str, type_: str) -> list[OutboxEvent]:
    db.expire_all()
    return list(
        db.scalars(
            select(OutboxEvent).where(
                OutboxEvent.aggregate_id == project_id, OutboxEvent.type == type_
            )
        )
    )


def test_publishing_a_project_delivers_its_event_straight_away(
    owner: SignedIn, db: Session, qr_present: None
) -> None:
    project = create_project(owner, "Deliver Soon Heights")
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    [published] = _events(db, project["id"], "project.published")
    assert published.status == "delivered"
