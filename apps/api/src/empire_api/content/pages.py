"""Business rules for pages: list, load, create, update (including archive, restore and the
schedule), delete, publish and unpublish. Blocks are saved by page_blocks.py.

Collaborators: page_rules.py (blockers, draft text), common.py (Editor, audit, events),
seo/redirects.py (a live slug change leaves a 308 behind; going live claims the path),
seo/checks.py (the share image), schedule.py (applies publish_at / unpublish_at), routes_pages.py.
Implements: ARCHITECTURE §6 (publishing, deletion), §9 (`page.*` events), §10 (schedule), §11
(permissions, audit), §16; D-015, D-017, D-018.

Rules:
  - Kinds: standard, landing, legal and system. System pages (home, about, contact, projects)
    come from `empire-api seed`; they can't be created. Some slugs are the website's own
    sections (seo/paths.RESERVED_PAGE_SLUGS).
  - Required pages (`is_required`: every system page, and the seeded legal pages privacy, terms
    and disclaimer, review L8) keep their slug and kind and can't be deleted or archived; they
    can be unpublished (a legal one with `legal.publish`).
  - Publish and unpublish need `content.publish`; scheduling (publish_at / unpublish_at) is
    deciding to publish, so it needs it too, and so does archiving or un-drafting a live page.
    A live page has nothing to schedule a publish for (422), and taking a page off the website
    clears `publish_at`, so a stale time can't bring it back (review M2).
  - COMPLIANCE (D-017): legal pages also need `legal.publish` to publish, unpublish, schedule,
    archive, delete, change while live or scheduled (review H2), or change kind to or from
    legal. Production refuses to publish a legal page whose text still says [DRAFT
    (page_rules.LEGAL_DRAFT), to leave that text on a live legal page, or to move it into or
    out of the legal kind (review M1).
  - D-015: sample pages can't be published in production.
  - Changing `seo` needs `seo.manage` (ARCHITECTURE §11).
  - Delete only drafts that were never published; otherwise archive (409 says so).
  - A slug change on a live page redirects the old path to the new one (308, collapsing chains).
  - `page.updated` is emitted only while the page is live.
  - A PATCH (or a blocks save) may send `expected_updated_at`, the page's `updated_at` when the
    editor loaded it; if the page changed since, 409 (review L7).

INVARIANT: every function commits once, after its audit row and events (common.py header).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from empire_api.content import page_rules
from empire_api.content.common import Editor, audit_row, event
from empire_api.content.models import Page
from empire_api.content.schemas_pages import PageInput, PageUpdate
from empire_api.errors import ApiProblem
from empire_api.pagination import PageParams
from empire_api.platform import audit
from empire_api.projects.common import (
    Actor,
    FieldError,
    commit,
    conflict,
    flush,
    invalid,
    jsonable,
    like_pattern,
    slug_or_error,
    snapshot,
)
from empire_api.seo import redirects
from empire_api.seo.checks import check_seo
from empire_api.seo.paths import RESERVED_PAGE_SLUGS, page_path
from empire_api.timeutil import utcnow

NO_PAGE: Final = "No page with this id."
SLUG_TAKEN: Final = "Another page already uses this web address. Choose a different one."
SLUG_CONFLICTS: Final = {"uq_page_slug": ("slug", SLUG_TAKEN)}
SLUG_RESERVED: Final = "This address is a section of the website. Choose a different one."
REQUIRED_FIXED: Final = "This page comes with the website: it keeps its web address and kind."
REQUIRED_STAYS: Final = "This page comes with the website: it can't be deleted or archived."
STALE: Final = (
    "Someone else saved this page since you opened it. Reload it to see their changes, then "
    "make yours again."
)
ALREADY_LIVE: Final = (
    "This page is already on the website, so there is no publish time to set. To take it down "
    "at a set time, use the unpublish time."
)
WAS_PUBLISHED: Final = (
    "This page has been on the website, so it can't be deleted. Archive it instead."
)
NOT_A_DRAFT: Final = "Only drafts can be deleted. Restore it to draft first, or keep it archived."
FUTURE: Final = "Choose a time in the future."
SCHEDULE_ORDER: Final = "The unpublish time must be after the publish time."
ARCHIVED_SCHEDULE: Final = "Restore the page to draft before scheduling it."
LEGAL_VERSION_ONLY: Final = "Only legal pages carry a version."
_AUDIT_SKIP: Final = ("updated_by",)
_SCHEDULE: Final = ("publish_at", "unpublish_at")
_PLAIN: Final = (
    "slug",
    "title",
    "kind",
    "publish_at",
    "unpublish_at",
    "show_in_nav",
    "nav_order",
    "legal_version",
)


@dataclass(frozen=True)
class PageFilters:
    q: str | None = None
    kind: str | None = None
    publish_state: str | None = None


def load_page(db: Session, page_id: uuid.UUID) -> Page:
    """A page with its blocks, fresh from the database, or 404."""
    page = db.scalar(
        select(Page)
        .where(Page.id == page_id)
        .options(selectinload(Page.blocks))
        .execution_options(populate_existing=True)
    )
    if page is None:
        raise ApiProblem(404, NO_PAGE)
    return page


def lock_page(db: Session, page_id: uuid.UUID) -> Page:
    """The page row, locked until commit (serialises every write to one page), or 404."""
    page = db.get(Page, page_id, with_for_update=True, populate_existing=True)
    if page is None:
        raise ApiProblem(404, NO_PAGE)
    return page


def list_pages(db: Session, paging: PageParams, filters: PageFilters) -> tuple[list[Page], int]:
    """The CMS list, most recent edit first. `q` matches title or slug, ignoring case."""
    stmt = select(Page)
    if filters.q and filters.q.strip():
        pattern = like_pattern(filters.q)
        stmt = stmt.where(
            or_(
                func.lower(Page.title).like(pattern, escape="\\"),
                Page.slug.like(pattern, escape="\\"),
            )
        )
    if filters.kind is not None:
        stmt = stmt.where(Page.kind == filters.kind)
    if filters.publish_state is not None:
        stmt = stmt.where(Page.publish_state == filters.publish_state)
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.options(selectinload(Page.blocks))
        .order_by(Page.updated_at.desc(), Page.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


# --- Checks shared by create and update ------------------------------------------------------


def check_fresh(page: Page, expected_updated_at: datetime | None) -> None:
    """409 when the editor's copy of the page is older than the saved one (module rules)."""
    if expected_updated_at is not None and expected_updated_at != page.updated_at:
        raise conflict(STALE, "expected_updated_at", STALE)


