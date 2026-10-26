"""Service functions the content module calls about the library items its pages and posts use:
keep their `media_link` rows in step with a page's blocks or a post's cover, read them back,
and describe library items for block checks.

Collaborators: content/page_blocks.py, content/posts.py, content/block_refs.py (callers);
links.owner_links; present.py.
Implements: ARCHITECTURE §2 (other modules call these, never the media tables), §6 (exclusive
arc, owners `page` and `post`), and the part 4 rule that a library item can't be deleted while
a block or a post cover uses it: the link's foreign key is RESTRICT and library.delete_media
counts it (409 "used in …").

INVARIANT: a page's `block` links are exactly the library items its blocks name (in order of
first use), and a post has at most one `cover` link. Only `set_links` writes them; the
media-links endpoints refuse them (rules.CONTENT_LINK). No audit rows or media events here: the
page or post save that caused the change records it (content module).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.media import present, schemas
from empire_api.media.links import owner_links
from empire_api.media.models import Media, MediaLink
from empire_api.media.rules import Owner


@dataclass(frozen=True)
class LibraryFacts:
    """What a block check needs to know about one library item."""

    kind: str
    has_label: bool
    is_sample: bool


def library_facts(db: Session, media_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, LibraryFacts]:
    """Library items by id, read FOR SHARE.

    WHY the share lock: a page saving a block that uses a file and a library delete must not
    pass each other; the lock makes the delete wait and then see the new link (409), or makes
    this read miss the deleted row (422 for the block).
    """
    ids = set(media_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(Media.id, Media.kind, Media.label, Media.is_sample)
        .where(Media.id.in_(ids))
        .with_for_update(read=True)
    ).all()
    return {
        row.id: LibraryFacts(
            kind=row.kind, has_label=row.label is not None, is_sample=row.is_sample
        )
        for row in rows
    }


def set_links(
    db: Session, owner: Owner, role: str, media_ids: Sequence[uuid.UUID]
) -> tuple[list[uuid.UUID], list[uuid.UUID]]:
    """Make `owner`'s links in `role` exactly `media_ids` (in that order). Caller commits.

    Returns (added, removed) media ids, for the caller's audit row.
    """
    wanted = list(dict.fromkeys(media_ids))
    current = owner_links(db, owner, role)
    by_media = {link.media_id: link for link in current}
    removed = [link.media_id for link in current if link.media_id not in wanted]
    for link in current:
        if link.media_id not in wanted:
            db.delete(link)
    db.flush()
    added: list[uuid.UUID] = []
    for index, media_id in enumerate(wanted):
        existing = by_media.get(media_id)
        if existing is not None:
            existing.sort_order = index
            continue
        db.add(
            MediaLink(
                media_id=media_id,
                role=role,
                sort_order=index,
                is_visible=True,
                **{owner.column: owner.id},
            )
        )
        added.append(media_id)
    db.flush()
    return added, removed


def library_items(
    db: Session, media_ids: Iterable[uuid.UUID | None]
) -> dict[uuid.UUID, schemas.Media]:
    """media id → `Media` (with delivery URLs and use counts) for every id that exists."""
    ids = {media_id for media_id in media_ids if media_id is not None}
    if not ids:
        return {}
    rows = list(db.scalars(select(Media).where(Media.id.in_(ids))))
    return {item.id: item for item in present.media_list(db, rows)}


def post_covers(db: Session, post_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, schemas.Media]:
    """post id → its cover image."""
    ids = set(post_ids)
    if not ids:
        return {}
    links = list(
        db.scalars(select(MediaLink).where(MediaLink.post_id.in_(ids), MediaLink.role == "cover"))
    )
    items = library_items(db, (link.media_id for link in links))
    return {
        link.post_id: items[link.media_id]
        for link in links
        if link.post_id is not None and link.media_id in items
    }


def post_cover_id(db: Session, post_id: uuid.UUID) -> uuid.UUID | None:
    return db.scalar(
        select(MediaLink.media_id).where(MediaLink.post_id == post_id, MediaLink.role == "cover")
    )
