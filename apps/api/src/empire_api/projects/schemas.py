"""Request and response shapes for projects (design contract schemas ProjectSummary,
ProjectDetail, ProjectAdmin, ProjectInput).

Additions to the contract, each needed by the CMS (recorded in the Phase 4 report):
  - `ProjectUpdate`: the PATCH body. Everything is optional, and `publish_state` may be set to
    "archived" (or back to "draft"); the contract's ProjectInput requires name and status and
    has no publish_state, so it can't express "archive this" or "change only the price".
  - `ProjectAdminSummary`: list rows also carry publish_state, published_at and updated_at
    for the CMS list's columns.
  - `rera_account` (RERA designated account) and `featured_order` on ProjectAdmin.

Media-backed fields (`cover`, `gallery`, `videos`, `documents`, `brochure`, `rera.qr`) stay
empty until part 2, and `faqs` until part 4. TODO(phase-4) markers in present.py say where.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from empire_api.media.schemas import LinkedMedia, Media
from empire_api.projects.fields import (
    BlankIsNone,
    Count,
    Line40,
    Line60,
    Line120,
    Line160,
    OutModel,
    Slug,
    StrictModel,
    Text20000,
    WebUrl,
)
from empire_api.projects.schemas_catalogue import Amenity
from empire_api.projects.schemas_children import (
    Configuration,
    ConstructionUpdate,
    LocationAdvantage,
    PaymentPlan,
    Specification,
    Tower,
)
from empire_api.projects.schemas_shared import (
    Area,
    CityRef,
    LocalityRef,
    Location,
    LocationInput,
    Price,
    Rera,
    ReraAccount,
    Seo,
    Translations,
    check_translation_fields,
)
from empire_api.projects.vocab import (
    DEFAULT_RERA_AUTHORITY,
    ProjectStatus,
    ProjectType,
    PropertyType,
    PublishState,
    SalesStatus,
)
from empire_api.users.schemas import PageMeta

PROJECT_TRANSLATABLE: Final = frozenset({"name", "tagline", "description"})
FeaturedOrder = Annotated[int, Field(ge=0, le=10_000)]


class Faq(OutModel):
    """Contract shape, for `faqs` on a project. TODO(phase-4): part 4 (content module) owns
    FAQs; move this class there keeping its name."""

    id: uuid.UUID
    project_id: uuid.UUID | None
    question: str
    answer: str = Field(description="WhatsApp-style formatted text")
    sort_order: int
    is_visible: bool
    translations: Translations


class ProjectSummary(OutModel):
    id: uuid.UUID
    slug: str
    name: str
    status: ProjectStatus
    sales_status: SalesStatus
    city: CityRef | None
    locality: LocalityRef | None
    price: Price
    configuration_labels: list[str] = Field(examples=[["2 BHK", "3 BHK"]])
    property_types: list[PropertyType]
    cover: Media | None
    rera: Rera
    possession_date: date | None
    is_featured: bool
    is_sample: bool = Field(description="Sample data — never shown in production")


class ProjectAdminSummary(ProjectSummary):
    """A row of the CMS projects list."""

    publish_state: PublishState
    published_at: datetime | None
    updated_at: datetime


class ProjectList(OutModel):
    items: list[ProjectAdminSummary]
    meta: PageMeta


class ProjectDetail(ProjectSummary):
    tagline: str | None
    description: str | None = Field(description="WhatsApp-style formatted text")
    project_type: ProjectType
    land_area: Area | None
    total_units: int | None
    launch_date: date | None
    location: Location
    towers: list[Tower]
    configurations: list[Configuration]
    amenities: list[Amenity]
    specifications: list[Specification]
    location_advantages: list[LocationAdvantage]
    construction_updates: list[ConstructionUpdate]
    payment_plans: list[PaymentPlan]
    gallery: list[LinkedMedia]
    videos: list[LinkedMedia]
    documents: list[LinkedMedia]
    brochure: LinkedMedia | None
    brochure_gated: bool
    faqs: list[Faq]
    seo: Seo
    translations: Translations
    updated_at: datetime


class ProjectAdmin(ProjectDetail):
    publish_state: PublishState
    published_at: datetime | None = Field(
        description="When it was last published; kept after unpublishing (null = never published)"
    )
    created_at: datetime
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    publish_blockers: list[str] = Field(
        description="Why Publish is locked, e.g. 'RERA registration number missing' (read-only)"
    )
    rera_account: ReraAccount | None
    featured_order: int | None


class ProjectInput(StrictModel):
    """Create a project. It always starts as a draft."""

    name: Line120
    slug: Annotated[Slug | None, BlankIsNone] = Field(
        default=None, description="Made from the name when left out"
    )
    tagline: Annotated[Line160 | None, BlankIsNone] = None
    description: Annotated[Text20000 | None, BlankIsNone] = None
    status: ProjectStatus
    sales_status: SalesStatus = "available"
    project_type: ProjectType = "residential"
    rera_authority: Line40 = DEFAULT_RERA_AUTHORITY
    rera_number: Annotated[Line60 | None, BlankIsNone] = None
    rera_url: Annotated[WebUrl | None, BlankIsNone] = None
    rera_account: ReraAccount | None = None
    possession_date: date | None = None
    launch_date: date | None = None
    price: Price = Field(default_factory=Price)
    land_area: Area | None = None
    total_units: Count | None = None
    location: LocationInput = Field(default_factory=LocationInput)
    is_featured: bool = False
    featured_order: FeaturedOrder | None = None
    brochure_gated: bool = False
    seo: Seo = Field(default_factory=Seo)
    translations: Translations = Field(default_factory=Translations)

    @field_validator("translations")
    @classmethod
    def _translatable(cls, value: Translations) -> Translations:
        return check_translation_fields(value, PROJECT_TRANSLATABLE)


# Fields a PATCH may not set to null (their columns are NOT NULL).
_NOT_NULL: Final = (
    "name",
    "slug",
    "status",
    "sales_status",
    "project_type",
    "rera_authority",
    "price",
    "location",
    "is_featured",
    "brochure_gated",
    "seo",
    "translations",
    "publish_state",
)


class ProjectUpdate(StrictModel):
    """PATCH a project: send only what changes. `publish_state` archives ("archived") or
    restores ("draft"); publishing goes through `POST …/publish`, which checks the blockers."""

    name: Line120 | None = None
    slug: Annotated[Slug | None, BlankIsNone] = None
    tagline: Annotated[Line160 | None, BlankIsNone] = None
    description: Annotated[Text20000 | None, BlankIsNone] = None
    status: ProjectStatus | None = None
    sales_status: SalesStatus | None = None
    project_type: ProjectType | None = None
    rera_authority: Line40 | None = None
    rera_number: Annotated[Line60 | None, BlankIsNone] = None
    rera_url: Annotated[WebUrl | None, BlankIsNone] = None
    rera_account: ReraAccount | None = None
    possession_date: date | None = None
    launch_date: date | None = None
    price: Price | None = None
    land_area: Area | None = None
    total_units: Count | None = None
    location: LocationInput | None = None
    is_featured: bool | None = None
    featured_order: FeaturedOrder | None = None
    brochure_gated: bool | None = None
    seo: Seo | None = None
    translations: Translations | None = None
    publish_state: PublishState | None = None

    @field_validator(*_NOT_NULL)
    @classmethod
    def _not_null(cls, value: Any) -> Any:
        # Runs only for fields the client sent (defaults aren't validated).
        if value is None:
            raise PydanticCustomError("not_null", "This can't be empty.")
        return value

    @field_validator("publish_state")
    @classmethod
    def _no_publish_by_patch(cls, value: PublishState | None) -> PublishState | None:
        if value == "published":
            raise PydanticCustomError(
                "publish_by_patch", "Use Publish to put a project on the website."
            )
        return value

    @field_validator("translations")
    @classmethod
    def _translatable(cls, value: Translations | None) -> Translations | None:
        return value if value is None else check_translation_fields(value, PROJECT_TRANSLATABLE)