def _slug_errors(slug: str, page: Page | None) -> list[FieldError]:
    if page is not None and page.is_required:
        return [FieldError("slug", REQUIRED_FIXED)] if slug != page.slug else []
    if slug in RESERVED_PAGE_SLUGS:
        return [FieldError("slug", SLUG_RESERVED)]
    return []


def _slug_must_be_free(db: Session, slug: str, page_id: uuid.UUID | None) -> None:
    stmt = select(Page.id).where(Page.slug == slug)
    if page_id is not None:
        stmt = stmt.where(Page.id != page_id)
    if db.scalar(stmt) is not None:
        raise conflict(SLUG_TAKEN, "slug", SLUG_TAKEN)


def _schedule_errors(
    state: Mapping[str, Any], sent: Mapping[str, Any], now: datetime
) -> list[FieldError]:
    errors = [
        FieldError(key, FUTURE)
        for key in _SCHEDULE
        if sent.get(key) is not None and sent[key] <= now
    ]
    publish_at, unpublish_at = state.get("publish_at"), state.get("unpublish_at")
    if publish_at and unpublish_at and unpublish_at <= publish_at:
        errors.append(FieldError("unpublish_at", SCHEDULE_ORDER))
    if state.get("publish_state") == "archived" and sent.get("publish_at") is not None:
        errors.append(FieldError("publish_at", ARCHIVED_SCHEDULE))
    if state.get("publish_state") == "published" and sent.get("publish_at") is not None:
        errors.append(FieldError("publish_at", ALREADY_LIVE))
    if state.get("legal_version") and state.get("kind") != "legal":
        errors.append(FieldError("legal_version", LEGAL_VERSION_ONLY))
    return errors


