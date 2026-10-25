"""Business rules for testimonials: real buyers' words, shown only with a source and consent.

Collaborators: common.py (audit, events), page_blocks.py (a deleted testimonial leaves every
block that picked it), media/content_links.py (the photo is a library image),
projects/queries.py, routes_marketing.py.
Implements: ARCHITECTURE §9 (`testimonial.changed`), §11 (writing needs `content.publish`, as in
the design contract); AGENTS.md "Honest content".

Rules:
  - COMPLIANCE: real testimonials only. Showing one (`is_visible`) needs `source` and
    `consent_date` (also a CHECK constraint). A consent date can't be in the future. There is
    no sample testimonial anywhere: the table has no sample flag and the seed adds none, so the
    website's section stays hidden until a real one is shown (honest empty state).
  - Rating is optional, 1–5.
  - Deleting is always allowed (a buyer may withdraw consent): the testimonial leaves every
    block at once, and live pages are revalidated.
  - SECURITY.md §8: the audit log is never edited, so it must not keep a person's name or words
    after a deletion. Audit diffs record `[hidden]` for the name, detail, quote, source and
    source link (staff type names into `source`, e.g. "WhatsApp from Ravi, 2 Mar"; review L9).
  - The photo needs no honest label (review L11): it shows the person, not a property, so it
    can't pass for a photo of a building. Offer images and post covers do need one.
  - `testimonial.changed` is emitted when it is shown before or after the change.

INVARIANT: every function commits once, after its audit row and events.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.content.common import Editor, audit_row, event
from empire_api.content.models import Testimonial
from empire_api.content.page_blocks import drop_reference
from empire_api.content.schemas_marketing import TestimonialInput, TestimonialUpdate
from empire_api.errors import ApiProblem
from empire_api.media.content_links import library_facts
from empire_api.pagination import PageParams
from empire_api.platform import audit
from empire_api.projects import queries as project_queries
from empire_api.projects.common import Actor, FieldError, invalid, snapshot

NO_TESTIMONIAL: Final = "No testimonial with this id."
SHOW_NEEDS_CONSENT: Final = (
    "Record where it came from and the date the person agreed to publishing before showing "
    "it on the website."
)
PHOTO: Final = "Choose an image from the media library."
HIDDEN: Final = "[hidden]"
# SECURITY.md §8: personal words never enter the (never edited) audit log.
_PERSONAL: Final = frozenset({"person_name", "person_detail", "quote", "source", "source_url"})
_AUDIT_SKIP: Final = ("updated_by",)


def _masked(values: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: (HIDDEN if key in _PERSONAL and value is not None else value)
        for key, value in values.items()
    }


def _diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[Any]]:
    """Which fields changed, with personal values hidden (a changed quote shows as changed)."""
    diff = audit.diff(dict(before), dict(after))
    return {key: ([HIDDEN, HIDDEN] if key in _PERSONAL else value) for key, value in diff.items()}


def list_testimonials(
    db: Session, paging: PageParams, project_id: uuid.UUID | None, is_visible: bool | None
) -> tuple[list[Testimonial], int]:
    stmt = select(Testimonial)
    if project_id is not None:
        stmt = stmt.where(Testimonial.project_id == project_id)
    if is_visible is not None:
        stmt = stmt.where(Testimonial.is_visible.is_(is_visible))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(Testimonial.created_at.desc(), Testimonial.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


def _errors(db: Session, state: Mapping[str, Any], sent: Mapping[str, Any]) -> list[FieldError]:
    errors: list[FieldError] = []
    if state.get("is_visible") and not (
        state.get("consent_date") and len((state.get("source") or "").strip()) >= 3
    ):
        errors.append(FieldError("is_visible", SHOW_NEEDS_CONSENT))
    project_id = state.get("project_id")
    unknown_project = project_id is not None and project_queries.project_ref(db, project_id) is None
    if "project_id" in sent and unknown_project:
        errors.append(FieldError("project_id", "No project with this id."))
    photo_id = state.get("photo_media_id")
    if "photo_media_id" in sent and photo_id is not None:
        found = library_facts(db, [photo_id]).get(photo_id)
        if found is None or found.kind != "image":
            errors.append(FieldError("photo_media_id", PHOTO))
    return errors


def testimonial_event(
    db: Session, actor: Actor | None, row: Testimonial, change: str, **data: Any
) -> None:
    """`testimonial.changed`. Ids only: the person's name and words stay out of event payloads.
    Also sent by media_changes.py when the photo's details change."""
    event(
        db,
        actor,
        "testimonial.changed",
        aggregate_type="testimonial",
        aggregate_id=row.id,
        testimonial_id=row.id,
        project_id=row.project_id,
        is_visible=row.is_visible,
        change=change,
        **data,
    )


def create_testimonial(db: Session, editor: Editor, body: TestimonialInput) -> Testimonial:
    values = body.model_dump()
    errors = _errors(db, values, values)
    if errors:
        raise invalid(errors)
    row = Testimonial(**values, created_by=editor.user_id, updated_by=editor.user_id)
    db.add(row)
    db.flush()
    audit_row(
        db,
        editor,
        action="testimonial.created",
        entity_type="testimonial",
        entity_id=row.id,
        changes=audit.diff({}, _masked(snapshot(row, _AUDIT_SKIP))),
    )
    if row.is_visible:
        testimonial_event(db, editor, row, "created")
    db.commit()
    return row


def _locked(db: Session, testimonial_id: uuid.UUID) -> Testimonial:
    row = db.get(Testimonial, testimonial_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise ApiProblem(404, NO_TESTIMONIAL)
    return row


def update_testimonial(
    db: Session, editor: Editor, testimonial_id: uuid.UUID, body: TestimonialUpdate
) -> Testimonial:
    row = _locked(db, testimonial_id)
    sent = body.model_dump(exclude_unset=True)
    state = {column.key: getattr(row, column.key) for column in Testimonial.__table__.columns}
    errors = _errors(db, state | sent, sent)
    if errors:
        raise invalid(errors)
    before = snapshot(row, _AUDIT_SKIP)
    was_visible = row.is_visible
    for key, value in sent.items():
        setattr(row, key, value)
    db.flush()
    diff = _diff(before, snapshot(row, _AUDIT_SKIP))
    if not diff:
        db.rollback()
        return _locked(db, testimonial_id)
    row.updated_by = editor.user_id
    audit_row(
        db,
        editor,
        action="testimonial.updated",
        entity_type="testimonial",
        entity_id=row.id,
        changes=diff,
    )
    if was_visible or row.is_visible:
        testimonial_event(db, editor, row, "updated")
    db.commit()
    return row


def delete_testimonial(db: Session, editor: Editor, testimonial_id: uuid.UUID) -> None:
    """Delete it and take it out of every block that picked it (module rules)."""
    row = _locked(db, testimonial_id)
    drop_reference(db, editor, "testimonial_ids", row.id)
    audit_row(
        db,
        editor,
        action="testimonial.deleted",
        entity_type="testimonial",
        entity_id=row.id,
        changes={k: [v, None] for k, v in _masked(snapshot(row, _AUDIT_SKIP)).items()},
    )
    if row.is_visible:
        testimonial_event(db, editor, row, "deleted")
    db.delete(row)
    db.commit()
