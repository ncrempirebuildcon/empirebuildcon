"""Request and response shapes for the catalogue (design contract schemas City, CityInput,
Locality, LocalityInput, Amenity, AmenityInput, MapsResolveRequest, MapsResolveResult) and their
paged lists.

Slugs: cities and localities may set one; amenities always get one from the name. A slug is
kept when the name changes later, so links and seeds stay stable.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from pydantic import Field, StringConstraints

from empire_api.projects.fields import (
    BlankIsNone,
    IconKey,
    Line60,
    Line80,
    OutModel,
    Slug,
    StrictModel,
)
from empire_api.projects.maps import MAX_URL_LENGTH, PinKind
from empire_api.projects.vocab import AmenityCategory
from empire_api.users.schemas import PageMeta


class City(OutModel):
    id: uuid.UUID
    name: str
    slug: str
    state: str
    project_count: int = Field(description="Projects in this city (read-only)")


class CityInput(StrictModel):
    name: Line80
    slug: Annotated[Slug | None, BlankIsNone] = None
    state: Line60 = Field(examples=["Uttar Pradesh"])


class CityList(OutModel):
    items: list[City]
    meta: PageMeta


class Locality(OutModel):
    id: uuid.UUID
    city_id: uuid.UUID
    name: str
    slug: str
    project_count: int = Field(description="Projects in this locality (read-only)")


class LocalityInput(StrictModel):
    city_id: uuid.UUID
    name: Line80
    slug: Annotated[Slug | None, BlankIsNone] = None


class LocalityList(OutModel):
    items: list[Locality]
    meta: PageMeta


class Amenity(OutModel):
    id: uuid.UUID
    name: str
    slug: str
    icon: str = Field(description="Icon key from the design system")
    category: AmenityCategory


class AmenityInput(StrictModel):
    name: Line80
    icon: IconKey
    category: AmenityCategory


class AmenityList(OutModel):
    items: list[Amenity]
    meta: PageMeta


class MapsResolveRequest(StrictModel):
    # WHY 2,048 and not the contract's 500: full Google Maps place links often run 600+
    # characters (the data= part), and staff paste them straight from the address bar.
    input: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_URL_LENGTH)
    ] = Field(description="Google Maps link (long or maps.app.goo.gl), or a full plus code")


class MapsResolveResult(OutModel):
    lat: float
    lng: float
    source: PinKind = Field(
        description="url_coordinates and short_link → pin_source 'url'; plus_code → 'plus_code'"
    )
    resolved_url: str | None
    plus_code: str | None = Field(
        description=(
            "The full plus code alone, uppercase (any place name dropped), when source is "
            "plus_code; otherwise null. Save it as the project's location.plus_code."
        ),
        examples=["7JWV8XX8+XX"],
    )
