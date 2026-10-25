"""Page and post endpoints: /api/v1/admin/pages/** and /api/v1/admin/posts/** (design contract
tag "Content").

HTTP only: the rules are in pages.py, page_blocks.py and posts.py. Permissions (ARCHITECTURE
§11): reading `content.read`; creating, editing, blocks and delete `content.write`; publish and
unpublish `content.publish`. The services add `legal.publish` (legal pages), `content.publish`
(scheduling, archiving a live page) and `seo.manage` (SEO fields) where a change needs them.
TODO(phase-5): the public `/api/v1/public/pages/{slug}`, `/posts` and `/posts/{slug}`.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from empire_api.content import page_blocks, pages, posts, present
from empire_api.content.common import editor_of
from empire_api.content.schemas_pages import (
    Page,
    PageBlocksInput,
    PageInput,
    PageList,
    PageUpdate,
    Post,
    PostInput,
    PostList,
    PostUpdate,
)
from empire_api.content.vocab import PageKind
from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.pagination import PageParams, page_params
from empire_api.projects.vocab import PublishState
from empire_api.users.deps import require, staff
from empire_api.users.schemas import PageMeta
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Content"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]
Reader = Annotated[SessionInfo, Depends(require("content.read"))]
Writer = Annotated[SessionInfo, Depends(require("content.write"))]
Publisher = Annotated[SessionInfo, Depends(require("content.publish"))]
ItemId = Annotated[uuid.UUID, Path(alias="id")]
Search = Annotated[str | None, Query(max_length=100, description="Title or slug contains")]
CONFLICT = problem_responses(409)


def page_view(db: Session, page_id: uuid.UUID) -> Page:
    db.expire_all()
    return present.page_out(db, pages.load_page(db, page_id))


def post_view(db: Session, post_id: uuid.UUID) -> Post:
    db.expire_all()
    return present.post_out(db, posts.load_post(db, post_id))


# --- Pages -----------------------------------------------------------------------------------


@router.get(
    "/pages",
    response_model=PageList,
    operation_id="list_pages",
    summary="List pages",
    **staff("content.read"),
)
def list_pages(
    actor: Reader,
    db: Db,
    paging: Paging,
    q: Search = None,
    kind: PageKind | None = None,
    publish_state: PublishState | None = None,
) -> PageList:
    """Most recently edited first. Rows are PageSummary (no blocks)."""
    rows, total = pages.list_pages(db, paging, pages.PageFilters(q, kind, publish_state))
    return PageList(items=present.page_summaries(db, rows), meta=PageMeta(**paging.meta(total)))


@router.post(
    "/pages",
    status_code=201,
    response_model=Page,
    operation_id="create_page",
    summary="Create page",
    responses=CONFLICT,
    **staff("content.write", write=True),
)
def create_page(body: PageInput, actor: Writer, request: Request, db: Db) -> Page:
    """A draft. Kind standard, landing or legal (system pages come with the site)."""
    page = pages.create_page(db, editor_of(actor, request), body)
    return page_view(db, page.id)


@router.get(
    "/pages/{id}",
    response_model=Page,
    operation_id="get_page",
    summary="Get page",
    **staff("content.read"),
)
def get_page(page_id: ItemId, actor: Reader, db: Db) -> Page:
    return page_view(db, page_id)


@router.patch(
    "/pages/{id}",
    response_model=Page,
    operation_id="update_page",
    summary="Update page",
    responses=CONFLICT,
    **staff("content.write", write=True),
)
def update_page(page_id: ItemId, body: PageUpdate, actor: Writer, request: Request, db: Db) -> Page:
    """Change the fields sent. `publish_state: archived` archives; `draft` restores. A slug
    change on a live page leaves a 308 redirect from the old address. 409 when the page was
    saved since `expected_updated_at`."""
    pages.update_page(db, editor_of(actor, request), page_id, body)
    return page_view(db, page_id)


@router.delete(
    "/pages/{id}",
    status_code=204,
    operation_id="delete_page",
    summary="Delete page",
    responses=CONFLICT,
    description="Only drafts that were never published; otherwise archive. Never system pages.",
    **staff("content.write", write=True),
)
def delete_page(page_id: ItemId, actor: Writer, request: Request, db: Db) -> Response:
    pages.delete_page(db, editor_of(actor, request), page_id)
    return Response(status_code=204)


@router.put(
    "/pages/{id}/blocks",
    response_model=Page,
    operation_id="set_page_blocks",
    summary="Save the page's blocks (full ordered list)",
    responses=CONFLICT,
    **staff("content.write", write=True),
)
def set_page_blocks(
    page_id: ItemId, body: PageBlocksInput, actor: Writer, request: Request, db: Db
) -> Page:
    """Blocks left out are deleted. 422 names each problem, e.g. `blocks.2.data.href`. 409 when
    the page was saved since `expected_updated_at`, or (production) for DRAFT legal text on a
    live legal page."""
    page_blocks.set_blocks(
        db, editor_of(actor, request), page_id, body.blocks, body.expected_updated_at
    )
    return page_view(db, page_id)


@router.post(
    "/pages/{id}/publish",
    response_model=Page,
    operation_id="publish_page",
    summary="Publish (legal pages need legal.publish)",
    responses=CONFLICT,
    **staff("content.publish", write=True),
)
def publish_page(page_id: ItemId, actor: Publisher, request: Request, db: Db) -> Page:
    """409 listing every blocker (sample data or draft legal text in production)."""
    pages.publish_page(db, editor_of(actor, request), page_id)
    return page_view(db, page_id)


@router.post(
    "/pages/{id}/unpublish",
    response_model=Page,
    operation_id="unpublish_page",
    summary="Unpublish",
    **staff("content.publish", write=True),
)
def unpublish_page(page_id: ItemId, actor: Publisher, request: Request, db: Db) -> Page:
    pages.unpublish_page(db, editor_of(actor, request), page_id)
    return page_view(db, page_id)


# --- Posts -----------------------------------------------------------------------------------


@router.get(
    "/posts",
    response_model=PostList,
    operation_id="list_posts",
    summary="List posts",
    **staff("content.read"),
)
def list_posts(
    actor: Reader,
    db: Db,
    paging: Paging,
    q: Search = None,
    publish_state: PublishState | None = None,
    category: Annotated[str | None, Query(max_length=40)] = None,
) -> PostList:
    """Newest first. Rows are PostSummary (no body). `category` is an addition."""
    rows, total = posts.list_posts(db, paging, posts.PostFilters(q, publish_state, category))
    return PostList(items=present.post_summaries(db, rows), meta=PageMeta(**paging.meta(total)))


@router.post(
    "/posts",
    status_code=201,
    response_model=Post,
    operation_id="create_post",
    summary="Create post",
    responses=CONFLICT,
    **staff("content.write", write=True),
)
def create_post(body: PostInput, actor: Writer, request: Request, db: Db) -> Post:
    post = posts.create_post(db, editor_of(actor, request), body)
    return post_view(db, post.id)


@router.get(
    "/posts/{id}",
    response_model=Post,
    operation_id="get_post",
    summary="Get post",
    **staff("content.read"),
)
def get_post(post_id: ItemId, actor: Reader, db: Db) -> Post:
    return post_view(db, post_id)


@router.patch(
    "/posts/{id}",
    response_model=Post,
    operation_id="update_post",
    summary="Update post",
    responses=CONFLICT,
    **staff("content.write", write=True),
)
def update_post(post_id: ItemId, body: PostUpdate, actor: Writer, request: Request, db: Db) -> Post:
    """`publish_state: archived` archives; `draft` restores. A slug change on a live post
    leaves a 308 redirect from the old address."""
    posts.update_post(db, editor_of(actor, request), post_id, body)
    return post_view(db, post_id)


@router.delete(
    "/posts/{id}",
    status_code=204,
    operation_id="delete_post",
    summary="Delete post",
    responses=CONFLICT,
    description="Only drafts that were never published; otherwise archive.",
    **staff("content.write", write=True),
)
def delete_post(post_id: ItemId, actor: Writer, request: Request, db: Db) -> Response:
    posts.delete_post(db, editor_of(actor, request), post_id)
    return Response(status_code=204)


@router.post(
    "/posts/{id}/publish",
    response_model=Post,
    operation_id="publish_post",
    summary="Publish",
    responses=CONFLICT,
    **staff("content.publish", write=True),
)
def publish_post(post_id: ItemId, actor: Publisher, request: Request, db: Db) -> Post:
    posts.publish_post(db, editor_of(actor, request), post_id)
    return post_view(db, post_id)


@router.post(
    "/posts/{id}/unpublish",
    response_model=Post,
    operation_id="unpublish_post",
    summary="Unpublish",
    **staff("content.publish", write=True),
)
def unpublish_post(post_id: ItemId, actor: Publisher, request: Request, db: Db) -> Post:
    posts.unpublish_post(db, editor_of(actor, request), post_id)
    return post_view(db, post_id)
