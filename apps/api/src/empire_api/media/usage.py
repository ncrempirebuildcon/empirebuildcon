"""Where a library item is used: project galleries, documents, floor plans, progress photos,
projects' share images, page blocks, post covers, page and post share images, offer images and
testimonial photos.

Collaborators: library.py (delete refused while used, with the places named), routes.py
(GET /admin/media/{id}/usage); projects/media_owners.py and content/media_uses.py (the owners'
names, through their service functions).
Implements: ARCHITECTURE §12 ("a library item can't be deleted while it is attached or used as a
share image"), extended in Phase 4 part 4 to content.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.content import media_uses
from empire_api.media.models import MediaLink
from empire_api.media.rules import ROLE_LABELS, Owner
from empire_api.media.schemas import MediaUse
from empire_api.projects.media_owners import (
    owner_project_id,
    projects_by_ids,
    share_image_projects,
)

SHOWN_IN_MESSAGE: Final = 5
_WORDS: Final = {**ROLE_LABELS, "share_image": "share image", "image": "image", "photo": "photo"}


def usage(db: Session, media_id: uuid.UUID) -> list[MediaUse]:
    """Every place the item is used, projects first, then content."""
    links = list(
        db.scalars(select(MediaLink).where(MediaLink.media_id == media_id).order_by(MediaLink.id))
    )
    page_ids: list[uuid.UUID] = []
    post_ids: list[uuid.UUID] = []
    project_links: list[tuple[Owner, uuid.UUID, str]] = []
    for link in links:
        owner = Owner.of(link)
        if owner.type == "page":
            page_ids.append(owner.id)
        elif owner.type == "post":
            post_ids.append(owner.id)
        else:
            project_id = owner_project_id(db, owner.type, owner.id)
            if project_id is not None:
                project_links.append((owner, project_id, link.role))
    names = {p.id: p.name for p in projects_by_ids(db, {pid for _, pid, _ in project_links})}
    found = [
        MediaUse(
            owner_type=owner.type,
            owner_id=owner.id,
            project_id=project_id,
            name=names.get(project_id, ""),
            role=role,
        )
        for owner, project_id, role in project_links
    ]
    found += [
        MediaUse(
            owner_type="project", owner_id=p.id, project_id=p.id, name=p.name, role="share_image"
        )
        for p in share_image_projects(db, media_id)
    ]
    found += [
        MediaUse(
            owner_type=use.owner_type,
            owner_id=use.owner_id,
            project_id=None,
            name=use.name,
            role=use.role,
        )
        for use in media_uses.uses(db, media_id, page_ids, post_ids)
    ]
    return found


def _place(use: MediaUse) -> str:
    """'page “Home” (page block)'; a testimonial by its name alone, 'Testimonial photo (R. S.)'
    (initials only, content/media_uses.testimonial_use_name)."""
    if use.owner_type == "testimonial":
        return use.name
    return f"{use.owner_type.replace('_', ' ')} “{use.name}” ({_WORDS.get(use.role, use.role)})"


def in_use_message(found: list[MediaUse]) -> str:
    """'This file is used in 2 places: page “Home” (page block), offer “…” (image). …'"""
    count = len(found)
    places = "1 place" if count == 1 else f"{count} places"
    named = ", ".join(_place(use) for use in found[:SHOWN_IN_MESSAGE])
    more = f" and {count - SHOWN_IN_MESSAGE} more" if count > SHOWN_IN_MESSAGE else ""
    return f"This file is used in {places}: {named}{more}. Remove it from there first."
