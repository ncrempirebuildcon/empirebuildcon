"""Business rules for redirects: list, create, update and delete them in the CMS, and the
automatic ones made when a live page, post or project changes its slug.

Collaborators: paths.py (both ends of a redirect), routes.py (HTTP), content/pages.py,
content/posts.py and projects/service.py (slug changes and publishing call `slug_changed` and
`claim_path`); platform/audit.py and outbox.py.
Implements: ARCHITECTURE §9 (`redirect.changed`), §11 (audit), §16 (redirects manager);
SECURITY.md §5 (no open redirects).

Rules:
  - `from_path` is unique. 308 unless 301 is chosen.
  - INVARIANT: every active redirect is one hop. Saving A→B while B→C is active stores A→C and
    says so in `notices`; active redirects that pointed at A are re-pointed to A's target (the
    chain collapses) and that is said too. A→B while B→A is active is a loop: 409.
  - Collapsing keeps what the visitor's link carried (review L4): when the onward target has no
    query string (or no fragment) of its own, the original target's is kept, and the notice
    says so. `/y → /a?ref=1` plus a new `/a → /b` gives `/y → /b?ref=1`.
  - A redirect typed in the CMS can't start at the address of a live page, post or project
    (409, review L5): the website would send visitors away from it. Automatic slug redirects
    never do (claim_path below).
  - Paths match exactly and case-sensitively (the Phase 5 contract in paths.py).
  - A slug change on a live page, post or project redirects the old path to the new one (308),
    re-using the redirect from the old path if one exists, and collapses chains the same way.
  - When something goes live at a path (publish, or a live slug change), a redirect *from* that
    path is deleted: otherwise it would hide the new page, and renaming back and forth would
    make a loop.
  - Inactive redirects do nothing, so they take no part in chains; they are checked again when
    switched back on.

INVARIANT: all redirect writes take one transaction-level advisory lock, so two saves can't
create a loop or a chain between them; each public function's caller commits once.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from empire_api.content import queries as content_queries
from empire_api.errors import ApiProblem
from empire_api.pagination import PageParams
from empire_api.platform import audit, outbox
from empire_api.projects import queries as project_queries
from empire_api.projects.common import (
    Actor,
    FieldError,
    commit,
    conflict,
    flush,
    invalid,
    like_pattern,
    snapshot,
)
from empire_api.seo.models import Redirect
from empire_api.seo.paths import owner_of_path, path_of, split_target
from empire_api.seo.schemas import RedirectInput, RedirectUpdate
from empire_api.seo.vocab import MAX_PATH

FROM_TAKEN: Final = "There is already a redirect from this address. Edit that one instead."
CONFLICTS: Final = {"uq_redirect_from_path": ("from_path", FROM_TAKEN)}
NO_REDIRECT: Final = "No redirect with this id."
TO_ITSELF: Final = "A redirect can't point to the address it comes from."
_LOCK_KEY: Final = "seo:redirects"
_SKIP: Final = ("created_by", "updated_by", "hits", "last_hit_at")


@dataclass(frozen=True)
class Saved:
    """A saved redirect and what else the save did, in words for staff."""

    row: Redirect
    notices: list[str]


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": _LOCK_KEY})


def _actor_id(actor: Actor | None) -> uuid.UUID | None:
    return actor.user_id if actor else None


def _audit(
    db: Session, actor: Actor | None, action: str, row: Redirect, changes: dict[str, Any]
) -> None:
    audit.record(
        db,
        action=action,
        entity_type="redirect",
        entity_id=row.id,
        actor_id=_actor_id(actor),
        ip=actor.ip if actor else None,
        changes=changes,
    )


def _event(db: Session, actor: Actor | None, row: Redirect, change: str) -> None:
    """`redirect.changed`: the web app reloads its redirect table (Phase 5, `site` tag)."""
    outbox.emit(
        db,
        type_="redirect.changed",
        aggregate_type="redirect",
        aggregate_id=row.id,
        actor_id=_actor_id(actor),
        data={
            "redirect_id": str(row.id),
            "change": change,
            "from_path": row.from_path,
            "to_path": row.to_path,
            "status_code": row.status_code,
            "is_active": row.is_active,
        },
    )


# --- Reading ---------------------------------------------------------------------------------


def list_redirects(
    db: Session, paging: PageParams, q: str | None, origin: str | None, is_active: bool | None
) -> tuple[list[Redirect], int]:
    """Newest first. `q` matches either end, ignoring case."""
    stmt = select(Redirect)
    if q and q.strip():
        pattern = like_pattern(q)
        stmt = stmt.where(
            or_(
                func.lower(Redirect.from_path).like(pattern, escape="\\"),
                func.lower(Redirect.to_path).like(pattern, escape="\\"),
            )
        )
    if origin is not None:
        stmt = stmt.where(Redirect.origin == origin)
    if is_active is not None:
        stmt = stmt.where(Redirect.is_active.is_(is_active))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(Redirect.created_at.desc(), Redirect.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


def _active_from(db: Session, path: str, exclude: uuid.UUID | None) -> Redirect | None:
    stmt = select(Redirect).where(Redirect.from_path == path, Redirect.is_active.is_(True))
    if exclude is not None:
        stmt = stmt.where(Redirect.id != exclude)
    return db.scalar(stmt)


def _pointing_at(db: Session, path: str, exclude: uuid.UUID | None) -> list[Redirect]:
    """Active redirects whose target is `path` (with or without a query or fragment)."""
    stmt = select(Redirect).where(
        Redirect.is_active.is_(True),
        or_(
            Redirect.to_path == path,
            Redirect.to_path.startswith(path + "?", autoescape=True),
            Redirect.to_path.startswith(path + "#", autoescape=True),
        ),
    )
    if exclude is not None:
        stmt = stmt.where(Redirect.id != exclude)
    return list(db.scalars(stmt.order_by(Redirect.id)))


# --- The one-hop rule -----------------------------------------------------------------------


def _carry(original: str, onward: str) -> tuple[str, str]:
    """Where `original` goes once its path redirects to `onward`, keeping the original's query
    string and fragment where `onward` has none (module rules). Returns (target, kept part).

    WHY onward wins when both have one: the onward target was chosen for that path; merging
    two query strings could change what the page shows. A result too long to store keeps
    nothing extra (the plain onward target is always storable).
    """
    _, query, fragment = split_target(original)
    path, onward_query, onward_fragment = split_target(onward)
    kept = (query if not onward_query else "") + (fragment if not onward_fragment else "")
    target = f"{path}{onward_query or query}{onward_fragment or fragment}"
    if not kept or len(target) > MAX_PATH:
        return onward, ""
    return target, kept


def _resolve(
    db: Session, from_path: str, target: str, row_id: uuid.UUID | None, *, active: bool
) -> tuple[str, list[str]]:
    """Where `from_path` should finally point (one hop), with notices for staff; or 422/409.

    How it works:
      1. A target equal to the source is refused (422).
      2. An inactive redirect does nothing, so it takes no part in chains (checked again when
         it is switched on).
      3. If the target itself redirects onward (an active B→C), point straight at C; if C is
         the source, that is a loop (409).
    """
    target_path = path_of(target)
    if target_path == from_path:  # 1
        raise invalid([FieldError("to_path", TO_ITSELF)], TO_ITSELF)
    if not active:  # 2
        return target, []
    onward = _active_from(db, target_path, row_id)  # 3
    if onward is None:
        return target, []
    if path_of(onward.to_path) == from_path:
        message = (
            f"{target_path} already redirects to {from_path}, so this would make a loop. "
            f"Change or delete the redirect from {target_path} first."
        )
        raise conflict(message, "to_path", message)
    final, kept = _carry(target, onward.to_path)
    notice = (
        f"{target_path} already redirects to {onward.to_path}, so {from_path} now goes "
        f"straight to {final}."
    )
    if kept:
        notice += f" {kept} from the address you entered is kept."
    return final, [notice]


def _collapse_incoming(db: Session, actor: Actor | None, row: Redirect, notices: list[str]) -> None:
    """Re-point active redirects that pointed at `row.from_path` to `row.to_path` (no chains),
    each keeping its own query string and fragment (`_carry`)."""
    incoming = _pointing_at(db, row.from_path, row.id)
    carried = False
    for other in incoming:
        before = other.to_path
        other.to_path, kept = _carry(before, row.to_path)
        carried = carried or bool(kept)
        other.updated_by = _actor_id(actor)
        _audit(db, actor, "redirect.updated", other, {"to_path": [before, other.to_path]})
        _event(db, actor, other, "updated")
    if incoming:
        count = len(incoming)
        what, verb = ("1 redirect", "goes") if count == 1 else (f"{count} redirects", "go")
        notice = f"{what} that pointed to {row.from_path} now {verb} straight to {row.to_path}."
        if carried:
            notice += f" Any query string or fragment {'it' if count == 1 else 'they'} had is kept."
        notices.append(notice)


def _refuse_live_source(db: Session, from_path: str) -> None:
    """409 when something is live at `from_path` (module rules, review L5)."""
    owner = owner_of_path(from_path)
    if owner is None:
        return
    kind, slug = owner
    if kind == "project":
        title = project_queries.published_project_name(db, slug)
    else:
        title = content_queries.live_title(db, kind, slug)
    if title is None:
        return
    message = (
        f"The {kind} “{title}” is on the website at {from_path}, so a redirect from there would "
        f"hide it. Unpublish the {kind} first, or redirect a different address."
    )
    raise conflict(message, "from_path", message)


# --- Staff edits -----------------------------------------------------------------------------


def create_redirect(db: Session, actor: Actor, body: RedirectInput) -> Saved:
    _lock(db)
    if db.scalar(select(Redirect.id).where(Redirect.from_path == body.from_path)):
        raise conflict(FROM_TAKEN, "from_path", FROM_TAKEN)
    _refuse_live_source(db, body.from_path)
    to_path, notices = _resolve(db, body.from_path, body.to_path, None, active=body.is_active)
    row = Redirect(
        from_path=body.from_path,
        to_path=to_path,
        status_code=int(body.status_code),
        is_active=body.is_active,
        origin="manual",
        created_by=actor.user_id,
        updated_by=actor.user_id,
    )
    db.add(row)
    flush(db, CONFLICTS)
    _audit(db, actor, "redirect.created", row, audit.diff({}, snapshot(row, _SKIP)))
    _event(db, actor, row, "created")
    if row.is_active:
        _collapse_incoming(db, actor, row, notices)
    commit(db, CONFLICTS)
    return Saved(row, notices)


def _locked(db: Session, redirect_id: uuid.UUID) -> Redirect:
    row = db.get(Redirect, redirect_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise ApiProblem(404, NO_REDIRECT)
    return row


def update_redirect(
    db: Session, actor: Actor, redirect_id: uuid.UUID, body: RedirectUpdate
) -> Saved:
    """Change what was sent; the one-hop rule is checked on the merged values."""
    _lock(db)
    row = _locked(db, redirect_id)
    sent = body.model_dump(exclude_unset=True)
    from_path = sent.get("from_path", row.from_path)
    target = sent.get("to_path", row.to_path)
    is_active = sent.get("is_active", row.is_active)
    if from_path != row.from_path and db.scalar(
        select(Redirect.id).where(Redirect.from_path == from_path, Redirect.id != row.id)
    ):
        raise conflict(FROM_TAKEN, "from_path", FROM_TAKEN)
    _refuse_live_source(db, from_path)
    to_path, notices = _resolve(db, from_path, target, row.id, active=is_active)
    before = snapshot(row, _SKIP)
    row.from_path, row.to_path, row.is_active = from_path, to_path, is_active
    if "status_code" in sent:
        row.status_code = int(sent["status_code"])
    flush(db, CONFLICTS)
    diff = audit.diff(before, snapshot(row, _SKIP))
    if not diff:
        db.rollback()
        return Saved(_locked(db, redirect_id), [])
    row.updated_by = actor.user_id
    _audit(db, actor, "redirect.updated", row, diff)
    _event(db, actor, row, "updated")
    if row.is_active:
        _collapse_incoming(db, actor, row, notices)
    commit(db, CONFLICTS)
    return Saved(row, notices)


def delete_redirect(db: Session, actor: Actor, redirect_id: uuid.UUID) -> None:
    _lock(db)
    row = _locked(db, redirect_id)
    _audit(db, actor, "redirect.deleted", row, {k: [v, None] for k, v in snapshot(row).items()})
    _event(db, actor, row, "deleted")
    db.delete(row)
    commit(db)


# --- Called by content and projects ----------------------------------------------------------


def claim_path(db: Session, actor: Actor | None, path: str) -> None:
    """Something went live at `path`: delete a redirect *from* it (module rules). Caller
    commits. `actor` is None for the schedule tick."""
    _lock(db)
    row = db.scalar(select(Redirect).where(Redirect.from_path == path).with_for_update())
    if row is None:
        return
    changes = {k: [v, None] for k, v in snapshot(row).items()}
    changes["note"] = [None, "Something is published at this address now."]
    _audit(db, actor, "redirect.deleted", row, changes)
    _event(db, actor, row, "deleted")
    db.delete(row)
    db.flush()


def slug_changed(
    db: Session, actor: Actor | None, origin: str, old_path: str, new_path: str
) -> Redirect | None:
    """A live page, post or project moved from `old_path` to `new_path`: 308 old → new.

    Re-uses (and re-activates) a redirect that already starts at `old_path`, and collapses
    redirects that pointed at the old path. Caller commits. Returns the redirect.
    """
    if old_path == new_path:
        return None
    claim_path(db, actor, new_path)
    row = db.scalar(select(Redirect).where(Redirect.from_path == old_path).with_for_update())
    if row is None:
        row = Redirect(
            from_path=old_path,
            to_path=new_path,
            status_code=308,
            is_active=True,
            origin=origin,
            created_by=_actor_id(actor),
            updated_by=_actor_id(actor),
        )
        db.add(row)
        db.flush()
        _audit(db, actor, "redirect.created", row, audit.diff({}, snapshot(row, _SKIP)))
        _event(db, actor, row, "created")
    else:
        before = snapshot(row, _SKIP)
        row.to_path, row.status_code, row.is_active, row.origin = new_path, 308, True, origin
        row.updated_by = _actor_id(actor)
        db.flush()
        _audit(db, actor, "redirect.updated", row, audit.diff(before, snapshot(row, _SKIP)))
        _event(db, actor, row, "updated")
    _collapse_incoming(db, actor, row, [])
    db.flush()
    return row
