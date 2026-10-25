"""Business rules for FAQs: site-wide or per project, ordered, shown or hidden.

Collaborators: common.py (Editor, audit, events), page_blocks.py (a deleted FAQ leaves every
faq_list block), projects/queries.py (project names and slugs), routes_marketing.py,
projects/routes.py (ProjectAdmin.faqs, through `project_faqs`).
Implements: ARCHITECTURE §9 (`faq.changed`), §11; part 1's TODO (FAQs on ProjectAdmin).

Rules:
  - Writing needs `content.write` (the route). Showing an FAQ on the website (`is_visible`
    true, on create or by a change) needs `content.publish`, because ARCHITECTURE §11 lists
    FAQs under "publish pages, posts, FAQs, testimonials" (D-035). Editing the text of a shown
    FAQ stays with `content.write`, as editing a live page or project does.
  - A new FAQ goes to the end of its list (site-wide, or its project's) unless `sort_order` is
    given; moving it to another project puts it at the end there. Reorder sends the full list.
  - `faq.changed` is emitted when the FAQ is shown before or after the change.

INVARIANT: every function commits once, after its audit row and events.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from empire_api.content import present
from empire_api.content.common import Editor, audit_row, event
from empire_api.content.models import Faq
from empire_api.content.page_blocks import drop_reference
from empire_api.content.schemas_marketing import Faq as FaqOut
from empire_api.content.schemas_marketing import FaqInput, FaqUpdate
from empire_api.errors import ApiProblem
from empire_api.pagination import PageParams
from empire_api.platform import audit
from empire_api.projects import queries as project_queries
from empire_api.projects.common import FieldError, commit, invalid, snapshot

NO_FAQ: Final = "No FAQ with this id."
NO_PROJECT: Final = "No project with this id."
SHOW_NEEDS_PUBLISH: Final = "Your role can't show FAQs on the website (content.publish)."
FULL_LIST: Final = "Send every FAQ of this list exactly once, in the new order."
_AUDIT_SKIP: Final = ("updated_by",)


def _group(project_id: uuid.UUID | None) -> ColumnElement[bool]:
    return Faq.project_id.is_(None) if project_id is None else Faq.project_id == project_id


def list_faqs(
    db: Session, paging: PageParams, project_id: uuid.UUID | None, site_wide: bool
) -> tuple[list[Faq], int]:
    """Site-wide first, then by project, each in its order. Filters: one project, or only the
    site-wide ones."""
    stmt = select(Faq)
    if project_id is not None:
        stmt = stmt.where(Faq.project_id == project_id)
    elif site_wide:
        stmt = stmt.where(Faq.project_id.is_(None))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(Faq.project_id.nulls_first(), Faq.sort_order, Faq.created_at, Faq.id)
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


def project_faqs(db: Session, project_id: uuid.UUID) -> list[FaqOut]:
    """A project's FAQs in their order, hidden ones included (ProjectAdmin.faqs)."""
    rows = db.scalars(
        select(Faq).where(Faq.project_id == project_id).order_by(Faq.sort_order, Faq.created_at)
    ).all()
    return present.faqs_out(db, rows)


def _next_order(db: Session, project_id: uuid.UUID | None) -> int:
    last = db.scalar(select(func.max(Faq.sort_order)).where(_group(project_id)))
    return 0 if last is None else int(last) + 1


def _check_project(db: Session, project_id: uuid.UUID | None) -> None:
    if project_id is not None and project_queries.project_ref(db, project_id) is None:
        raise invalid([FieldError("project_id", NO_PROJECT)])


def _event(db: Session, editor: Editor, faq: Faq, change: str) -> None:
    """`faq.changed`: revalidate the project page (or the site-wide FAQ page) and FAQ data."""
    ref = project_queries.project_ref(db, faq.project_id) if faq.project_id else None
    event(
        db,
        editor,
        "faq.changed",
        aggregate_type="faq",
        aggregate_id=faq.id,
        faq_id=faq.id,
        project_id=faq.project_id,
        project_slug=ref.slug if ref else None,
        change=change,
    )


