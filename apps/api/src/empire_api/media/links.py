"""Business rules for media links: attach a library item to an owner, show or hide it, pin the
cover, detach it, and set the order of one owner's list.

Collaborators: rules.py (roles and kinds), events.py, projects/media_owners.py (the owner's
project, locked), projects/common.py (audit rows, flush/commit with 409s); routes.py (HTTP),
uploads.py (attach in the same transaction as an upload).
Implements: ARCHITECTURE §6 (exclusive arc, one cover per owner and role), §9 (media events),
§11 (audit on every change), D-002 (RERA QR).

Rules:
  - Single-valued roles (brochure, rera_qr, hero, og_image; floor_plan per configuration):
    attaching replaces the old link in the same transaction, with its own audit row. The old
    file stays in the library.
  - Cover: the pinned item, else the first visible one in order. Pinning one unpins the others;
    hidden items can't be pinned; hiding the pinned cover unpins it. Only photo lists have one.
  - New links go to the end of their list; detaching closes the gap.
  - COMPLIANCE (D-002): while a project is published, its RERA QR can't be hidden or removed,
    only replaced ("Upload the new QR first").
  - COMPLIANCE (honest content): an unlabelled photo in a photo list is attached hidden and
    can't be shown until it has a label (rules.needs_label). Sample placeholders are exempt.

INVARIANT: the owner's project row is locked first (lock_owner_project), so every change to one
project's media is serialised with publishing and with each other.
"""

from __future__ import annotations

import uuid
from typing import Final

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.media import events
from empire_api.media.models import Media, MediaLink
from empire_api.media.rules import LABEL_FIRST, Owner, check_role, needs_label
from empire_api.media.schemas import MediaLinkUpdate
from empire_api.media.vocab import COVER_ROLES, SINGLE_ROLES
from empire_api.projects.common import (
    Actor,
    FieldError,
    commit,
    conflict,
    flush,
    invalid,
    record,
    snapshot,
    touch,
)
from empire_api.projects.media_owners import lock_owner_project
from empire_api.projects.models import Project

QR_FIRST: Final = (
    "This project is on the website, so its RERA QR code must stay visible. "
    "Upload the new QR first, or unpublish the project."
)
ALREADY_ATTACHED: Final = "This file is already attached here."
LINK_CONFLICTS: Final = {
    f"uq_media_link_{column}_role_media_id": ("media_id", ALREADY_ATTACHED)
    for column in ("project_id", "configuration_id", "construction_update_id")
}
NO_LINK: Final = "No attached media with this id."


def owner_links(db: Session, owner: Owner, role: str) -> list[MediaLink]:
    """One owner's list for one role, in order."""
    return list(
        db.scalars(
            select(MediaLink)
            .where(owner.matches(), MediaLink.role == role)
            .order_by(MediaLink.sort_order, MediaLink.id)
        )
    )


def _locked_link(db: Session, link_id: uuid.UUID) -> tuple[MediaLink, Owner, Project]:
    """The link and its owner's project, both locked (project first), or 404."""
    link = db.get(MediaLink, link_id)
    if link is None:
        raise ApiProblem(404, NO_LINK)
    owner = Owner.of(link)
    project = lock_owner_project(db, owner.type, owner.id)
    # WHY `of`: `MediaLink.media` is eager-loaded with a LEFT OUTER JOIN, and PostgreSQL refuses
    # FOR UPDATE on the nullable side of an outer join; lock the link row only.
    link = db.get(MediaLink, link_id, with_for_update={"of": MediaLink}, populate_existing=True)
    if link is None:
        raise ApiProblem(404, NO_LINK)
    return link, owner, project


# --- Attach --------------------------------------------------------------------------------


def attach(
    db: Session,
    actor: Actor,
    *,
    media: Media,
    owner: Owner,
    role: str,
    is_visible: bool,
    project: Project,
) -> MediaLink:
    """Add a link inside the caller's transaction (the project is already locked).

    How it works:
      1. Check the role exists for this owner and accepts this file; refuse a duplicate.
      2. Single-valued role: remove the current link (audited as replaced); a live project's
         replacement QR must be visible.
      3. Add the link at the end of the list, audit it and mark the project edited.
    The caller emits the events and commits.
    """
    check_role(owner, role, media)  # 1
    if needs_label(media, role):
        is_visible = False  # COMPLIANCE: shown only once it is honestly labelled
    current = owner_links(db, owner, role)
    if any(link.media_id == media.id for link in current):
        raise conflict(ALREADY_ATTACHED, "media_id", ALREADY_ATTACHED)
    if role in SINGLE_ROLES and current:  # 2
        if role == "rera_qr" and project.publish_state == "published" and not is_visible:
            raise conflict(QR_FIRST)
        for old in current:
            record(
                db,
                actor,
                action="media_link.replaced",
                entity_type="media_link",
                entity_id=old.id,
                changes={"media_id": [str(old.media_id), str(media.id)]},
            )
            db.delete(old)
        flush(db)
        current = []
    link = MediaLink(  # 3
        media_id=media.id,
        role=role,
        sort_order=(max((link.sort_order for link in current), default=-1) + 1),
        is_visible=is_visible,
        created_by=actor.user_id,
        **{owner.column: owner.id},
    )
    db.add(link)
    flush(db, LINK_CONFLICTS)
    record(
        db,
        actor,
        action="media_link.attached",
        entity_type="media_link",
        entity_id=link.id,
        before={},
        after=snapshot(link, ("created_by",)),
    )
    touch(project, actor)
    return link


