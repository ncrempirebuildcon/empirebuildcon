"""Request and response shapes for a project's ordered children (design contract schemas
Tower, TowerInput, Configuration, ConfigurationInput, Specification, SpecificationInput,
LocationAdvantage, LocationAdvantageInput, ConstructionUpdate, ConstructionUpdateInput,
PaymentPlanStage, PaymentPlan, PaymentPlanInput) and the amenities body of
`PUT /admin/projects/{id}/amenities`.

PATCH on a child takes its *Input shape (as in the contract): the required fields are always
sent, and optional fields that are left out keep their stored value. `sort_order` left out on
create puts the item at the end.

Additions to the contract: `sort_order` on ConstructionUpdate/PaymentPlan (both have a reorder
endpoint), and media placeholders (`floor_plans`, `photos`) that part 2 fills.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Annotated, Final

from pydantic import AfterValidator, Field, field_validator
from pydantic_core import PydanticCustomError

from empire_api.media.schemas import LinkedMedia
from empire_api.projects.fields import (
    BlankIsNone,
    Count,
    IdList,
    Line60,
    Line80,
    Line120,
    OutModel,
    Slug,
    SortOrder,
    StrictModel,
    Text500,
    Text2000,
    Text5000,
    no_duplicates,
)
from empire_api.projects.schemas_shared import (
    Area,
    Price,
    Translations,
    check_translation_fields,
)
from empire_api.projects.vocab import (
    AdvantageKind,
    PropertyType,
    PublishState,
    SalesStatus,
    TowerKind,
    TowerStatus,
)

CONFIGURATION_TRANSLATABLE: Final = frozenset({"name"})
MAX_STAGES: Final = 30
Percent = Annotated[int, Field(ge=0, le=100)]


# --- Towers / phases ---------------------------------------------------------------------------


class Tower(OutModel):
    id: uuid.UUID
    name: str
    kind: TowerKind
    floors: int | None
    units_count: int | None
    status: TowerStatus
    rera_number: str | None = Field(description="Only if this phase has its own registration")
    possession_date: date | None
    progress_percent: Percent | None = Field(
        description="From the latest published construction update for this tower (read-only)."
    )
    sort_order: int


class TowerInput(StrictModel):
    name: Line60
    kind: TowerKind
    floors: Annotated[int, Field(ge=0, le=300)] | None = None
    units_count: Count | None = None
    status: TowerStatus = "planned"
    rera_number: Annotated[Line60 | None, BlankIsNone] = None
    possession_date: date | None = None
    sort_order: SortOrder | None = None


# --- Configurations ----------------------------------------------------------------------------


def _half_steps(value: float | None) -> float | None:
    if value is not None and value * 2 != int(value * 2):
        raise PydanticCustomError("bhk", "Use whole or half numbers, like 2 or 2.5.")
    return value


class Configuration(OutModel):
    """A floor-plan type; a "property" on the public site (D-004)."""

    id: uuid.UUID
    slug: str
    name: str = Field(examples=["2 BHK Premium"])
    tower_id: uuid.UUID | None
    property_type: PropertyType
    bhk: float | None
    bathrooms: int | None
    balconies: int | None
    area: Area
    price: Price
    sales_status: SalesStatus
    # TODO(phase-4): part 2 fills floor plans from media links (role floor_plan).
    floor_plans: list[LinkedMedia]
    sort_order: int
    is_sample: bool = Field(description="Sample data — never shown in production")
    translations: Translations


class ConfigurationInput(StrictModel):
    name: Line80
    slug: Annotated[Slug | None, BlankIsNone] = None
    tower_id: uuid.UUID | None = None
    property_type: PropertyType
    bhk: Annotated[Annotated[float, Field(ge=0, le=20)] | None, AfterValidator(_half_steps)] = None
    bathrooms: Annotated[int, Field(ge=0, le=20)] | None = None
    balconies: Annotated[int, Field(ge=0, le=20)] | None = None
    area: Area = Field(default_factory=Area)
    price: Price = Field(default_factory=Price)
    sales_status: SalesStatus = "available"
    sort_order: SortOrder | None = None
    translations: Translations = Field(default_factory=Translations)

    @field_validator("translations")
    @classmethod
    def _translatable(cls, value: Translations) -> Translations:
        return check_translation_fields(value, CONFIGURATION_TRANSLATABLE)


# --- Specifications and location advantages -------------------------------------------------


class Specification(OutModel):
    id: uuid.UUID
    category: str = Field(examples=["Flooring"])
    text: str
    sort_order: int


class SpecificationInput(StrictModel):
    category: Line60
    text: Text500
    sort_order: SortOrder | None = None


class LocationAdvantage(OutModel):
    """Distances are approximate and shown as such (≈) on the site."""

    id: uuid.UUID
    label: str = Field(examples=["Metro station"])
    kind: AdvantageKind
    distance_km: float | None
    travel_minutes: int | None
    sort_order: int


class LocationAdvantageInput(StrictModel):
    label: Line80
    kind: AdvantageKind
    distance_km: Annotated[float, Field(ge=0, le=1000)] | None = None
    travel_minutes: Annotated[int, Field(ge=0, le=1440)] | None = None
    sort_order: SortOrder | None = None


# --- Construction updates --------------------------------------------------------------------


class ConstructionUpdate(OutModel):
    id: uuid.UUID
    tower_id: uuid.UUID | None
    title: str
    update_date: date
    progress_percent: Percent | None
    body: str | None = Field(description="WhatsApp-style formatted text")
    # TODO(phase-4): part 2 fills progress photos from media links.
    photos: list[LinkedMedia]
    publish_state: PublishState
    sort_order: int


class ConstructionUpdateInput(StrictModel):
    tower_id: uuid.UUID | None = None
    title: Line120
    update_date: date
    progress_percent: Percent | None = None
    body: Annotated[Text5000 | None, BlankIsNone] = None
    publish_state: PublishState = "draft"
    sort_order: SortOrder | None = None


# --- Payment plans ---------------------------------------------------------------------------


def _two_decimals(value: float) -> float:
    if round(value, 2) != value:
        raise PydanticCustomError("percent", "Use at most two decimals, like 12.5.")
    return value


class PaymentPlanStage(StrictModel):
    label: Line80 = Field(examples=["On booking"])
    percent: Annotated[float, Field(ge=0, le=100), AfterValidator(_two_decimals)]
    sort_order: SortOrder | None = None


def _total_is_100(stages: list[PaymentPlanStage]) -> list[PaymentPlanStage]:
    """INVARIANT: a payment plan's stages add up to exactly 100% (contract PaymentPlan).

    WHY Decimal: 33.33 + 33.33 + 33.34 is not exactly 100 in binary floating point.
    """
    total = sum((Decimal(str(stage.percent)) for stage in stages), Decimal(0))
    if total != Decimal(100):
        raise PydanticCustomError(
            "stages_total",
            "The stages add up to {total}%. They must total exactly 100%.",
            {"total": format(total.normalize(), "f")},
        )
    return stages


class PaymentPlan(OutModel):
    """Stage percentages total 100. No "assured return" fields exist, by design."""

    id: uuid.UUID
    name: str = Field(examples=["Construction-linked plan"])
    description: str | None = Field(description="WhatsApp-style formatted text")
    stages: list[PaymentPlanStage]
    is_visible: bool
    sort_order: int


class PaymentPlanInput(StrictModel):
    name: Line80
    description: Annotated[Text2000 | None, BlankIsNone] = None
    stages: Annotated[
        list[PaymentPlanStage],
        Field(min_length=1, max_length=MAX_STAGES),
        AfterValidator(_total_is_100),
    ]
    is_visible: bool = True
    sort_order: SortOrder | None = None


# --- Amenities of a project ------------------------------------------------------------------


class ProjectAmenitiesInput(StrictModel):
    """`PUT /admin/projects/{id}/amenities`: the full ordered list (empty clears it)."""

    amenity_ids: Annotated[IdList, AfterValidator(no_duplicates), Field(max_length=200)]
