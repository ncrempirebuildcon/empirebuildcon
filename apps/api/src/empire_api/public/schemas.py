"""Strict public schemas returning only published data (Task 5.1).

INVARIANT: No staff or personal fields (created_by, updated_by, internal notes, passwords,
personal contact records, staff user ids) may ever be defined or returned here.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from pydantic import Field

from empire_api.projects.fields import OutModel
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
    Price,
    Seo,
    Translations,
)
from empire_api.users.schemas import PageMeta


class PublicMedia(OutModel):
    id: uuid.UUID
    kind: str
    url: str
    thumbnail_url: str | None = None
    title: str | None = None
    alt_text: str | None = None
    format: str | None = None
    bytes: int | None = None
    width: int | None = None
    height: int | None = None
    duration_s: float | None = None
    label: str | None = None
    label_month: str | None = None
    is_sample: bool = False


class PublicLinkedMedia(PublicMedia):
    link_id: uuid.UUID
    role: str
    sort_order: int
    is_cover: bool
    is_visible: bool


class PublicCompany(OutModel):
    name: str
    legal_name: str | None = None
    tagline: str | None = None
    gstin: str | None = None
    address: str | None = None
    registered_address: str | None = None
    corporate_address: str | None = None
    phones: list[str] = Field(default_factory=list)
    whatsapp: str | None = None
    whatsapp_message: str | None = None
    office_hours: str | None = None
    emails: list[str] = Field(default_factory=list)


class PublicRegulator(OutModel):
    state: str = "UP"
    authority: str = "UP-RERA"
    website: str = "https://www.up-rera.in"
    name: str = "Uttar Pradesh Real Estate Regulatory Authority"
    promoter_number: str | None = None


class PublicNavItem(OutModel):
    label: str
    path: str


class PublicTracking(OutModel):
    gtm_id: str | None = None
    ga4_id: str | None = None
    meta_pixel_id: str | None = None


class PublicConsentText(OutModel):
    id: uuid.UUID
    kind: str
    version: int
    body: str
    checkbox_label: str


class PublicOffer(OutModel):
    id: uuid.UUID
    title: str
    body: str | None = None
    image: PublicMedia | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    terms: str | None = None
    terms_url: str | None = None
    placement: str
    project_slug: str | None = None


class PublicSeoDefaults(OutModel):
    default_title: str | None = None
    title_suffix: str | None = None
    default_description: str | None = None


class PublicSite(OutModel):
    company: PublicCompany
    social: dict[str, str] = Field(default_factory=dict)
    regulator: PublicRegulator
    nav: list[PublicNavItem] = Field(default_factory=list)
    features: dict[str, bool] = Field(default_factory=dict)
    tracking: PublicTracking | None = None
    consent: dict[str, PublicConsentText | None] = Field(default_factory=dict)
    offers: list[PublicOffer] = Field(default_factory=list)
    locales: list[str] = Field(default_factory=lambda: ["en"])
    seo: PublicSeoDefaults | None = None


class PublicRera(OutModel):
    authority: str
    number: str | None = None
    url: str | None = None
    qr: PublicMedia | None = None


class PublicProjectSummary(OutModel):
    id: uuid.UUID
    slug: str
    name: str
    status: str
    sales_status: str
    city: CityRef | None = None
    locality: LocalityRef | None = None
    price: Price
    configuration_labels: list[str] = Field(default_factory=list)
    property_types: list[str] = Field(default_factory=list)
    cover: PublicMedia | None = None
    rera: PublicRera
    possession_date: date | None = None
    is_featured: bool = False
    is_sample: bool = False


class PublicProjectDetail(PublicProjectSummary):
    tagline: str | None = None
    description: str | None = None
    project_type: str
    land_area: Area | None = None
    total_units: int | None = None
    launch_date: date | None = None
    location: Location
    towers: list[Tower] = Field(default_factory=list)
    configurations: list[Configuration] = Field(default_factory=list)
    amenities: list[Amenity] = Field(default_factory=list)
    specifications: list[Specification] = Field(default_factory=list)
    location_advantages: list[LocationAdvantage] = Field(default_factory=list)
    construction_updates: list[ConstructionUpdate] = Field(default_factory=list)
    payment_plans: list[PaymentPlan] = Field(default_factory=list)
    gallery: list[PublicLinkedMedia] = Field(default_factory=list)
    videos: list[PublicLinkedMedia] = Field(default_factory=list)
    documents: list[PublicLinkedMedia] = Field(default_factory=list)
    brochure: PublicLinkedMedia | None = None
    brochure_gated: bool = False
    faqs: list[PublicFaq] = Field(default_factory=list)
    seo: Seo
    translations: Translations
    updated_at: datetime


class PublicProjectRef(OutModel):
    slug: str
    name: str
    status: str
    city: CityRef | None = None
    locality: LocalityRef | None = None
    rera: PublicRera | None = None


class PublicPropertySummary(OutModel):
    id: uuid.UUID
    slug: str
    name: str
    property_type: str
    bhk: float | None = None
    area: Area
    price: Price
    sales_status: str
    cover: PublicMedia | None = None
    project: PublicProjectRef
    is_sample: bool = False


class PublicPropertyDetail(Configuration):
    project: PublicProjectSummary


class PublicCity(OutModel):
    id: uuid.UUID
    name: str
    slug: str
    state: str
    project_count: int


class PublicBlock(OutModel):
    id: uuid.UUID
    type: str
    data: dict[str, Any]
    sort_order: int
    is_visible: bool = True


class PublicPage(OutModel):
    id: uuid.UUID
    slug: str
    title: str
    kind: str
    publish_state: str = "published"
    show_in_nav: bool = False
    nav_order: int | None = None
    blocks: list[PublicBlock] = Field(default_factory=list)
    legal_version: str | None = None
    is_draft_text: bool = False
    seo: Seo
    translations: Translations
    updated_at: datetime


class PublicPost(OutModel):
    id: uuid.UUID
    slug: str
    title: str
    excerpt: str | None = None
    body: str
    cover: PublicMedia | None = None
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    author: str | None = None  # Author display name only
    published_at: datetime | None = None
    seo: Seo
    translations: Translations


class PublicFaq(OutModel):
    id: uuid.UUID
    project_id: uuid.UUID | None = None
    question: str
    answer: str
    sort_order: int = 0
    is_visible: bool = True
    translations: Translations


class PublicTestimonial(OutModel):
    id: uuid.UUID
    person_name: str
    person_detail: str | None = None
    quote: str
    project_id: uuid.UUID | None = None
    source: str
    source_url: str | None = None
    consent_date: date | None = None
    rating: int | None = None
    photo: PublicMedia | None = None
    is_visible: bool = True


class PublicRedirect(OutModel):
    id: uuid.UUID
    from_path: str
    to_path: str
    status_code: int = 308


class PublicSitemapEntry(OutModel):
    path: str
    lastmod: datetime
    alternates: dict[str, str] = Field(default_factory=dict)


class PublicProjectList(OutModel):
    items: list[PublicProjectSummary]
    meta: PageMeta


class PublicPropertyList(OutModel):
    items: list[PublicPropertySummary]
    meta: PageMeta


class PublicPostList(OutModel):
    items: list[PublicPost]
    meta: PageMeta
