"""Catalogue endpoints (design contract tag "Catalogue"): /api/v1/admin/amenities, /cities,
/localities and /maps/resolve.

Permissions (ARCHITECTURE §11): reading needs `projects.read`; every change, and the maps
resolver, needs `projects.write`. A delete of something in use answers 409 "used by N projects".
"""

from __future__ import annotations

import uuid
from typing import Annotated, Final

import httpx
from fastapi import APIRouter, Depends, Path, Request, Response
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.pagination import PageParams, page_params
from empire_api.platform import rate_limit
from empire_api.projects import catalogue, maps, present
from empire_api.projects.routes import CONFLICT, Reader, Writer, actor_of
from empire_api.projects.schemas_catalogue import (
    Amenity,
    AmenityInput,
    AmenityList,
    City,
    CityInput,
    CityList,
    Locality,
    LocalityInput,
    LocalityList,
    MapsResolveRequest,
    MapsResolveResult,
)
from empire_api.users.deps import staff
from empire_api.users.schemas import PageMeta

router = APIRouter(
    prefix="/api/v1/admin", tags=["Catalogue"], responses=problem_responses(401, 403, 404, 422)
)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]
# The contract names the path parameter `id`; `item_id` in Python avoids shadowing id().
ItemId = Annotated[uuid.UUID, Path(alias="id")]

# SECURITY: the resolver can make the API call Google (maps.py); cap it per staff member.
MAPS_LIMIT: Final = 30
MAPS_WINDOW_SECONDS: Final = 600


# --- Amenities -------------------------------------------------------------------------------


@router.get(
    "/amenities",
    response_model=AmenityList,
    operation_id="list_amenities",
    **staff("projects.read"),
)
def list_amenities(actor: Reader, db: Db, paging: Paging) -> AmenityList:
    """The amenity catalogue, A–Z."""
    rows, total = catalogue.list_amenities(db, paging)
    return AmenityList(
        items=[present.amenity_out(r) for r in rows], meta=PageMeta(**paging.meta(total))
    )


@router.post(
    "/amenities",
    status_code=201,
    response_model=Amenity,
    operation_id="create_amenity",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def create_amenity(body: AmenityInput, actor: Writer, request: Request, db: Db) -> Amenity:
    return present.amenity_out(catalogue.create_amenity(db, body, actor_of(actor, request)))


@router.patch(
    "/amenities/{id}",
    response_model=Amenity,
    operation_id="update_amenity",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def update_amenity(
    item_id: ItemId, body: AmenityInput, actor: Writer, request: Request, db: Db
) -> Amenity:
    row = catalogue.update_amenity(db, item_id, body, actor_of(actor, request))
    return present.amenity_out(row)


@router.delete(
    "/amenities/{id}",
    status_code=204,
    operation_id="delete_amenity",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def delete_amenity(item_id: ItemId, actor: Writer, request: Request, db: Db) -> Response:
    catalogue.delete_amenity(db, item_id, actor_of(actor, request))
    return Response(status_code=204)


# --- Cities ----------------------------------------------------------------------------------


@router.get(
    "/cities", response_model=CityList, operation_id="list_cities", **staff("projects.read")
)
def list_cities(actor: Reader, db: Db, paging: Paging) -> CityList:
    """Cities A–Z with their project counts."""
    rows, total = catalogue.list_cities(db, paging)
    return CityList(
        items=[present.city_out(city, count) for city, count in rows],
        meta=PageMeta(**paging.meta(total)),
    )


@router.post(
    "/cities",
    status_code=201,
    response_model=City,
    operation_id="create_city",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def create_city(body: CityInput, actor: Writer, request: Request, db: Db) -> City:
    return present.city_out(catalogue.create_city(db, body, actor_of(actor, request)), 0)


@router.patch(
    "/cities/{id}",
    response_model=City,
    operation_id="update_city",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def update_city(item_id: ItemId, body: CityInput, actor: Writer, request: Request, db: Db) -> City:
    city = catalogue.update_city(db, item_id, body, actor_of(actor, request))
    return present.city_out(city, catalogue.city_project_count(db, city.id))


@router.delete(
    "/cities/{id}",
    status_code=204,
    operation_id="delete_city",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def delete_city(item_id: ItemId, actor: Writer, request: Request, db: Db) -> Response:
    """Refused (409) while projects use the city; its unused localities go with it."""
    catalogue.delete_city(db, item_id, actor_of(actor, request))
    return Response(status_code=204)


# --- Localities ------------------------------------------------------------------------------


@router.get(
    "/localities",
    response_model=LocalityList,
    operation_id="list_localities",
    **staff("projects.read"),
)
def list_localities(
    actor: Reader, db: Db, paging: Paging, city_id: uuid.UUID | None = None
) -> LocalityList:
    """Localities A–Z, optionally of one city, with their project counts."""
    rows, total = catalogue.list_localities(db, paging, city_id)
    return LocalityList(
        items=[present.locality_out(row, count) for row, count in rows],
        meta=PageMeta(**paging.meta(total)),
    )


@router.post(
    "/localities",
    status_code=201,
    response_model=Locality,
    operation_id="create_locality",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def create_locality(body: LocalityInput, actor: Writer, request: Request, db: Db) -> Locality:
    return present.locality_out(catalogue.create_locality(db, body, actor_of(actor, request)), 0)


@router.patch(
    "/localities/{id}",
    response_model=Locality,
    operation_id="update_locality",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def update_locality(
    item_id: ItemId, body: LocalityInput, actor: Writer, request: Request, db: Db
) -> Locality:
    row = catalogue.update_locality(db, item_id, body, actor_of(actor, request))
    return present.locality_out(row, catalogue.locality_project_count(db, row.id))


@router.delete(
    "/localities/{id}",
    status_code=204,
    operation_id="delete_locality",
    responses=CONFLICT,
    **staff("projects.write", write=True),
)
def delete_locality(item_id: ItemId, actor: Writer, request: Request, db: Db) -> Response:
    catalogue.delete_locality(db, item_id, actor_of(actor, request))
    return Response(status_code=204)


# --- Maps ------------------------------------------------------------------------------------


@router.post(
    "/maps/resolve",
    response_model=MapsResolveResult,
    operation_id="resolve_map_pin",
    summary="Get a pin from a Google Maps link, short link or plus code",
    description=(
        "Short links are followed on the server only, hop by hop, to an allowlist of Google "
        "Maps hosts over https: at most 5 redirects, 5 s in total, headers only. Anything "
        "else answers 422 with a reason staff can act on."
    ),
    responses=problem_responses(429),
    **staff("projects.write", write=True),
)
def resolve_map_pin(body: MapsResolveRequest, actor: Writer) -> MapsResolveResult:
    rate_limit.enforce(
        f"maps:user:{actor.user.id}",
        limit=MAPS_LIMIT,
        window_seconds=MAPS_WINDOW_SECONDS,
        message="Too many map lookups. Try again in a few minutes.",
    )
    try:
        pin = maps.resolve(body.input, client_factory=resolver_client)
    except maps.MapsInputError as exc:
        raise ApiProblem(422, str(exc), errors=[{"field": "input", "message": str(exc)}]) from exc
    return MapsResolveResult(
        lat=pin.lat,
        lng=pin.lng,
        source=pin.source,
        resolved_url=pin.resolved_url,
        plus_code=pin.plus_code,
    )


def resolver_client() -> httpx.Client:
    """The HTTP client the resolver uses. Tests replace this to stay off the network."""
    return maps.default_client()