def _check_rights(editor: Editor, page: Page | None, changes: Mapping[str, Any]) -> None:
    """SECURITY: the permissions a change needs beyond the route's `content.write` (header)."""
    kind_before = page.kind if page else None
    kind_after = changes.get("kind", kind_before)
    if any(key in changes for key in _SCHEDULE):
        editor.need("content.publish", page_rules.NO_SCHEDULE_RIGHTS)
    touches_legal = "legal" in (kind_before, kind_after)
    legal_kind_change = touches_legal and kind_before is not None and kind_before != kind_after
    guarded = page is not None and page_rules.legal_guarded(page)  # live or scheduled (H2)
    scheduled_legal = kind_after == "legal" and any(key in changes for key in _SCHEDULE)
    if legal_kind_change or guarded or scheduled_legal:
        editor.need("legal.publish", page_rules.LEGAL_ONLY)
    if "seo" in changes:
        editor.need("seo.manage", page_rules.NO_SEO_RIGHTS)


# --- Create and update -----------------------------------------------------------------------


def create_page(db: Session, editor: Editor, body: PageInput) -> Page:
    """A new draft. The slug comes from the title unless given; a taken slug is a 409."""
    values = body.model_dump(include=set(_PLAIN))
    values["slug"] = slug_or_error(body.slug, body.title)
    seo = jsonable(body.seo.model_dump(exclude_defaults=True))
    asked = {key: values[key] for key in _SCHEDULE if values[key] is not None}
    _check_rights(editor, None, {"kind": body.kind, **asked, **({"seo": seo} if seo else {})})
    errors = _slug_errors(values["slug"], None)
    errors += _schedule_errors({**values, "publish_state": "draft"}, asked, utcnow())
    errors += check_seo(db, seo)
    if errors:
        raise invalid(errors)
    _slug_must_be_free(db, values["slug"], None)
    page = Page(
        **values,
        seo=seo,
        translations=body.translations.root,
        publish_state="draft",
        created_by=editor.user_id,
        updated_by=editor.user_id,
    )
    db.add(page)
    flush(db, SLUG_CONFLICTS)
    audit_row(
        db,
        editor,
        action="page.created",
        entity_type="page",
        entity_id=page.id,
        changes=audit.diff({}, snapshot(page, _AUDIT_SKIP)),
    )
    commit(db, SLUG_CONFLICTS)
    return page


def _columns(page: Page, sent: Mapping[str, Any]) -> dict[str, Any]:
    """PATCH body → changed column values (`seo` merges into the stored JSON)."""
    changes = {key: sent[key] for key in _PLAIN if key in sent and sent[key] != getattr(page, key)}
    if "seo" in sent:
        merged = {**page.seo, **jsonable(sent["seo"])}
        if merged != page.seo:
            changes["seo"] = merged
    if "translations" in sent and sent["translations"] != page.translations:
        changes["translations"] = sent["translations"]
    if changes.get("kind", page.kind) != "legal" and page.legal_version is not None:
        changes.setdefault("legal_version", None)
    return changes


