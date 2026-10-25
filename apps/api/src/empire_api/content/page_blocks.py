"""Save a page's blocks: the full ordered list in one transaction (PUT /pages/{id}/blocks).

Collaborators: block_types.py and blocks.py (shapes, already validated by the request model),
block_refs.py (ids against the database), media/content_links.py (the page's media links),
pages.py (lock, events), common.py (audit).
Implements: the part 4 block rules, ARCHITECTURE §6 (exclusive arc: a page's library items are
`media_link` rows, so a file in use can't be deleted), §9 (`page.updated` while live), §11.

How a save works:
  1. Check every id the blocks name (library items with their kind and honest label, projects,
     cities, FAQs, testimonials, offers), reading each row FOR SHARE (block_refs.py).
  2. Lock the page. A live or scheduled legal page needs `legal.publish` (D-017, review H2).
     A save based on an older copy of the page (`expected_updated_at`) is refused (409, review
     L7), so a stale tab can't silently delete blocks someone else added. In production, DRAFT
     legal text can't be saved onto a live legal page (409, review M1). Then the 422s from 1.
  3. Blocks sent with an `id` of this page are updated in place; new ones are inserted; blocks
     left out are deleted. `sort_order` becomes the position in the list.
  4. The page's `block` media links are set to exactly the library items the blocks use.
  5. One audit row (types before/after, media added/removed), `page.updated` if the page is
     live, one commit.

WHY step 1 comes before the page lock: an FAQ or testimonial delete locks its row and then the
pages that use it (drop_reference). Taking the rows in the same order (named row, then page)
means the two can wait for each other but never deadlock.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.content import block_refs, page_rules
from empire_api.content.block_types import AnyBlockInput, BlockInput
from empire_api.content.blocks import VideoData
from empire_api.content.common import Editor, audit_row
from empire_api.content.models import PageBlock
from empire_api.content.pages import check_fresh, lock_page, page_event
from empire_api.media.content_links import set_links
from empire_api.media.rules import Owner
from empire_api.projects.common import FieldError, commit, invalid

UNKNOWN_BLOCK: Final = "This block isn't on this page any more. Reload the page."
DUPLICATE_BLOCK: Final = "The same block can appear only once."


def _stored(block: AnyBlockInput) -> dict[str, Any]:
    """The `data` JSON as stored: a video link is kept as its provider and id only."""
    if isinstance(block.data, VideoData):
        return block.data.stored()
    return block.data.model_dump(mode="json")


def _id_errors(blocks: list[AnyBlockInput], existing: set[uuid.UUID]) -> list[FieldError]:
    errors: list[FieldError] = []
    seen: set[uuid.UUID] = set()
    for index, block in enumerate(blocks):
        if block.id is None:
            continue
        if block.id not in existing:
            errors.append(FieldError(f"blocks.{index}.id", UNKNOWN_BLOCK))
        elif block.id in seen:
            errors.append(FieldError(f"blocks.{index}.id", DUPLICATE_BLOCK))
        seen.add(block.id)
    return errors


def set_blocks(
    db: Session,
    editor: Editor,
    page_id: uuid.UUID,
    body: list[BlockInput],
    expected_updated_at: datetime | None = None,
) -> None:
    """Replace the page's blocks with `body`, in order (module header)."""
    blocks = [item.root for item in body]
    refs = block_refs.collect(blocks)
    ref_errors = block_refs.check(db, refs)  # 1
    page = lock_page(db, page_id)  # 2
    if page_rules.legal_guarded(page):
        editor.need("legal.publish", page_rules.LEGAL_ONLY)
    check_fresh(page, expected_updated_at)
    stored = [_stored(block) for block in blocks]
    if page_rules.leaves_draft_text_live(page.kind, page.publish_state, page.title, stored):
        raise page_rules.legal_draft_conflict("blocks")
    current = {block.id: block for block in page.blocks}
    errors = _id_errors(blocks, set(current)) + ref_errors
    if errors:
        raise invalid(errors)
    before_types = [block.type for block in page.blocks]
    kept: set[uuid.UUID] = set()
    for index, (block, data) in enumerate(zip(blocks, stored, strict=True)):  # 3
        row = current.get(block.id) if block.id else None
        if row is None:
            row = PageBlock(page_id=page.id)
            page.blocks.append(row)
        else:
            kept.add(row.id)
        row.type, row.data = block.type, data
        row.sort_order, row.is_visible = index, block.is_visible
    for block_id, row in current.items():
        if block_id not in kept:
            page.blocks.remove(row)
    db.flush()
    added, removed = set_links(db, Owner("page", page.id), "block", refs.media_ids())  # 4
    page.updated_by = editor.user_id
    page.updated_at = func.now()  # the page counts as edited (list order, "last saved")
    audit_row(  # 5
        db,
        editor,
        action="page.blocks_saved",
        entity_type="page",
        entity_id=page.id,
        changes={
            "blocks": [before_types, [block.type for block in blocks]],
            "media_added": [None, added],
            "media_removed": [removed, None],
        },
    )
    if page.publish_state == "published":
        page_event(db, editor, page, "page.updated", changed=["blocks"])
    commit(db)


# --- Other content removed from under a block ------------------------------------------------


def pages_naming(db: Session, field: str, item_id: uuid.UUID) -> list[PageBlock]:
    """Blocks whose `data[field]` names `item_id` (a list field such as `faq_ids`, or a single
    id field such as `offer_id`)."""
    value: Any = [str(item_id)] if field.endswith("_ids") else str(item_id)
    return list(
        db.scalars(
            select(PageBlock)
            .where(PageBlock.data.contains({field: value}))
            .order_by(PageBlock.page_id, PageBlock.sort_order)
        )
    )


def drop_reference(db: Session, actor: Editor, field: str, item_id: uuid.UUID) -> None:
    """A FAQ or testimonial was deleted: take its id out of every block that picked it, so a
    page never asks for something that is gone (COMPLIANCE for testimonials: a buyer who
    withdrew consent disappears from every page at once). Live pages get `page.updated`.
    No commit.

    INVARIANT (review M4): a deletion never widens what a block shows. An empty pick list means
    "the site-wide FAQs" or "the newest testimonials" (blocks.py), which nobody chose for this
    page, so a block whose last pick goes is hidden instead (`is_visible` false, audited); the
    CMS shows it as hidden, and staff pick again or delete it. The page counts as edited, so a
    tab opened before this gets the stale-save 409 (review L7).
    """
    for block in pages_naming(db, field, item_id):
        page = lock_page(db, block.page_id)
        ids = [value for value in block.data.get(field, []) if value != str(item_id)]
        block.data = {**block.data, field: ids}
        changes: dict[str, Any] = {f"blocks.{block.sort_order}.data.{field}": [str(item_id), None]}
        if not ids and block.is_visible:
            block.is_visible = False
            changes[f"blocks.{block.sort_order}.is_visible"] = [True, False]
        page.updated_at = func.now()
        audit_row(
            db,
            actor,
            action="page.block_reference_removed",
            entity_type="page",
            entity_id=page.id,
            changes=changes,
        )
        if page.publish_state == "published":
            page_event(db, actor, page, "page.updated", changed=["blocks"])
    db.flush()