def create_faq(db: Session, editor: Editor, body: FaqInput) -> Faq:
    if body.is_visible:
        editor.need("content.publish", SHOW_NEEDS_PUBLISH)
    _check_project(db, body.project_id)
    faq = Faq(
        project_id=body.project_id,
        question=body.question,
        answer=body.answer,
        sort_order=(
            body.sort_order if body.sort_order is not None else _next_order(db, body.project_id)
        ),
        is_visible=body.is_visible,
        translations=body.translations.root,
        created_by=editor.user_id,
        updated_by=editor.user_id,
    )
    db.add(faq)
    db.flush()
    audit_row(
        db,
        editor,
        action="faq.created",
        entity_type="faq",
        entity_id=faq.id,
        changes=audit.diff({}, snapshot(faq, _AUDIT_SKIP)),
    )
    if faq.is_visible:
        _event(db, editor, faq, "created")
    commit(db)
    return faq


def _locked(db: Session, faq_id: uuid.UUID) -> Faq:
    faq = db.get(Faq, faq_id, with_for_update=True, populate_existing=True)
    if faq is None:
        raise ApiProblem(404, NO_FAQ)
    return faq


def update_faq(db: Session, editor: Editor, faq_id: uuid.UUID, body: FaqUpdate) -> Faq:
    faq = _locked(db, faq_id)
    sent = body.model_dump(exclude_unset=True)
    if "is_visible" in sent and sent["is_visible"] != faq.is_visible:
        editor.need("content.publish", SHOW_NEEDS_PUBLISH)
    moves = "project_id" in sent and sent["project_id"] != faq.project_id
    if moves:
        _check_project(db, sent["project_id"])
        if "sort_order" not in sent:
            sent["sort_order"] = _next_order(db, sent["project_id"])
    before = snapshot(faq, _AUDIT_SKIP)
    was_visible = faq.is_visible
    for key, value in sent.items():
        setattr(faq, key, value)
    db.flush()
    diff = audit.diff(before, snapshot(faq, _AUDIT_SKIP))
    if not diff:
        db.rollback()
        return _locked(db, faq_id)
    faq.updated_by = editor.user_id
    audit_row(db, editor, action="faq.updated", entity_type="faq", entity_id=faq.id, changes=diff)
    if was_visible or faq.is_visible:
        _event(db, editor, faq, "updated")
    commit(db)
    return faq


def delete_faq(db: Session, editor: Editor, faq_id: uuid.UUID) -> None:
    """Delete the FAQ and take it out of every faq_list block that picked it."""
    faq = _locked(db, faq_id)
    drop_reference(db, editor, "faq_ids", faq.id)
    audit_row(
        db,
        editor,
        action="faq.deleted",
        entity_type="faq",
        entity_id=faq.id,
        changes={k: [v, None] for k, v in snapshot(faq, _AUDIT_SKIP).items()},
    )
    if faq.is_visible:
        _event(db, editor, faq, "deleted")
    db.delete(faq)
    commit(db)


def reorder_faqs(db: Session, editor: Editor, ids: list[uuid.UUID]) -> list[Faq]:
    """Set the order of one list (site-wide, or one project's). `ids` names all of it once."""
    first = db.get(Faq, ids[0])
    if first is None:
        raise invalid([FieldError("ids", "Unknown FAQ in the list.")])
    rows = list(
        db.scalars(
            select(Faq)
            .where(_group(first.project_id))
            .order_by(Faq.sort_order, Faq.created_at, Faq.id)
            .with_for_update()
        )
    )
    by_id = {row.id: row for row in rows}
    if len(ids) != len(rows) or set(ids) != set(by_id):
        raise invalid([FieldError("ids", FULL_LIST)])
    old = [str(row.id) for row in rows]
    for index, faq_id in enumerate(ids):
        by_id[faq_id].sort_order = index
    if old != [str(i) for i in ids]:
        audit_row(
            db,
            editor,
            action="faq.reordered",
            entity_type="project" if first.project_id else "faq",
            entity_id=first.project_id or first.id,
            changes={"faq_order": [old, [str(i) for i in ids]]},
        )
        if any(row.is_visible for row in rows):
            _event(db, editor, first, "reordered")
    commit(db)
    return [by_id[faq_id] for faq_id in ids]
