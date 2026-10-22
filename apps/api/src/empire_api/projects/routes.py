"""Project endpoints: /api/v1/admin/projects (design contract tag "Projects").

HTTP only: services hold the rules (service.py, children.py). Permissions (ARCHITECTURE §11):
read `projects.read`; create, edit, duplicate and amenities `projects.write`; publish and
unpublish `projects.publish`; delete `projects.delete`. Children are in routes_children.py.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.pagination import PageParams, page_params
from empire_api.platform.crypto import client_ip
from empire_api.projects import blockers, children, present, service
from empire_api.projects.common import Actor
from empire_api.projects.schemas import ProjectAdmin, ProjectInput, ProjectList, ProjectUpdate
from empire_api.projects.schemas_catalogue import Amenity
from empire_api.projects.schemas_children import ProjectAmenitiesInput
from empire_api.projects.vocab import ProjectStatus, PublishState, SalesStatus
from empire_api.users.deps import require, staff
from empire_api.users.roles import has_permission
from empire_api.users.schemas import PageMeta
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Projects"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]
# The contract names the path parameter `id`; `project_id` in Python avoids shadowing id().
ProjectId = Annotated[uuid.UUID, Path(alias="id")]
Reader = Annotated[SessionInfo, Depends(require("projects.read"))]
Writer = Annotated[SessionInfo, Depends(require("projects.write"))]
Publisher = Annotated[SessionInfo, Depends(require("projects.publish"))]
Deleter = Annotated[SessionInfo, Depends(require("projects.delete"))]
CONFLICT = problem_responses(409)


def actor_of(info: SessionInfo, request: Request) -> Actor:
    return Actor(
        user_id=info.user.id,
        ip=client_ip(request),
        can_publish=has_permission(info.user.role, "projects.publish"),
    )


def admin_view(db: Session, project_id: uuid.UUID) -> ProjectAdmin:
    """The project as the CMS sees it, read fresh after any change."""
    db.expire_all()
    project = service.load_project(db, project_id)
    return present.project_admin(project, blockers.publish_blockers(db, project))


@router.get(
    "/projects", response_model=ProjectList, operation_id="list_projects", **staff("projects.read")
)
def list_projects(
    actor: Reader,
    db: Db,
    paging: Paging,
    q: Annotated[str | None, Query(max_length=100, description="Name or slug contains")] = None,
    status: ProjectStatus | None = None,
    publish_state: PublishState | None = None,
    sales_status: SalesStatus | None = None,
    city: uuid.UUID | None = None,
) -> ProjectList:
    """Projects, most recently edited first, with the CMS list's filters."""
    filters = service.ProjectFilters(q, status, publish_state, sales_status, city)
    rows, total = service.list_projects(db, paging, filters)
    return ProjectList(
        items=[present.project_summary(p) for p in rows], meta=PageMeta(**paging.meta(total))
    )


@router.post(
    "/projects",
    status_code=201,
    response_model=ProjectAdmin,
    operation_id="create_project",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def create_project(body: ProjectInput, actor: Writer, request: Request, db: Db) -> ProjectAdmin:
    """Create a draft. The slug is made from the name when left out; a taken slug is 409."""
    project = service.create_project(db, body, actor_of(actor, request))
    return admin_view(db, project.id)


@router.get(
    "/projects/{id}",
    response_model=ProjectAdmin,
    operation_id="get_project",
    **staff("projects.read"),
)
def get_project(project_id: ProjectId, actor: Reader, db: Db) -> ProjectAdmin:
    """The project with every child, the publish blockers and empty media placeholders."""
    return admin_view(db, project_id)


@router.patch(
    "/projects/{id}",
    response_model=ProjectAdmin,
    operation_id="update_project",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def update_project(
    project_id: ProjectId, body: ProjectUpdate, actor: Writer, request: Request, db: Db
) -> ProjectAdmin:
    """Change the fields sent. `publish_state: "archived"` archives; `"draft"` restores.
    Taking a published project off the website this way needs `projects.publish`."""
    service.update_project(db, project_id, body, actor_of(actor, request))
    return admin_view(db, project_id)


@router.delete(
    "/projects/{id}",
    status_code=204,
    operation_id="delete_project",
    responses=CONFLICT,
    description="Allowed only for drafts that were never published; otherwise archive.",
    **staff("projects.delete", write=True),
)
def delete_project(project_id: ProjectId, actor: Deleter, request: Request, db: Db) -> Response:
    service.delete_project(db, project_id, actor_of(actor, request))
    return Response(status_code=204)


@router.post(
    "/projects/{id}/publish",
    response_model=ProjectAdmin,
    operation_id="publish_project",
    responses=CONFLICT,
    summary="Publish (blocked until RERA number and QR are present)",
    **staff("projects.publish", write=True),
)
def publish_project(
    project_id: ProjectId, actor: Publisher, request: Request, db: Db
) -> ProjectAdmin:
    """409 problem+json listing every blocker in `errors[]` when it can't go live yet."""
    service.publish_project(db, project_id, actor_of(actor, request))
    return admin_view(db, project_id)


@router.post(
    "/projects/{id}/unpublish",
    response_model=ProjectAdmin,
    operation_id="unpublish_project",
    summary="Unpublish (back to draft)",
    **staff("projects.publish", write=True),
)
def unpublish_project(
    project_id: ProjectId, actor: Publisher, request: Request, db: Db
) -> ProjectAdmin:
    service.unpublish_project(db, project_id, actor_of(actor, request))
    return admin_view(db, project_id)


@router.post(
    "/projects/{id}/duplicate",
    status_code=201,
    response_model=ProjectAdmin,
    operation_id="duplicate_project",
    summary="Copy as a new draft",
    **staff("projects.write", write=True),
)
def duplicate_project(
    project_id: ProjectId, actor: Writer, request: Request, db: Db
) -> ProjectAdmin:
    """A draft copy (slug `<slug>-copy`, `-copy-2`, …) with every child; media isn't copied."""
    copy_id = service.duplicate_project(db, project_id, actor_of(actor, request))
    return admin_view(db, copy_id)


@router.put(
    "/projects/{id}/amenities",
    response_model=list[Amenity],
    operation_id="set_project_amenities",
    summary="Set the project's amenities (ordered list)",
    **staff("projects.write", write=True),
)
def set_project_amenities(
    project_id: ProjectId,
    body: ProjectAmenitiesInput,
    actor: Writer,
    request: Request,
    db: Db,
) -> list[Amenity]:
    rows = children.set_amenities(db, project_id, body.amenity_ids, actor_of(actor, request))
    return [present.amenity_out(row) for row in rows]
