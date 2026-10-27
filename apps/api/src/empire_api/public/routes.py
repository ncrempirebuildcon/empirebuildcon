"""Public read-only endpoints: /api/v1/public/* (design contract tag "Public").

Provides all 13 read operations needed by the public website.
Responses are cached with Cache-Control and strong ETag, returning 304 when If-None-Match matches.
All endpoints enforce per-network rate limiting.
"""

from __future__ import annotations

from typing import Annotated, Any, Final

from fastapi import APIRouter, Depends, Path, Query, Request, Response
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import ApiProblem, problem_responses
from empire_api.pagination import PageParams, page_params
from empire_api.public import caching, schemas, service
from empire_api.users.deps import PUBLIC

router = APIRouter(
    prefix="/api/v1/public",
    tags=["Public"],
    responses=problem_responses(400, 404, 422, 429),
)
Db = Annotated[Session, Depends(get_db)]
Paging = Annotated[PageParams, Depends(page_params)]

RATE: Final = f"{caching.PUBLIC_RATE_LIMIT} per minute per network"


def _public(**extra: Any) -> dict[str, Any]:
    marker = dict(PUBLIC["openapi_extra"])
    return {"openapi_extra": {**marker, "x-rate-limit": RATE, **extra}}


@router.get(
    "/site",
    response_model=schemas.PublicSite,
    operation_id="public_site",
    summary="Company details, nav, public flags, consent texts, active offers",
    **_public(),
)
def public_site(
    request: Request,
    db: Db,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.get_public_site(db, locale=locale)
    return caching.cached_response(request, data)


@router.get(
    "/projects",
    response_model=schemas.PublicProjectList,
    operation_id="public_list_projects",
    summary="Search projects (available first, then sold out; off-market hidden)",
    **_public(),
)
def public_list_projects(
    request: Request,
    db: Db,
    paging: Paging,
    q: Annotated[str | None, Query(max_length=200)] = None,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
    status: Annotated[str | None, Query(pattern="^(upcoming|ongoing|completed)$")] = None,
    city: Annotated[str | None, Query(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)] = None,
    locality: Annotated[
        str | None, Query(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    ] = None,
    property_type: Annotated[str | None, Query(alias="type")] = None,
    bhk: Annotated[float | None, Query(ge=0)] = None,
    budget_min: Annotated[int | None, Query(ge=0, description="Whole rupees")] = None,
    budget_max: Annotated[int | None, Query(ge=0, description="Whole rupees")] = None,
    featured: Annotated[bool | None, Query()] = None,
    sort: Annotated[
        str | None, Query(pattern="^(recommended|price_asc|price_desc|possession|newest)$")
    ] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.list_public_projects(
        db,
        paging,
        status=status,
        city=city,
        locality=locality,
        property_type=property_type,
        bhk=bhk,
        budget_min=budget_min,
        budget_max=budget_max,
        featured=featured,
        sort=sort,
        q=q,
        locale=locale,
    )
    return caching.cached_response(request, data)


@router.get(
    "/projects/{slug}",
    response_model=schemas.PublicProjectDetail,
    operation_id="public_get_project",
    summary="Project detail",
    **_public(),
)
def public_get_project(
    slug: Annotated[str, Path(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)],
    request: Request,
    db: Db,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.get_public_project(db, slug=slug, locale=locale)
    if data is None:
        raise ApiProblem(404, f"Project '{slug}' was not found.")
    return caching.cached_response(request, data)


@router.get(
    "/projects/{slug}/configurations/{config_slug}",
    response_model=schemas.PublicPropertyDetail,
    operation_id="public_get_property",
    summary="Property (configuration) detail",
    **_public(),
)
def public_get_property(
    slug: Annotated[str, Path(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)],
    config_slug: Annotated[str, Path(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)],
    request: Request,
    db: Db,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.get_public_property(
        db, project_slug=slug, config_slug=config_slug, locale=locale
    )
    if data is None:
        raise ApiProblem(404, f"Configuration '{config_slug}' was not found.")
    return caching.cached_response(request, data)


@router.get(
    "/properties",
    response_model=schemas.PublicPropertyList,
    operation_id="public_list_properties",
    summary="Search properties (configurations) across projects",
    **_public(),
)
def public_list_properties(
    request: Request,
    db: Db,
    paging: Paging,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
    city: Annotated[str | None, Query(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)] = None,
    locality: Annotated[
        str | None, Query(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    ] = None,
    property_type: Annotated[str | None, Query(alias="type")] = None,
    bhk: Annotated[float | None, Query(ge=0)] = None,
    budget_min: Annotated[int | None, Query(ge=0, description="Whole rupees")] = None,
    budget_max: Annotated[int | None, Query(ge=0, description="Whole rupees")] = None,
    project_status: Annotated[str | None, Query(pattern="^(upcoming|ongoing|completed)$")] = None,
    sort: Annotated[
        str | None, Query(pattern="^(recommended|price_asc|price_desc|size_desc)$")
    ] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.list_public_properties(
        db,
        paging,
        city=city,
        locality=locality,
        property_type=property_type,
        bhk=bhk,
        budget_min=budget_min,
        budget_max=budget_max,
        project_status=project_status,
        sort=sort,
        locale=locale,
    )
    return caching.cached_response(request, data)


@router.get(
    "/cities",
    response_model=list[schemas.PublicCity],
    operation_id="public_list_cities",
    summary="Cities with published projects",
    **_public(),
)
def public_list_cities(
    request: Request,
    db: Db,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.list_public_cities(db)
    return caching.cached_response(request, data)


@router.get(
    "/pages/{slug}",
    response_model=schemas.PublicPage,
    operation_id="public_get_page",
    summary="Published page with blocks (incl. legal and landing pages)",
    **_public(),
)
def public_get_page(
    slug: Annotated[str, Path()],
    request: Request,
    db: Db,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.get_public_page(db, slug=slug, locale=locale)
    if data is None:
        raise ApiProblem(404, f"Page '{slug}' was not found.")
    return caching.cached_response(request, data)


@router.get(
    "/posts",
    response_model=schemas.PublicPostList,
    operation_id="public_list_posts",
    summary="Blog and news",
    **_public(),
)
def public_list_posts(
    request: Request,
    db: Db,
    paging: Paging,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
    category: Annotated[str | None, Query()] = None,
    tag: Annotated[str | None, Query()] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.list_public_posts(db, paging, category=category, tag=tag, locale=locale)
    return caching.cached_response(request, data)


@router.get(
    "/posts/{slug}",
    response_model=schemas.PublicPost,
    operation_id="public_get_post",
    summary="Article",
    **_public(),
)
def public_get_post(
    slug: Annotated[str, Path(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)],
    request: Request,
    db: Db,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.get_public_post(db, slug=slug, locale=locale)
    if data is None:
        raise ApiProblem(404, f"Post '{slug}' was not found.")
    return caching.cached_response(request, data)


@router.get(
    "/faqs",
    response_model=list[schemas.PublicFaq],
    operation_id="public_list_faqs",
    summary="FAQs (site-wide, or for one project)",
    **_public(),
)
def public_list_faqs(
    request: Request,
    db: Db,
    project: Annotated[
        str | None, Query(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    ] = None,
    locale: Annotated[str | None, Query(pattern="^[a-z]{2}$")] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.list_public_faqs(db, project_slug=project, locale=locale)
    return caching.cached_response(request, data)


@router.get(
    "/testimonials",
    response_model=list[schemas.PublicTestimonial],
    operation_id="public_list_testimonials",
    summary="Published, sourced testimonials",
    **_public(),
)
def public_list_testimonials(
    request: Request,
    db: Db,
    project: Annotated[
        str | None, Query(pattern="^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    ] = None,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.list_public_testimonials(db, project_slug=project)
    return caching.cached_response(request, data)


@router.get(
    "/redirects",
    response_model=list[schemas.PublicRedirect],
    operation_id="public_list_redirects",
    summary="Active redirects (read by the web app, cached)",
    **_public(),
)
def public_list_redirects(
    request: Request,
    db: Db,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.list_public_redirects(db)
    return caching.cached_response(request, data)


@router.get(
    "/sitemap",
    response_model=list[schemas.PublicSitemapEntry],
    operation_id="public_sitemap",
    summary="All public URLs with last-modified (web app builds sitemap.xml)",
    **_public(),
)
def public_sitemap(
    request: Request,
    db: Db,
) -> Response:
    caching.check_public_rate_limit(request)
    data = service.get_public_sitemap(db)
    return caching.cached_response(request, data)
