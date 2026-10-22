"""Tables of the projects module: the catalogue (city, locality, amenity), the project row and
its ordered children (tower, configuration, specification, location advantage, construction
update, payment plan, project ↔ amenity link).

Collaborators: migrations/versions/0002_catalogue.py creates exactly these tables
(tests/test_migrations.py fails on any drift); projects/service.py, children.py and
catalogue.py are the only writers.
Implements: ARCHITECTURE §6 — UUID v7 ids, timestamptz, whole rupees in bigint, area in square
metres as numeric, min/max pairs, `seo` and `translations` JSON (D-014), `is_sample` (D-015).

INVARIANT: a project's locality belongs to the project's city. The composite foreign key
(city_id, locality_id) → locality(city_id, id) enforces it in the database, and
`ck_project_locality_needs_city` stops a locality without a city slipping past it.
INVARIANT: `project.published_at` is set on every publish and never cleared, so NULL means the
project was never published (only those drafts may be deleted, service.delete_project).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import text as sql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from empire_api.db import Base, created_at_column, uuid_pk
from empire_api.projects.vocab import (
    ADVANTAGE_KINDS,
    AMENITY_CATEGORIES,
    AREA_BASES,
    AREA_UNITS,
    PIN_SOURCES,
    PROJECT_STATUSES,
    PROJECT_TYPES,
    PROPERTY_TYPES,
    PUBLISH_STATES,
    SALES_STATUSES,
    TOWER_KINDS,
    TOWER_STATUSES,
    check_in,
)

# Area in square metres with two decimals: 980 sq ft = 91.04 sq m round-trips to 980 sq ft.
AREA_SQM = Numeric(12, 2)


class Timestamps:
    created_at: Mapped[datetime] = created_at_column()
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PriceColumns:
    """Price range and/or rate per unit area (contract schema `Price`). Whole rupees."""

    price_on_request: Mapped[bool] = mapped_column(server_default=sql("false"))
    price_min_inr: Mapped[int | None] = mapped_column(BigInteger)
    price_max_inr: Mapped[int | None] = mapped_column(BigInteger)
    rate_inr: Mapped[int | None] = mapped_column(BigInteger)
    rate_unit: Mapped[str | None] = mapped_column(String(8))
    price_note: Mapped[str | None] = mapped_column(String(160))


def _price_checks() -> tuple[CheckConstraint, ...]:
    return (
        CheckConstraint(check_in("rate_unit", AREA_UNITS), name="rate_unit_valid"),
        CheckConstraint(
            "COALESCE(price_min_inr, 0) >= 0 AND COALESCE(price_max_inr, 0) >= 0 "
            "AND COALESCE(rate_inr, 0) >= 0",
            name="prices_not_negative",
        ),
        CheckConstraint("price_min_inr <= price_max_inr", name="price_range_valid"),
    )


# --- Catalogue ------------------------------------------------------------------------------


class City(Timestamps, Base):
    __tablename__ = "city"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    state: Mapped[str] = mapped_column(String(60))


class Locality(Timestamps, Base):
    __tablename__ = "locality"

    id: Mapped[uuid.UUID] = uuid_pk()
    # WHY CASCADE: a city can only be deleted when no project uses it (catalogue.delete_city),
    # and then its localities are unused too, so they go with it.
    city_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("city.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(120))

    city: Mapped[City] = relationship(lazy="joined")

    __table_args__ = (
        # Also the index for the city_id foreign key (leading column).
        UniqueConstraint("city_id", "slug"),
        # Target of project's composite foreign key (INVARIANT in the module header).
        UniqueConstraint("city_id", "id"),
    )


class Amenity(Timestamps, Base):
    __tablename__ = "amenity"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(80))
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    icon: Mapped[str] = mapped_column(String(40))
    category: Mapped[str] = mapped_column(String(16))

    __table_args__ = (
        CheckConstraint(check_in("category", AMENITY_CATEGORIES), name="category_valid"),
    )


# --- Project ---------------------------------------------------------------------------------


class Project(Timestamps, PriceColumns, Base):
    """One development (contract schemas ProjectInput / ProjectAdmin)."""

    __tablename__ = "project"

    id: Mapped[uuid.UUID] = uuid_pk()
    slug: Mapped[str] = mapped_column(String(120), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    tagline: Mapped[str | None] = mapped_column(String(160))
    description: Mapped[str | None] = mapped_column(Text)  # WhatsApp-style formatted text
    status: Mapped[str] = mapped_column(String(16))
    sales_status: Mapped[str] = mapped_column(String(16), server_default=sql("'available'"))
    project_type: Mapped[str] = mapped_column(String(16), server_default=sql("'residential'"))

    # COMPLIANCE: D-002. Shown on every project page; publish is blocked without the number.
    rera_authority: Mapped[str] = mapped_column(String(40), server_default=sql("'UP-RERA'"))
    rera_number: Mapped[str | None] = mapped_column(String(60))
    rera_url: Mapped[str | None] = mapped_column(String(500))
    # The RERA designated account is public on the regulator's site; not personal data.
    rera_bank_name: Mapped[str | None] = mapped_column(String(100))
    rera_account_name: Mapped[str | None] = mapped_column(String(120))
    rera_account_number: Mapped[str | None] = mapped_column(String(40))
    possession_date: Mapped[date | None] = mapped_column()
    launch_date: Mapped[date | None] = mapped_column()
    total_units: Mapped[int | None] = mapped_column()

    land_area_min_sqm: Mapped[Decimal | None] = mapped_column(AREA_SQM)
    land_area_max_sqm: Mapped[Decimal | None] = mapped_column(AREA_SQM)
    land_area_basis: Mapped[str | None] = mapped_column(String(16))
    land_area_display_unit: Mapped[str | None] = mapped_column(String(8))

    address_line: Mapped[str | None] = mapped_column(String(300))
    city_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("city.id"))
    locality_id: Mapped[uuid.UUID | None] = mapped_column()
    state: Mapped[str] = mapped_column(String(60), server_default=sql("'Uttar Pradesh'"))
    pincode: Mapped[str | None] = mapped_column(String(6))
    lat: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(9, 6))
    google_maps_url: Mapped[str | None] = mapped_column(String(2048))
    plus_code: Mapped[str | None] = mapped_column(String(40))
    pin_source: Mapped[str | None] = mapped_column(String(10))

    seo: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))
    translations: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))

    publish_state: Mapped[str] = mapped_column(String(12), server_default=sql("'draft'"))
    published_at: Mapped[datetime | None] = mapped_column()
    is_featured: Mapped[bool] = mapped_column(server_default=sql("false"))
    featured_order: Mapped[int | None] = mapped_column()
    brochure_gated: Mapped[bool] = mapped_column(server_default=sql("false"))
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    # WHY no foreign key: like audit_log, authorship must outlive any staff account row.
    created_by: Mapped[uuid.UUID | None] = mapped_column()
    updated_by: Mapped[uuid.UUID | None] = mapped_column()

    city: Mapped[City | None] = relationship(foreign_keys=[city_id])
    locality: Mapped[Locality | None] = relationship(
        primaryjoin="Project.locality_id == Locality.id",
        foreign_keys=[locality_id],
        viewonly=True,
    )
    towers: Mapped[list[Tower]] = relationship(
        order_by="(Tower.sort_order, Tower.id)", cascade="all, delete-orphan", passive_deletes=True
    )
    configurations: Mapped[list[Configuration]] = relationship(
        order_by="(Configuration.sort_order, Configuration.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    specifications: Mapped[list[Specification]] = relationship(
        order_by="(Specification.sort_order, Specification.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    location_advantages: Mapped[list[LocationAdvantage]] = relationship(
        order_by="(LocationAdvantage.sort_order, LocationAdvantage.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    construction_updates: Mapped[list[ConstructionUpdate]] = relationship(
        order_by="(ConstructionUpdate.sort_order, ConstructionUpdate.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    payment_plans: Mapped[list[PaymentPlan]] = relationship(
        order_by="(PaymentPlan.sort_order, PaymentPlan.id)",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    amenity_links: Mapped[list[ProjectAmenity]] = relationship(
        order_by="ProjectAmenity.sort_order", cascade="all, delete-orphan", passive_deletes=True
    )

    __table_args__ = (
        ForeignKeyConstraint(["city_id", "locality_id"], ["locality.city_id", "locality.id"]),
        Index("ix_project_publish_state_sales_status", "publish_state", "sales_status"),
        Index("ix_project_city_id_locality_id", "city_id", "locality_id"),
        Index("ix_project_locality_id", "locality_id"),
        CheckConstraint(check_in("status", PROJECT_STATUSES), name="status_valid"),
        CheckConstraint(check_in("sales_status", SALES_STATUSES), name="sales_status_valid"),
        CheckConstraint(check_in("publish_state", PUBLISH_STATES), name="publish_state_valid"),
        CheckConstraint(check_in("project_type", PROJECT_TYPES), name="project_type_valid"),
        CheckConstraint(check_in("land_area_basis", AREA_BASES), name="land_area_basis_valid"),
        CheckConstraint(
            check_in("land_area_display_unit", AREA_UNITS), name="land_area_display_unit_valid"
        ),
        CheckConstraint("land_area_min_sqm <= land_area_max_sqm", name="land_area_range_valid"),
        CheckConstraint(check_in("pin_source", PIN_SOURCES), name="pin_source_valid"),
        CheckConstraint("(lat IS NULL) = (lng IS NULL)", name="pin_complete"),
        CheckConstraint("lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180", name="pin_valid"),
        CheckConstraint("locality_id IS NULL OR city_id IS NOT NULL", name="locality_needs_city"),
        *_price_checks(),
    )


class ProjectAmenity(Base):
    """Ordered link between a project and a catalogue amenity."""

    __tablename__ = "project_amenity"

    project_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("project.id", ondelete="CASCADE"), primary_key=True
    )
    # WHY RESTRICT (the default): an amenity in use can't vanish from project pages;
    # catalogue.delete_amenity answers 409 "used by N projects" first.
    amenity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("amenity.id"), primary_key=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))

    amenity: Mapped[Amenity] = relationship(lazy="joined")


# --- Children (ordered by sort_order within a project) ---------------------------------------


class Tower(Timestamps, Base):
    __tablename__ = "tower"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(60))
    kind: Mapped[str] = mapped_column(String(8))
    floors: Mapped[int | None] = mapped_column()
    units_count: Mapped[int | None] = mapped_column()
    status: Mapped[str] = mapped_column(String(20), server_default=sql("'planned'"))
    rera_number: Mapped[str | None] = mapped_column(String(60))  # own phase registration only
    possession_date: Mapped[date | None] = mapped_column()
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))

    __table_args__ = (
        Index("ix_tower_project_id_sort_order", "project_id", "sort_order"),
        CheckConstraint(check_in("kind", TOWER_KINDS), name="kind_valid"),
        CheckConstraint(check_in("status", TOWER_STATUSES), name="status_valid"),
    )


class Configuration(Timestamps, PriceColumns, Base):
    """A floor-plan type, e.g. "3 BHK Premium". On the public site this is a property (D-004).

    Availability is tracked here, not per flat (D-005).
    """

    __tablename__ = "configuration"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    tower_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tower.id", ondelete="SET NULL"), index=True
    )
    slug: Mapped[str] = mapped_column(String(120))
    name: Mapped[str] = mapped_column(String(80))
    property_type: Mapped[str] = mapped_column(String(12))
    bhk: Mapped[Decimal | None] = mapped_column(Numeric(3, 1))
    bathrooms: Mapped[int | None] = mapped_column()
    balconies: Mapped[int | None] = mapped_column()
    area_min_sqm: Mapped[Decimal | None] = mapped_column(AREA_SQM)
    area_max_sqm: Mapped[Decimal | None] = mapped_column(AREA_SQM)
    area_basis: Mapped[str] = mapped_column(String(16), server_default=sql("'carpet'"))
    area_display_unit: Mapped[str] = mapped_column(String(8), server_default=sql("'sqft'"))
    sales_status: Mapped[str] = mapped_column(String(16), server_default=sql("'available'"))
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))
    is_sample: Mapped[bool] = mapped_column(server_default=sql("false"))
    translations: Mapped[dict[str, Any]] = mapped_column(server_default=sql("'{}'::jsonb"))

    __table_args__ = (
        # Also the index for the project_id foreign key (leading column).
        UniqueConstraint("project_id", "slug"),
        CheckConstraint(check_in("property_type", PROPERTY_TYPES), name="property_type_valid"),
        CheckConstraint(check_in("sales_status", SALES_STATUSES), name="sales_status_valid"),
        CheckConstraint(check_in("area_basis", AREA_BASES), name="area_basis_valid"),
        CheckConstraint(check_in("area_display_unit", AREA_UNITS), name="area_display_unit_valid"),
        CheckConstraint("area_min_sqm <= area_max_sqm", name="area_range_valid"),
        *_price_checks(),
    )


class Specification(Timestamps, Base):
    __tablename__ = "specification"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    category: Mapped[str] = mapped_column(String(60))
    text: Mapped[str] = mapped_column(String(500))
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))

    __table_args__ = (Index("ix_specification_project_id_sort_order", "project_id", "sort_order"),)


class LocationAdvantage(Timestamps, Base):
    """A nearby place with an approximate road distance (shown with ≈ on the site)."""

    __tablename__ = "location_advantage"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    label: Mapped[str] = mapped_column(String(80))
    kind: Mapped[str] = mapped_column(String(12))
    distance_km: Mapped[Decimal | None] = mapped_column(Numeric(6, 2))
    travel_minutes: Mapped[int | None] = mapped_column()
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))

    __table_args__ = (
        Index("ix_location_advantage_project_id_sort_order", "project_id", "sort_order"),
        CheckConstraint(check_in("kind", ADVANTAGE_KINDS), name="kind_valid"),
    )


class ConstructionUpdate(Timestamps, Base):
    """A dated progress note, optionally for one tower. Photos arrive with media (part 2)."""

    __tablename__ = "construction_update"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    tower_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tower.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    update_date: Mapped[date] = mapped_column()
    progress_percent: Mapped[int | None] = mapped_column()
    body: Mapped[str | None] = mapped_column(Text)
    publish_state: Mapped[str] = mapped_column(String(12), server_default=sql("'draft'"))
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))

    __table_args__ = (
        Index("ix_construction_update_project_id_sort_order", "project_id", "sort_order"),
        CheckConstraint(check_in("publish_state", PUBLISH_STATES), name="publish_state_valid"),
        CheckConstraint("progress_percent BETWEEN 0 AND 100", name="progress_percent_valid"),
    )


class PaymentPlan(Timestamps, Base):
    """A payment schedule. Stage percentages total exactly 100 (schemas_children.py).

    WHY stages as a validated JSON array and not a payment_plan_stage table: stages are always
    read and written together with their plan, never queried on their own, and the "total is
    100" rule needs the whole list at once. A child table would add a delete-and-reinsert on
    every edit and a second ordering column for no query benefit. INVARIANT: every write goes
    through `PaymentPlanInput`, which checks the shape and the total; the CHECK below keeps the
    column an array.
    """

    __tablename__ = "payment_plan"

    id: Mapped[uuid.UUID] = uuid_pk()
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("project.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, server_default=sql("'[]'::jsonb"))
    is_visible: Mapped[bool] = mapped_column(server_default=sql("true"))
    sort_order: Mapped[int] = mapped_column(server_default=sql("0"))

    __table_args__ = (
        Index("ix_payment_plan_project_id_sort_order", "project_id", "sort_order"),
        CheckConstraint("jsonb_typeof(stages) = 'array'", name="stages_is_array"),
    )
