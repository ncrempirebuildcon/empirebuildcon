"""Business rules for the catalogue: cities, localities and amenities.

Collaborators: common.py (audit, slugs, conflicts), routes_catalogue.py.
Implements: ARCHITECTURE §11 (`projects.write` edits cities and amenities; audit on change).

Rules:
  - Slugs are made from the name when not given, and kept when the name changes later.
  - Nothing in use can be deleted: a 409 says how many projects use it ("used by 3 projects"),
    which the CMS shows as is. A city's unused localities go with it.
  - A locality used by projects can't move to another city (it would break the
    city/locality INVARIANT in models.py).

TODO(phase-5): emit an event when a city or amenity used by published projects is renamed,
so the public pages that show it revalidate.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.pagination import PageParams
from empire_api.projects.common import (
    Actor,
    Conflicts,
    FieldError,
    commit,
    conflict,
    flush,
    invalid,
    record,
    slug_or_error,
    slugify,
    snapshot,
)
from empire_api.projects.models import Amenity, City, Locality, Project, ProjectAmenity
from empire_api.projects.schemas_catalogue import AmenityInput, CityInput, LocalityInput

CITY_SLUG_TAKEN: Final = "Another city already uses this web address. Choose another."
LOCALITY_SLUG_TAKEN: Final = (
    "Another locality in this city already uses this web address. Choose another."
)
AMENITY_TAKEN: Final = "An amenity with this name already exists."
_CITY_CONFLICTS: Final = {"uq_city_slug": ("slug", CITY_SLUG_TAKEN)}
_AMENITY_CONFLICTS: Final = {"uq_amenity_slug": ("name", AMENITY_TAKEN)}


def used_by(count: int) -> str:
    return f"used by {count} project{'' if count == 1 else 's'}"


def _count_projects(db: Session, *where: Any) -> int:
    return int(db.scalar(select(func.count()).select_from(Project).where(*where)) or 0)


def _page(db: Session, stmt: Any, paging: PageParams) -> tuple[list[Any], int]:
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(stmt.offset(paging.offset).limit(paging.per_page)).all()
    return list(rows), total


def _changed(
    db: Session,
    actor: Actor,
    entity: str,
    row: Any,
    before: dict[str, Any],
    conflicts: Conflicts | None = None,
) -> None:
    flush(db, conflicts)
    after = snapshot(row)
    if after != before:
        record(
            db,
            actor,
            action=f"{entity}.updated",
            entity_type=entity,
            entity_id=row.id,
            before=before,
            after=after,
        )


# --- Cities ----------------------------------------------------------------------------------


def list_cities(db: Session, paging: PageParams) -> tuple[list[tuple[City, int]], int]:
    """Cities A–Z with how many projects each has."""
    counts = select(Project.city_id, func.count().label("n")).group_by(Project.city_id).subquery()
    stmt = (
        select(City, func.coalesce(counts.c.n, 0))
        .outerjoin(counts, counts.c.city_id == City.id)
        .order_by(City.name, City.id)
    )
    rows, total = _page(db, stmt, paging)
    return [(row[0], int(row[1])) for row in rows], total


def get_city(db: Session, city_id: uuid.UUID) -> City:
    city = db.get(City, city_id)
    if city is None:
        raise ApiProblem(404, "No city with this id.")
    return city


def city_project_count(db: Session, city_id: uuid.UUID) -> int:
    return _count_projects(db, Project.city_id == city_id)


def _city_slug_free(db: Session, slug: str, exclude: uuid.UUID | None = None) -> None:
    stmt = select(City.id).where(City.slug == slug)
    if exclude is not None:
        stmt = stmt.where(City.id != exclude)
    if db.scalar(stmt) is not None:
        raise conflict(CITY_SLUG_TAKEN, "slug", CITY_SLUG_TAKEN)


def create_city(db: Session, body: CityInput, actor: Actor) -> City:
    slug = slug_or_error(body.slug, body.name)
    _city_slug_free(db, slug)
    city = City(name=body.name, slug=slug, state=body.state)
    db.add(city)
    flush(db, _CITY_CONFLICTS)
    record(
        db,
        actor,
        action="city.created",
        entity_type="city",
        entity_id=city.id,
        before={},
        after=snapshot(city),
    )
    commit(db, _CITY_CONFLICTS)
    return city


def update_city(db: Session, city_id: uuid.UUID, body: CityInput, actor: Actor) -> City:
    city = get_city(db, city_id)
    before = snapshot(city)
    city.name, city.state = body.name, body.state
    if body.slug and body.slug != city.slug:
        _city_slug_free(db, body.slug, city.id)
        city.slug = body.slug
    _changed(db, actor, "city", city, before, _CITY_CONFLICTS)
    commit(db, _CITY_CONFLICTS)
    return city


def delete_city(db: Session, city_id: uuid.UUID, actor: Actor) -> None:
    city = get_city(db, city_id)
    count = city_project_count(db, city.id)
    if count:
        raise conflict(f"This city is {used_by(count)}. Move them to another city first.")
    localities = db.scalar(select(func.count()).where(Locality.city_id == city.id))
    record(
        db,
        actor,
        action="city.deleted",
        entity_type="city",
        entity_id=city.id,
        before={**snapshot(city), "localities_removed": localities},
    )
    db.delete(city)
    commit(db)


# --- Localities ------------------------------------------------------------------------------


def list_localities(
    db: Session, paging: PageParams, city_id: uuid.UUID | None
) -> tuple[list[tuple[Locality, int]], int]:
    """Localities A–Z (optionally of one city) with how many projects each has."""
    counts = (
        select(Project.locality_id, func.count().label("n"))
        .where(Project.locality_id.is_not(None))
        .group_by(Project.locality_id)
        .subquery()
    )
    stmt = select(Locality, func.coalesce(counts.c.n, 0)).outerjoin(
        counts, counts.c.locality_id == Locality.id
    )
    if city_id is not None:
        stmt = stmt.where(Locality.city_id == city_id)
    rows, total = _page(db, stmt.order_by(Locality.name, Locality.id), paging)
    return [(row[0], int(row[1])) for row in rows], total


def get_locality(db: Session, locality_id: uuid.UUID) -> Locality:
    locality = db.get(Locality, locality_id)
    if locality is None:
        raise ApiProblem(404, "No locality with this id.")
    return locality


def locality_project_count(db: Session, locality_id: uuid.UUID) -> int:
    return _count_projects(db, Project.locality_id == locality_id)


def _locality_slug_free(
    db: Session, city_id: uuid.UUID, slug: str, exclude: uuid.UUID | None = None
) -> None:
    stmt = select(Locality.id).where(Locality.city_id == city_id, Locality.slug == slug)
    if exclude is not None:
        stmt = stmt.where(Locality.id != exclude)
    if db.scalar(stmt) is not None:
        raise conflict(LOCALITY_SLUG_TAKEN, "slug", LOCALITY_SLUG_TAKEN)


_LOCALITY_CONFLICTS: Final = {"uq_locality_city_id_slug": ("slug", LOCALITY_SLUG_TAKEN)}


def _city_must_exist(db: Session, city_id: uuid.UUID) -> None:
    if db.get(City, city_id) is None:
        raise invalid([FieldError("city_id", "No city with this id.")])


def create_locality(db: Session, body: LocalityInput, actor: Actor) -> Locality:
    _city_must_exist(db, body.city_id)
    slug = slug_or_error(body.slug, body.name)
    _locality_slug_free(db, body.city_id, slug)
    locality = Locality(city_id=body.city_id, name=body.name, slug=slug)
    db.add(locality)
    flush(db, _LOCALITY_CONFLICTS)
    record(
        db,
        actor,
        action="locality.created",
        entity_type="locality",
        entity_id=locality.id,
        before={},
        after=snapshot(locality),
    )
    commit(db, _LOCALITY_CONFLICTS)
    return locality


def update_locality(
    db: Session, locality_id: uuid.UUID, body: LocalityInput, actor: Actor
) -> Locality:
    locality = get_locality(db, locality_id)
    before = snapshot(locality)
    if body.city_id != locality.city_id:
        _city_must_exist(db, body.city_id)
        count = locality_project_count(db, locality.id)
        if count:
            raise conflict(f"This locality is {used_by(count)}, so it can't move to another city.")
    slug = body.slug or locality.slug
    if (body.city_id, slug) != (locality.city_id, locality.slug):
        _locality_slug_free(db, body.city_id, slug, locality.id)
    locality.city_id, locality.name, locality.slug = body.city_id, body.name, slug
    _changed(db, actor, "locality", locality, before, _LOCALITY_CONFLICTS)
    commit(db, _LOCALITY_CONFLICTS)
    return locality


def delete_locality(db: Session, locality_id: uuid.UUID, actor: Actor) -> None:
    locality = get_locality(db, locality_id)
    count = locality_project_count(db, locality.id)
    if count:
        raise conflict(f"This locality is {used_by(count)}. Change their locality first.")
    record(
        db,
        actor,
        action="locality.deleted",
        entity_type="locality",
        entity_id=locality.id,
        before=snapshot(locality),
    )
    db.delete(locality)
    commit(db)


# --- Amenities -------------------------------------------------------------------------------


def list_amenities(db: Session, paging: PageParams) -> tuple[list[Amenity], int]:
    rows, total = _page(db, select(Amenity).order_by(Amenity.name, Amenity.id), paging)
    return [row[0] for row in rows], total


def get_amenity(db: Session, amenity_id: uuid.UUID) -> Amenity:
    amenity = db.get(Amenity, amenity_id)
    if amenity is None:
        raise ApiProblem(404, "No amenity with this id.")
    return amenity


def _amenity_name_free(db: Session, name: str, exclude: uuid.UUID | None = None) -> None:
    """Two amenities can't share a name (ignoring case) or the slug that name would make."""
    stmt = select(Amenity.id).where(
        or_(Amenity.slug == slugify(name), func.lower(Amenity.name) == name.lower())
    )
    if exclude is not None:
        stmt = stmt.where(Amenity.id != exclude)
    if db.scalar(stmt) is not None:
        raise conflict(AMENITY_TAKEN, "name", AMENITY_TAKEN)


