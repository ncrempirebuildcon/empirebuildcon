"""Endpoints for a project's ordered children (design contract tag "Projects"):
/api/v1/admin/projects/{id}/{towers|configurations|specifications|location-advantages|
construction-updates|payment-plans}, each with list, create, update, delete and reorder.

The thirty routes are registered by one factory, so every collection gets the same
permissions (read `projects.read`, writes `projects.write`), status codes and errors. Their
operationIds and schemas are the contract's (e.g. `create_project_tower`, TowerInput → Tower).

WHY this module has no `from __future__ import annotations`: the factory's handlers are typed
with the collection's own models, held in closure variables. Python 3.14 evaluates such
annotations lazily *with* the closure, so FastAPI sees the real classes; as strings they could
not be resolved.
"""

import uuid
from dataclasses import dataclass
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Path, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.projects import children
from empire_api.projects.routes import CONFLICT, ProjectId, Reader, Writer, actor_of
from empire_api.projects.schemas_children import (
    Configuration,
    ConfigurationInput,
    ConstructionUpdate,
    ConstructionUpdateInput,
    LocationAdvantage,
    LocationAdvantageInput,
    PaymentPlan,
    PaymentPlanInput,
    Specification,
    SpecificationInput,
    Tower,
    TowerInput,
)
from empire_api.projects.schemas_shared import ReorderRequest
from empire_api.users.deps import staff

router = APIRouter(
    prefix="/api/v1/admin", tags=["Projects"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
ItemId = Annotated[uuid.UUID, Path()]


@dataclass(frozen=True)
class Collection:
    """How one child collection appears in the API."""

    kind: str  # children.KINDS key
    path: str  # URL segment: "location-advantages"
    one: str  # operationId part: "location_advantage"
    many: str  # operationId part: "location_advantages"
    label: str  # summaries: "location advantage"
    labels: str  # summaries: "location advantages"
    input_model: type[BaseModel]
    output_model: type[BaseModel]


COLLECTIONS = (
    Collection("tower", "towers", "tower", "towers", "tower", "towers", TowerInput, Tower),
    Collection(
        "configuration",
        "configurations",
        "configuration",
        "configurations",
        "configuration",
        "configurations",
        ConfigurationInput,
        Configuration,
    ),
    Collection(
        "specification",
        "specifications",
        "specification",
        "specifications",
        "specification",
        "specifications",
        SpecificationInput,
        Specification,
    ),
    Collection(
        "location_advantage",
        "location-advantages",
        "location_advantage",
        "location_advantages",
        "location advantage",
        "location advantages",
        LocationAdvantageInput,
        LocationAdvantage,
    ),
    Collection(
        "construction_update",
        "construction-updates",
        "construction_update",
        "construction_updates",
        "construction update",
        "construction updates",
        ConstructionUpdateInput,
        ConstructionUpdate,
    ),
    Collection(
        "payment_plan",
        "payment-plans",
        "payment_plan",
        "payment_plans",
        "payment plan",
        "payment plans",
        PaymentPlanInput,
        PaymentPlan,
    ),
)


def _register(spec: Collection) -> None:
    """Add list, create, update, delete and reorder routes for one collection."""
    kind = children.KINDS[spec.kind]
    InputModel = spec.input_model  # noqa: N806 — used as a type in the handlers below
    OutputModel = spec.output_model  # noqa: N806
    base = f"/projects/{{id}}/{spec.path}"
    write = staff("projects.write", write=True)

    @router.get(
        base,
        response_model=list[OutputModel],  # type: ignore[valid-type]
        operation_id=f"list_project_{spec.many}",
        name=f"list_project_{spec.many}",
        summary=f"List {spec.labels}",
        **staff("projects.read"),
    )
    def list_items(project_id: ProjectId, actor: Reader, db: Db) -> Any:
        return children.list_children(db, kind, project_id)

    @router.post(
        base,
        status_code=201,
        response_model=OutputModel,
        operation_id=f"create_project_{spec.one}",
        name=f"create_project_{spec.one}",
        summary=f"Add {spec.label}",
        responses=CONFLICT,
        **write,
    )
    def create_item(
        project_id: ProjectId,
        body: InputModel,  # type: ignore[valid-type]
        actor: Writer,
        request: Request,
        db: Db,
    ) -> Any:
        row = children.create_child(db, kind, project_id, body, actor_of(actor, request))
        db.refresh(row)
        return children.present_one(db, kind, row)

    @router.patch(
        f"{base}/{{item_id}}",
        response_model=OutputModel,
        operation_id=f"update_project_{spec.one}",
        name=f"update_project_{spec.one}",
        summary=f"Update {spec.label}",
        responses=CONFLICT,
        **write,
    )
    def update_item(
        project_id: ProjectId,
        item_id: ItemId,
        body: InputModel,  # type: ignore[valid-type]
        actor: Writer,
        request: Request,
        db: Db,
    ) -> Any:
        row = children.update_child(db, kind, project_id, item_id, body, actor_of(actor, request))
        db.refresh(row)
        return children.present_one(db, kind, row)

    @router.delete(
        f"{base}/{{item_id}}",
        status_code=204,
        operation_id=f"delete_project_{spec.one}",
        name=f"delete_project_{spec.one}",
        summary=f"Remove {spec.label}",
        responses=CONFLICT,
        **write,
    )
    def delete_item(
        project_id: ProjectId, item_id: ItemId, actor: Writer, request: Request, db: Db
    ) -> Response:
        children.delete_child(db, kind, project_id, item_id, actor_of(actor, request))
        return Response(status_code=204)

    @router.put(
        f"{base}/order",
        status_code=204,
        operation_id=f"reorder_project_{spec.many}",
        name=f"reorder_project_{spec.many}",
        summary=f"Reorder {spec.labels}",
        **write,
    )
    def reorder_items(
        project_id: ProjectId, body: ReorderRequest, actor: Writer, request: Request, db: Db
    ) -> Response:
        """Send every item's id once, in the new order."""
        children.reorder_children(db, kind, project_id, body.ids, actor_of(actor, request))
        return Response(status_code=204)


for _collection in COLLECTIONS:
    _register(_collection)
