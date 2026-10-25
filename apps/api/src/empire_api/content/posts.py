"""Business rules for blog and news posts: list, load, create, update (including archive and
restore), delete, publish and unpublish.

Collaborators: page_rules.py (blockers), common.py (Editor, audit, events), media/content_links.py
(the cover is a `media_link`, role `cover`), seo/redirects.py, seo/checks.py, routes_pages.py.
Implements: ARCHITECTURE §6 (publishing, deletion), §9 (`post.*` events), §11, §16; D-015.

Rules:
  - The author is the staff member who created the post. The cover is an image in the library
    with an honest label (COMPLIANCE, D-033, review L11: covers often show renders; sample
    placeholders are exempt, D-015).
  - Publish and unpublish need `content.publish`; `published_at` is set on the first publish and
    kept (the article's date). Archiving or un-drafting a live post needs it too.
  - Changing `seo` needs `seo.manage`. Sample posts can't be published in production (D-015).
  - Delete only drafts that were never published; otherwise archive.
  - A slug change on a live post redirects the old path to the new one (308).

INVARIANT: every function commits once, after its audit row and events (common.py header).
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from empire_api.content import page_rules
from empire_api.content.block_refs import LABEL_FIRST
from empire_api.content.common import Editor, audit_row, event
from empire_api.content.models import Post
from empire_api.content.schemas_pages import PostInput, PostUpdate
from empire_api.errors import ApiProblem
from empire_api.media.content_links import library_facts, post_cover_id, set_links
from empire_api.media.rules import Owner
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
from empire_api.seo.paths import post_path
from empire_api.timeutil import utcnow

NO_POST: Final = "No post with this id."
SLUG_TAKEN: Final = "Another post already uses this web address. Choose a different one."
SLUG_CONFLICTS: Final = {"uq_post_slug": ("slug", SLUG_TAKEN)}
COVER_IMAGE: Final = "Choose an image from the media library for the cover."
WAS_PUBLISHED: Final = (
    "This post has been on the website, so it can't be deleted. Archive it instead."
)
NOT_A_DRAFT: Final = "Only drafts can be deleted. Restore it to draft first, or keep it archived."
_AUDIT_SKIP: Final = ("updated_by",)
_PLAIN: Final = ("slug", "title", "excerpt", "body", "category", "tags")


@dataclass(frozen=True)
class PostFilters:
    q: str | None = None
    publish_state: str | None = None
    category: str | None = None


def load_post(db: Session, post_id: uuid.UUID) -> Post:
    post = db.scalar(
        select(Post).where(Post.id == post_id).execution_options(populate_existing=True)
    )
    if post is None:
        raise ApiProblem(404, NO_POST)
    return post


def lock_post(db: Session, post_id: uuid.UUID) -> Post:
    post = db.get(Post, post_id, with_for_update=True, populate_existing=True)
    if post is None:
        raise ApiProblem(404, NO_POST)
    return post


def list_posts(db: Session, paging: PageParams, filters: PostFilters) -> tuple[list[Post], int]:
    """Newest first (published date, else last edit). `q` matches title or slug."""
    stmt = select(Post)
    if filters.q and filters.q.strip():
        pattern = like_pattern(filters.q)
        stmt = stmt.where(
            or_(
                func.lower(Post.title).like(pattern, escape="\\"),
                Post.slug.like(pattern, escape="\\"),
            )
        )
    if filters.publish_state is not None:
        stmt = stmt.where(Post.publish_state == filters.publish_state)
    if filters.category is not None:
        stmt = stmt.where(func.lower(Post.category) == filters.category.strip().lower())
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.scalars(
        stmt.order_by(func.coalesce(Post.published_at, Post.updated_at).desc(), Post.id.desc())
        .offset(paging.offset)
        .limit(paging.per_page)
    ).all()
    return list(rows), total


def _cover_errors(db: Session, cover_id: uuid.UUID | None) -> list[FieldError]:
    if cover_id is None:
        return []
    found = library_facts(db, [cover_id]).get(cover_id)
    if found is None or found.kind != "image":
        return [FieldError("cover_media_id", COVER_IMAGE)]
    if not found.has_label and not found.is_sample:
        return [FieldError("cover_media_id", LABEL_FIRST)]
    return []


def _slug_must_be_free(db: Session, slug: str, post_id: uuid.UUID | None) -> None:
    stmt = select(Post.id).where(Post.slug == slug)
    if post_id is not None:
        stmt = stmt.where(Post.id != post_id)
    if db.scalar(stmt) is not None:
        raise conflict(SLUG_TAKEN, "slug", SLUG_TAKEN)


def post_event(db: Session, actor: Actor | None, post: Post, type_: str, **data: Any) -> None:
    event(
        db,
        actor,
        type_,
        aggregate_type="post",
        aggregate_id=post.id,
        post_id=post.id,
        slug=post.slug,
        path=post_path(post.slug),
        **data,
    )


# --- Create and update -----------------------------------------------------------------------


def create_post(db: Session, editor: Editor, body: PostInput) -> Post:
    """A new draft by this editor. The slug comes from the title unless given."""
    values = body.model_dump(include=set(_PLAIN))
    values["slug"] = slug_or_error(body.slug, body.title)
    seo = jsonable(body.seo.model_dump(exclude_defaults=True))
    if seo:
        editor.need("seo.manage", page_rules.NO_SEO_RIGHTS)
    errors = check_seo(db, seo) + _cover_errors(db, body.cover_media_id)
    if errors:
        raise invalid(errors)
    _slug_must_be_free(db, values["slug"], None)
    post = Post(
        **values,
        seo=seo,
        translations=body.translations.root,
        author_id=editor.user_id,
        publish_state="draft",
        created_by=editor.user_id,
        updated_by=editor.user_id,
    )
    db.add(post)
    flush(db, SLUG_CONFLICTS)
    covers = [body.cover_media_id] if body.cover_media_id else []
    set_links(db, Owner("post", post.id), "cover", covers)
    after = snapshot(post, _AUDIT_SKIP) | {"cover_media_id": body.cover_media_id}
    audit_row(
        db,
        editor,
        action="post.created",
        entity_type="post",
        entity_id=post.id,
        changes=audit.diff({}, jsonable(after)),
    )
    commit(db, SLUG_CONFLICTS)
    return post


def _columns(post: Post, sent: Mapping[str, Any]) -> dict[str, Any]:
    changes = {key: sent[key] for key in _PLAIN if key in sent and sent[key] != getattr(post, key)}
    if "seo" in sent:
        merged = {**post.seo, **jsonable(sent["seo"])}
        if merged != post.seo:
            changes["seo"] = merged
    if "translations" in sent and sent["translations"] != post.translations:
        changes["translations"] = sent["translations"]
    return changes


def update_post(db: Session, editor: Editor, post_id: uuid.UUID, body: PostUpdate) -> None:
    """Apply a PATCH (module rules). Nothing changed → nothing is written."""
    post = lock_post(db, post_id)
    sent = body.model_dump(exclude_unset=True)
    target = sent.pop("publish_state", None)
    changes = _columns(post, sent)
    cover_before = post_cover_id(db, post.id)
    cover_after = sent.get("cover_media_id", cover_before)
    was = post.publish_state
    if "seo" in changes:
        editor.need("seo.manage", page_rules.NO_SEO_RIGHTS)
    if target is not None and target != was and was == "published":
        editor.need("content.publish", page_rules.NOT_ALLOWED_OFF_SITE)
    errors = check_seo(db, changes["seo"]) if "seo" in changes else []
    if cover_after != cover_before:
        errors += _cover_errors(db, cover_after)
    if errors:
        raise invalid(errors)
    if "slug" in changes:
        _slug_must_be_free(db, changes["slug"], post.id)
    before = snapshot(post, _AUDIT_SKIP) | {"cover_media_id": cover_before}
    for key, value in changes.items():
        setattr(post, key, value)
    if target is not None:
        post.publish_state = target
    flush(db, SLUG_CONFLICTS)
    if cover_after != cover_before:
        set_links(db, Owner("post", post.id), "cover", [cover_after] if cover_after else [])
    diff = audit.diff(
        jsonable(before), jsonable(snapshot(post, _AUDIT_SKIP) | {"cover_media_id": cover_after})
    )
    if not diff:
        db.rollback()
        return
    post.updated_by = editor.user_id
    post.updated_at = func.now()
    if was == "published" and post.publish_state == "published" and "slug" in diff:
        redirects.slug_changed(db, editor, "post", post_path(before["slug"]), post_path(post.slug))
    audit_row(
        db,
        editor,
        action=_action(was, post.publish_state),
        entity_type="post",
        entity_id=post.id,
        changes=diff,
    )
    if was == "published" and post.publish_state != "published":
        post_event(db, editor, post, "post.unpublished", reason=post.publish_state)
    elif post.publish_state == "published":
        extra = {"previous_path": post_path(before["slug"])} if "slug" in diff else {}
        post_event(db, editor, post, "post.updated", changed=sorted(diff), **extra)
    commit(db, SLUG_CONFLICTS)


def _action(was: str, now: str) -> str:
    if was == now:
        return "post.updated"
    if now == "archived":
        return "post.archived"
    return "post.unpublished" if was == "published" else "post.restored"


# --- Delete, publish, unpublish --------------------------------------------------------------


def delete_post(db: Session, editor: Editor, post_id: uuid.UUID) -> None:
    """Delete a draft that was never published (its cover link goes with it)."""
    post = lock_post(db, post_id)
    if post.published_at is not None:
        raise conflict(WAS_PUBLISHED)
    if post.publish_state != "draft":
        raise conflict(NOT_A_DRAFT)
    audit_row(
        db,
        editor,
        action="post.deleted",
        entity_type="post",
        entity_id=post.id,
        changes={k: [v, None] for k, v in snapshot(post, _AUDIT_SKIP).items()},
    )
    db.delete(post)
    commit(db)


def publish_post(db: Session, editor: Editor, post_id: uuid.UUID) -> None:
    """Put the post on the website, or 409 listing every blocker. Already live: no change."""
    post = lock_post(db, post_id)
    if post.publish_state == "published":
        return
    blockers = page_rules.post_blockers(post)
    if blockers:
        raise ApiProblem(
            409,
            "This post can't be published yet: " + "; ".join(blockers) + ".",
            title="Publish blocked",
            errors=[{"field": "publish", "message": message} for message in blockers],
        )
    was = post.publish_state
    post.publish_state = "published"
    post.published_at = post.published_at or utcnow()
    post.updated_by = editor.user_id
    redirects.claim_path(db, editor, post_path(post.slug))
    audit_row(
        db,
        editor,
        action="post.published",
        entity_type="post",
        entity_id=post.id,
        changes={"publish_state": [was, "published"]},
    )
    post_event(db, editor, post, "post.published")
    commit(db)


def unpublish_post(db: Session, editor: Editor, post_id: uuid.UUID) -> None:
    """Take the post off the website (back to draft). No-op when it isn't live."""
    post = lock_post(db, post_id)
    if post.publish_state != "published":
        return
    post.publish_state = "draft"
    post.updated_by = editor.user_id
    audit_row(
        db,
        editor,
        action="post.unpublished",
        entity_type="post",
        entity_id=post.id,
        changes={"publish_state": ["published", "draft"]},
    )
    post_event(db, editor, post, "post.unpublished", reason="draft")
    commit(db)