def create_amenity(db: Session, body: AmenityInput, actor: Actor) -> Amenity:
    """The slug always comes from the name (AmenityInput has none in the contract)."""
    slug = slug_or_error(None, body.name, field="name")
    _amenity_name_free(db, body.name)
    amenity = Amenity(name=body.name, slug=slug, icon=body.icon, category=body.category)
    db.add(amenity)
    flush(db, _AMENITY_CONFLICTS)
    record(
        db,
        actor,
        action="amenity.created",
        entity_type="amenity",
        entity_id=amenity.id,
        before={},
        after=snapshot(amenity),
    )
    commit(db, _AMENITY_CONFLICTS)
    return amenity


def update_amenity(db: Session, amenity_id: uuid.UUID, body: AmenityInput, actor: Actor) -> Amenity:
    amenity = get_amenity(db, amenity_id)
    before = snapshot(amenity)
    if body.name.lower() != amenity.name.lower():
        _amenity_name_free(db, body.name, amenity.id)
    amenity.name, amenity.icon, amenity.category = body.name, body.icon, body.category
    _changed(db, actor, "amenity", amenity, before, _AMENITY_CONFLICTS)
    commit(db)
    return amenity


def delete_amenity(db: Session, amenity_id: uuid.UUID, actor: Actor) -> None:
    amenity = get_amenity(db, amenity_id)
    count = int(
        db.scalar(
            select(func.count())
            .select_from(ProjectAmenity)
            .where(ProjectAmenity.amenity_id == amenity.id)
        )
        or 0
    )
    if count:
        raise conflict(f"This amenity is {used_by(count)}. Remove it from them first.")
    record(
        db,
        actor,
        action="amenity.deleted",
        entity_type="amenity",
        entity_id=amenity.id,
        before=snapshot(amenity),
    )
    db.delete(amenity)
    commit(db)