def attach_media(
    db: Session, actor: Actor, media_id: uuid.UUID, attach_to: str, role: str, is_visible: bool
) -> MediaLink:
    """POST /admin/media-links: attach an existing library item."""
    owner = Owner.parse(attach_to)
    project = lock_owner_project(db, owner.type, owner.id)
    media = db.get(Media, media_id, with_for_update=True)
    if media is None:
        raise ApiProblem(404, "No media with this id.")
    link = attach(
        db, actor, media=media, owner=owner, role=role, is_visible=is_visible, project=project
    )
    events.media_event(db, actor, "media.updated", media, "attached", link=link, project=project)
    events.owner_changed(db, actor, project, owner, role, "attached")
    commit(db, LINK_CONFLICTS)
    return link


# --- Show/hide and cover ---------------------------------------------------------------------


def update_link(db: Session, actor: Actor, link_id: uuid.UUID, body: MediaLinkUpdate) -> MediaLink:
    """Show or hide a link, or pin/unpin it as the cover (rules in the module header)."""
    link, owner, project = _locked_link(db, link_id)
    sent = body.model_dump(exclude_unset=True)
    visible: bool = sent.get("is_visible", link.is_visible)
    cover: bool = sent.get("is_cover", link.is_cover)
    _check_cover(link, sent, visible)
    if visible and not link.is_visible and needs_label(link.media, link.role):
        raise invalid([FieldError("is_visible", LABEL_FIRST)], LABEL_FIRST)
    if cover and not visible:
        cover = False  # hiding the pinned cover unpins it
    hides_live_qr = link.role == "rera_qr" and link.is_visible and not visible
    if hides_live_qr and project.publish_state == "published":
        raise conflict(QR_FIRST)
    before = {"is_visible": link.is_visible, "is_cover": link.is_cover}
    if cover and not link.is_cover:
        db.execute(
            update(MediaLink)
            .where(owner.matches(), MediaLink.role == link.role, MediaLink.id != link.id)
            .values(is_cover=False)
        )
        flush(db)
    link.is_visible, link.is_cover = visible, cover
    flush(db)
    after = {"is_visible": link.is_visible, "is_cover": link.is_cover}
    if after != before:
        diff = {key: [before[key], after[key]] for key in after if before[key] != after[key]}
        record(
            db,
            actor,
            action="media_link.updated",
            entity_type="media_link",
            entity_id=link.id,
            changes=diff,
        )
        touch(project, actor)
        change = _change_name(before, after)
        events.media_event(
            db, actor, "media.updated", link.media, change, link=link, project=project
        )
        events.owner_changed(db, actor, project, owner, link.role, change)
    commit(db)
    return link


def _change_name(before: dict[str, bool], after: dict[str, bool]) -> str:
    if before["is_visible"] != after["is_visible"]:
        return "shown" if after["is_visible"] else "hidden"
    return "cover_pinned" if after["is_cover"] else "cover_unpinned"


def _check_cover(link: MediaLink, sent: dict[str, bool], visible: bool) -> None:
    if not sent.get("is_cover"):
        return
    if link.role not in COVER_ROLES:
        raise invalid([FieldError("is_cover", "Only photos can be the cover.")])
    if not visible:
        raise invalid(
            [FieldError("is_cover", "Show this photo on the website before making it the cover.")]
        )


# --- Detach and reorder ----------------------------------------------------------------------


def detach(db: Session, actor: Actor, link_id: uuid.UUID) -> None:
    """Remove a link; the file stays in the library. The list's order closes the gap."""
    link, owner, project = _locked_link(db, link_id)
    if link.role == "rera_qr" and link.is_visible and project.publish_state == "published":
        raise conflict(QR_FIRST)
    media, role = link.media, link.role
    record(
        db,
        actor,
        action="media_link.detached",
        entity_type="media_link",
        entity_id=link.id,
        before=snapshot(link, ("created_by",)),
    )
    events.media_event(db, actor, "media.updated", media, "detached", link=link, project=project)
    db.delete(link)
    flush(db)
    for index, rest in enumerate(owner_links(db, owner, role)):
        rest.sort_order = index
    touch(project, actor)
    events.owner_changed(db, actor, project, owner, role, "detached")
    commit(db)


def reorder(db: Session, actor: Actor, ids: list[uuid.UUID]) -> None:
    """Set the order of one owner's list. `ids` must name every link of that list once."""
    first = db.get(MediaLink, ids[0])
    if first is None:
        raise invalid([FieldError("ids", "Unknown item in the list.")])
    owner, role = Owner.of(first), first.role
    project = lock_owner_project(db, owner.type, owner.id)
    links = owner_links(db, owner, role)
    by_id = {link.id: link for link in links}
    if len(ids) != len(links) or set(ids) != set(by_id):
        raise invalid(
            [FieldError("ids", "Send every item of this list exactly once, in the new order.")]
        )
    old = [str(link.id) for link in links]
    for index, link_id in enumerate(ids):
        by_id[link_id].sort_order = index
    new = [str(i) for i in ids]
    if old != new:
        record(
            db,
            actor,
            action="media_link.reordered",
            entity_type=owner.type,
            entity_id=owner.id,
            changes={f"{role}_order": [old, new]},
        )
        touch(project, actor)
        events.list_reordered(db, actor, owner, role, project)
        events.owner_changed(db, actor, project, owner, role, "reordered")
    commit(db)


def links_count(db: Session, media_id: uuid.UUID) -> int:
    count = db.scalar(
        select(func.count()).select_from(MediaLink).where(MediaLink.media_id == media_id)
    )
    return int(count or 0)