def update_page(db: Session, editor: Editor, page_id: uuid.UUID, body: PageUpdate) -> None:
    """Apply a PATCH (module rules). Nothing changed → nothing is written.

    How it works:
      1. Lock the page; refuse a stale copy (409); turn the body into changes; check the
         permissions they need.
      2. Validate the merged values (slug, schedule, legal version, share image); 409 for a
         taken slug, or for draft legal text that would be live or change kind (production).
      3. Apply, including archive/restore; taking a live page down clears `publish_at` unless
         this request sets a new one; on a live page a slug change leaves a redirect.
      4. One audit row with the diff, and the event the change implies; commit.
    """
    page = lock_page(db, page_id)  # 1
    sent = body.model_dump(exclude_unset=True)
    check_fresh(page, sent.pop("expected_updated_at", None))
    target = sent.pop("publish_state", None)
    changes = _columns(page, sent)
    _check_rights(editor, page, changes)
    was = page.publish_state
    if target is not None and target != was:
        _check_transition(editor, page, target)
    state = {c.key: getattr(page, c.key) for c in Page.__table__.columns} | changes  # 2
    state["publish_state"] = target or was
    errors = _schedule_errors(state, {k: v for k, v in sent.items() if k in changes}, utcnow())
    errors += _slug_errors(changes["slug"], page) if "slug" in changes else []
    errors += _kind_errors(page, changes)
    errors += check_seo(db, changes["seo"]) if "seo" in changes else []
    if errors:
        raise invalid(errors)
    _check_draft_text(page, state)
    if "slug" in changes:
        _slug_must_be_free(db, changes["slug"], page.id)
    before = snapshot(page, _AUDIT_SKIP)
    for key, value in changes.items():  # 3
        setattr(page, key, value)
    if target is not None and target != was:
        page.publish_state = target
        if target == "archived":
            page.publish_at = page.unpublish_at = None
        elif was == "published" and "publish_at" not in changes:
            page.publish_at = None  # M2: a stale publish time must not bring it back
    flush(db, SLUG_CONFLICTS)
    diff = audit.diff(before, snapshot(page, _AUDIT_SKIP))
    if not diff:
        db.rollback()
        return
    page.updated_by = editor.user_id
    if was == "published" and page.publish_state == "published" and "slug" in diff:
        redirects.slug_changed(db, editor, "page", page_path(before["slug"]), page_path(page.slug))
    audit_row(  # 4
        db,
        editor,
        action=_action(was, page.publish_state),
        entity_type="page",
        entity_id=page.id,
        changes=diff,
    )
    if was == "published" and page.publish_state != "published":
        page_event(db, editor, page, "page.unpublished", reason=page.publish_state)
    elif page.publish_state == "published":
        extra = {"previous_path": page_path(before["slug"])} if "slug" in diff else {}
        page_event(db, editor, page, "page.updated", changed=sorted(diff), **extra)
    commit(db, SLUG_CONFLICTS)


def _kind_errors(page: Page, changes: Mapping[str, Any]) -> list[FieldError]:
    if page.is_required and "kind" in changes:
        return [FieldError("kind", REQUIRED_FIXED)]
    return []


def _check_draft_text(page: Page, state: Mapping[str, Any]) -> None:
    """COMPLIANCE (D-017, review M1): in production, 409 when the PATCH would move [DRAFT text
    into or out of the legal kind, or leave it on a live legal page (only the title changes
    here; page_blocks.py checks the blocks)."""
    blocks = [block.data for block in page.blocks]
    if page_rules.moves_draft_text(page.kind, state["kind"], state["title"], blocks):
        raise page_rules.legal_draft_conflict("kind")
    if page_rules.leaves_draft_text_live(
        state["kind"], state["publish_state"], state["title"], blocks
    ):
        raise page_rules.legal_draft_conflict("title")


def _check_transition(editor: Editor, page: Page, target: str) -> None:
    """Archive or restore. SECURITY: taking a live page off the site is publishing work."""
    if page.is_required and target == "archived":
        raise conflict(REQUIRED_STAYS)
    if page.publish_state == "published":
        editor.need("content.publish", page_rules.NOT_ALLOWED_OFF_SITE)
    if page.kind == "legal":
        editor.need("legal.publish", page_rules.LEGAL_ONLY)


def _action(was: str, now: str) -> str:
    if was == now:
        return "page.updated"
    if now == "archived":
        return "page.archived"
    return "page.unpublished" if was == "published" else "page.restored"


