"""Library rows and links → the contract shapes `Media` and `LinkedMedia`, with delivery URLs
from the active store and how many owners use each file.

Collaborators: routes.py, queries.py (the projects module's views); store.py for the URLs.
Nothing here writes to the database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.media import schemas
from empire_api.media.models import Media, MediaLink
from empire_api.media.store import AssetRef, MediaStore, get_store
from empire_api.projects.media_owners import share_image_counts


def attached_counts(db: Session, media_ids: Iterable[uuid.UUID]) -> dict[uuid.UUID, int]:
    """media id → how many places use it: links, plus projects' SEO share images."""
    ids = set(media_ids)
    if not ids:
        return {}
    rows = db.execute(
        select(MediaLink.media_id, func.count())
        .where(MediaLink.media_id.in_(ids))
        .group_by(MediaLink.media_id)
    ).all()
    counts = {media_id: int(count) for media_id, count in rows}
    for media_id, count in share_image_counts(db, ids).items():
        counts[media_id] = counts.get(media_id, 0) + count
    return counts


def _fields(row: Media, store: MediaStore, attached: int) -> dict[str, object]:
    urls = store.urls(
        AssetRef(
            kind=row.kind,
            public_id=row.public_id,
            resource_type=row.resource_type,
            version=row.version,
            format=row.format,
        )
    )
    return {
        "id": row.id,
        "kind": row.kind,
        "url": urls.url,
        "thumbnail_url": urls.thumbnail_url,
        "title": row.title,
        "alt_text": row.alt_text,
        "format": row.format,
        "bytes": row.bytes,
        "width": row.width,
        "height": row.height,
        "duration_s": None if row.duration_s is None else float(row.duration_s),
        "created_at": row.created_at,
        "label": row.label,
        "label_month": row.label_month,
        "is_sample": row.is_sample,
        "attached_count": attached,
    }


def media_out(row: Media, attached: int, store: MediaStore | None = None) -> schemas.Media:
    return schemas.Media.model_validate(_fields(row, store or get_store(), attached))


def linked_out(
    link: MediaLink, attached: int, store: MediaStore | None = None
) -> schemas.LinkedMedia:
    return schemas.LinkedMedia.model_validate(
        {
            **_fields(link.media, store or get_store(), attached),
            "link_id": link.id,
            "role": link.role,
            "sort_order": link.sort_order,
            "is_cover": link.is_cover,
            "is_visible": link.is_visible,
        }
    )


def media_list(db: Session, rows: Iterable[Media]) -> list[schemas.Media]:
    rows = list(rows)
    counts = attached_counts(db, (row.id for row in rows))
    store = get_store()
    return [media_out(row, counts.get(row.id, 0), store) for row in rows]


def linked_list(
    links: Iterable[MediaLink], counts: Mapping[uuid.UUID, int]
) -> list[schemas.LinkedMedia]:
    store = get_store()
    return [linked_out(link, counts.get(link.media_id, 0), store) for link in links]