def page_event(db: Session, actor: Actor | None, page: Page, type_: str, **data: Any) -> None:
    """`page.*` events name the page and its path, so consumers revalidate it (§5, §9)."""
    event(
        db,
        actor,
        type_,
        aggregate_type="page",
        aggregate_id=page.id,
        page_id=page.id,
        slug=page.slug,
        path=page_path(page.slug),
        kind=page.kind,
        **data,
    )


# --- Delete, publish, unpublish --------------------------------------------------------------


def delete_page(db: Session, editor: Editor, page_id: uuid.UUID) -> None:
    """Delete a draft that was never published, with its blocks and media links.

    INVARIANT: `published_at` is never cleared (models.py), so it tells "never published".
    """
    page = lock_page(db, page_id)
    if page.is_required:
        raise conflict(REQUIRED_STAYS)
    if page.kind == "legal":
        editor.need("legal.publish", page_rules.LEGAL_ONLY)
    if page.published_at is not None:
        raise conflict(WAS_PUBLISHED)
    if page.publish_state != "draft":
        raise conflict(NOT_A_DRAFT)
    audit_row(
        db,
        editor,
        action="page.deleted",
        entity_type="page",
        entity_id=page.id,
        changes={k: [v, None] for k, v in snapshot(page, _AUDIT_SKIP).items()},
    )
    db.delete(page)
    commit(db)


def go_live(db: Session, actor: Actor | None, page: Page, *, scheduled: bool = False) -> None:
    """Put a checked page on the website (manual publish or the schedule tick). No commit.

    Going live claims the page's path: a redirect from it would hide the page (redirects.py).
    """
    now = utcnow()
    was = page.publish_state
    page.publish_state = "published"
    page.published_at = page.published_at or now
    page.publish_at = None
    if page.unpublish_at is not None and page.unpublish_at <= now:
        page.unpublish_at = None
    page.updated_by = actor.user_id if actor else page.updated_by
    redirects.claim_path(db, actor, page_path(page.slug))
    audit_row(
        db,
        actor,
        action="page.published",
        entity_type="page",
        entity_id=page.id,
        changes={"publish_state": [was, "published"], "scheduled": [None, scheduled]},
    )
    page_event(db, actor, page, "page.published", scheduled=scheduled)


def take_down(db: Session, actor: Actor | None, page: Page, *, scheduled: bool = False) -> None:
    """Take a live page off the website (back to draft). No commit.

    Clears `publish_at` as well as `unpublish_at` (review M2): a publish time left from before
    would otherwise make the next tick put the page straight back.
    """
    page.publish_state = "draft"
    page.publish_at = page.unpublish_at = None
    page.updated_by = actor.user_id if actor else page.updated_by
    audit_row(
        db,
        actor,
        action="page.unpublished",
        entity_type="page",
        entity_id=page.id,
        changes={"publish_state": ["published", "draft"], "scheduled": [None, scheduled]},
    )
    page_event(db, actor, page, "page.unpublished", reason="draft", scheduled=scheduled)


def publish_page(db: Session, editor: Editor, page_id: uuid.UUID) -> None:
    """Put the page on the website, or 409 listing every blocker. Already live: no change."""
    page = lock_page(db, page_id)
    if page.kind == "legal":
        editor.need("legal.publish", page_rules.LEGAL_ONLY)
    if page.publish_state == "published":
        return
    blockers = page_rules.page_blockers(page)
    if blockers:
        raise ApiProblem(
            409,
            "This page can't be published yet: " + "; ".join(blockers) + ".",
            title="Publish blocked",
            errors=[{"field": "publish", "message": message} for message in blockers],
        )
    go_live(db, editor, page)
    commit(db)


def unpublish_page(db: Session, editor: Editor, page_id: uuid.UUID) -> None:
    """Take the page off the website (back to draft). No-op when it isn't live."""
    page = lock_page(db, page_id)
    if page.kind == "legal":
        editor.need("legal.publish", page_rules.LEGAL_ONLY)
    if page.publish_state != "published":
        return
    take_down(db, editor, page)
    commit(db)
