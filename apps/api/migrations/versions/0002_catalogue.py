"""Catalogue: cities, localities, amenities, projects and their ordered children (towers,
configurations, specifications, location advantages, construction updates, payment plans,
project ↔ amenity links).

Revision ID: 0002
Revises: 0001
Created: 2026-10-22 14:22:55.311962+00:00

What changes and why: the Phase 4 projects module (handbook/ARCHITECTURE.md §4, §6): money in
whole rupees (bigint), area in square metres (numeric), UUID v7 ids, timestamptz, `seo` and
`translations` JSON (D-014), `is_sample` (D-015), RERA fields (D-002). The composite foreign key
project(city_id, locality_id) → locality(city_id, id) keeps a project's locality inside its city.
No `unit` or `listing` tables (D-004, D-005).
Downgrade safe: only before real projects exist. It drops every table this creates, with their
rows; Phase 3 tables are untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "amenity",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("icon", sa.String(length=40), nullable=False),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "category IN ('lifestyle', 'sports', 'kids', 'security', 'green', 'convenience', 'other')",
            name=op.f("ck_amenity_category_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_amenity")),
        sa.UniqueConstraint("slug", name=op.f("uq_amenity_slug")),
    )
    op.create_table(
        "city",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=60), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_city")),
        sa.UniqueConstraint("slug", name=op.f("uq_city_slug")),
    )
    op.create_table(
        "locality",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("city_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["city_id"], ["city.id"], name=op.f("fk_locality_city_id_city"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_locality")),
        sa.UniqueConstraint("city_id", "id", name=op.f("uq_locality_city_id_id")),
        sa.UniqueConstraint("city_id", "slug", name=op.f("uq_locality_city_id_slug")),
    )
    op.create_table(
        "project",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("tagline", sa.String(length=160), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "sales_status",
            sa.String(length=16),
            server_default=sa.text("'available'"),
            nullable=False,
        ),
        sa.Column(
            "project_type",
            sa.String(length=16),
            server_default=sa.text("'residential'"),
            nullable=False,
        ),
        sa.Column(
            "rera_authority",
            sa.String(length=40),
            server_default=sa.text("'UP-RERA'"),
            nullable=False,
        ),
        sa.Column("rera_number", sa.String(length=60), nullable=True),
        sa.Column("rera_url", sa.String(length=500), nullable=True),
        sa.Column("rera_bank_name", sa.String(length=100), nullable=True),
        sa.Column("rera_account_name", sa.String(length=120), nullable=True),
        sa.Column("rera_account_number", sa.String(length=40), nullable=True),
        sa.Column("possession_date", sa.Date(), nullable=True),
        sa.Column("launch_date", sa.Date(), nullable=True),
        sa.Column("total_units", sa.Integer(), nullable=True),
        sa.Column("land_area_min_sqm", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("land_area_max_sqm", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("land_area_basis", sa.String(length=16), nullable=True),
        sa.Column("land_area_display_unit", sa.String(length=8), nullable=True),
        sa.Column("address_line", sa.String(length=300), nullable=True),
        sa.Column("city_id", sa.UUID(), nullable=True),
        sa.Column("locality_id", sa.UUID(), nullable=True),
        sa.Column(
            "state", sa.String(length=60), server_default=sa.text("'Uttar Pradesh'"), nullable=False
        ),
        sa.Column("pincode", sa.String(length=6), nullable=True),
        sa.Column("lat", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("lng", sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column("google_maps_url", sa.String(length=2048), nullable=True),
        sa.Column("plus_code", sa.String(length=40), nullable=True),
        sa.Column("pin_source", sa.String(length=10), nullable=True),
        sa.Column(
            "seo",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "publish_state", sa.String(length=12), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_featured", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("featured_order", sa.Integer(), nullable=True),
        sa.Column("brochure_gated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "price_on_request", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("price_min_inr", sa.BigInteger(), nullable=True),
        sa.Column("price_max_inr", sa.BigInteger(), nullable=True),
        sa.Column("rate_inr", sa.BigInteger(), nullable=True),
        sa.Column("rate_unit", sa.String(length=8), nullable=True),
        sa.Column("price_note", sa.String(length=160), nullable=True),
        sa.CheckConstraint(
            "land_area_basis IN ('carpet', 'builtup', 'super_builtup', 'plot')",
            name=op.f("ck_project_land_area_basis_valid"),
        ),
        sa.CheckConstraint(
            "land_area_display_unit IN ('sqft', 'sqyd', 'sqm')",
            name=op.f("ck_project_land_area_display_unit_valid"),
        ),
        sa.CheckConstraint(
            "pin_source IN ('url', 'plus_code', 'manual')", name=op.f("ck_project_pin_source_valid")
        ),
        sa.CheckConstraint(
            "project_type IN ('residential', 'commercial', 'mixed', 'plots')",
            name=op.f("ck_project_project_type_valid"),
        ),
        sa.CheckConstraint(
            "publish_state IN ('draft', 'published', 'archived')",
            name=op.f("ck_project_publish_state_valid"),
        ),
        sa.CheckConstraint(
            "rate_unit IN ('sqft', 'sqyd', 'sqm')", name=op.f("ck_project_rate_unit_valid")
        ),
        sa.CheckConstraint(
            "sales_status IN ('available', 'sold_out', 'off_market')",
            name=op.f("ck_project_sales_status_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('upcoming', 'ongoing', 'completed')", name=op.f("ck_project_status_valid")
        ),
        sa.CheckConstraint("(lat IS NULL) = (lng IS NULL)", name=op.f("ck_project_pin_complete")),
        sa.CheckConstraint(
            "COALESCE(price_min_inr, 0) >= 0 AND COALESCE(price_max_inr, 0) >= 0 AND COALESCE(rate_inr, 0) >= 0",
            name=op.f("ck_project_prices_not_negative"),
        ),
        sa.CheckConstraint(
            "land_area_min_sqm <= land_area_max_sqm", name=op.f("ck_project_land_area_range_valid")
        ),
        sa.CheckConstraint(
            "lat BETWEEN -90 AND 90 AND lng BETWEEN -180 AND 180", name=op.f("ck_project_pin_valid")
        ),
        sa.CheckConstraint(
            "locality_id IS NULL OR city_id IS NOT NULL",
            name=op.f("ck_project_locality_needs_city"),
        ),
        sa.CheckConstraint(
            "price_min_inr <= price_max_inr", name=op.f("ck_project_price_range_valid")
        ),
        sa.ForeignKeyConstraint(
            ["city_id", "locality_id"],
            ["locality.city_id", "locality.id"],
            name=op.f("fk_project_city_id_locality"),
        ),
        sa.ForeignKeyConstraint(["city_id"], ["city.id"], name=op.f("fk_project_city_id_city")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_project")),
        sa.UniqueConstraint("slug", name=op.f("uq_project_slug")),
    )
    op.create_index(
        "ix_project_city_id_locality_id", "project", ["city_id", "locality_id"], unique=False
    )
    op.create_index("ix_project_locality_id", "project", ["locality_id"], unique=False)
    op.create_index(
        "ix_project_publish_state_sales_status",
        "project",
        ["publish_state", "sales_status"],
        unique=False,
    )
    op.create_table(
        "location_advantage",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("distance_km", sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column("travel_minutes", sa.Integer(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('transport', 'school', 'hospital', 'shopping', 'office', 'leisure', 'other')",
            name=op.f("ck_location_advantage_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_location_advantage_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_location_advantage")),
    )
    op.create_index(
        "ix_location_advantage_project_id_sort_order",
        "location_advantage",
        ["project_id", "sort_order"],
        unique=False,
    )
    op.create_table(
        "payment_plan",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "stages",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "jsonb_typeof(stages) = 'array'", name=op.f("ck_payment_plan_stages_is_array")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_payment_plan_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_payment_plan")),
    )
    op.create_index(
        "ix_payment_plan_project_id_sort_order",
        "payment_plan",
        ["project_id", "sort_order"],
        unique=False,
    )
    op.create_table(
        "project_amenity",
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("amenity_id", sa.UUID(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.ForeignKeyConstraint(
            ["amenity_id"], ["amenity.id"], name=op.f("fk_project_amenity_amenity_id_amenity")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_project_amenity_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("project_id", "amenity_id", name=op.f("pk_project_amenity")),
    )
    op.create_index(
        op.f("ix_project_amenity_amenity_id"), "project_amenity", ["amenity_id"], unique=False
    )
    op.create_table(
        "specification",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("category", sa.String(length=60), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_specification_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_specification")),
    )
    op.create_index(
        "ix_specification_project_id_sort_order",
        "specification",
        ["project_id", "sort_order"],
        unique=False,
    )
    op.create_table(
        "tower",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=60), nullable=False),
        sa.Column("kind", sa.String(length=8), nullable=False),
        sa.Column("floors", sa.Integer(), nullable=True),
        sa.Column("units_count", sa.Integer(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), server_default=sa.text("'planned'"), nullable=False
        ),
        sa.Column("rera_number", sa.String(length=60), nullable=True),
        sa.Column("possession_date", sa.Date(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "kind IN ('tower', 'phase', 'block', 'wing')", name=op.f("ck_tower_kind_valid")
        ),
        sa.CheckConstraint(
            "status IN ('planned', 'under_construction', 'completed')",
            name=op.f("ck_tower_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_tower_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_tower")),
    )
    op.create_index(
        "ix_tower_project_id_sort_order", "tower", ["project_id", "sort_order"], unique=False
    )
    op.create_table(
        "configuration",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("tower_id", sa.UUID(), nullable=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("property_type", sa.String(length=12), nullable=False),
        sa.Column("bhk", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("bathrooms", sa.Integer(), nullable=True),
        sa.Column("balconies", sa.Integer(), nullable=True),
        sa.Column("area_min_sqm", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("area_max_sqm", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column(
            "area_basis", sa.String(length=16), server_default=sa.text("'carpet'"), nullable=False
        ),
        sa.Column(
            "area_display_unit",
            sa.String(length=8),
            server_default=sa.text("'sqft'"),
            nullable=False,
        ),
        sa.Column(
            "sales_status",
            sa.String(length=16),
            server_default=sa.text("'available'"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "price_on_request", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column("price_min_inr", sa.BigInteger(), nullable=True),
        sa.Column("price_max_inr", sa.BigInteger(), nullable=True),
        sa.Column("rate_inr", sa.BigInteger(), nullable=True),
        sa.Column("rate_unit", sa.String(length=8), nullable=True),
        sa.Column("price_note", sa.String(length=160), nullable=True),
        sa.CheckConstraint(
            "area_basis IN ('carpet', 'builtup', 'super_builtup', 'plot')",
            name=op.f("ck_configuration_area_basis_valid"),
        ),
        sa.CheckConstraint(
            "area_display_unit IN ('sqft', 'sqyd', 'sqm')",
            name=op.f("ck_configuration_area_display_unit_valid"),
        ),
        sa.CheckConstraint(
            "property_type IN ('apartment', 'villa', 'plot', 'penthouse', 'shop', 'office', 'other')",
            name=op.f("ck_configuration_property_type_valid"),
        ),
        sa.CheckConstraint(
            "rate_unit IN ('sqft', 'sqyd', 'sqm')", name=op.f("ck_configuration_rate_unit_valid")
        ),
        sa.CheckConstraint(
            "sales_status IN ('available', 'sold_out', 'off_market')",
            name=op.f("ck_configuration_sales_status_valid"),
        ),
        sa.CheckConstraint(
            "COALESCE(price_min_inr, 0) >= 0 AND COALESCE(price_max_inr, 0) >= 0 AND COALESCE(rate_inr, 0) >= 0",
            name=op.f("ck_configuration_prices_not_negative"),
        ),
        sa.CheckConstraint(
            "area_min_sqm <= area_max_sqm", name=op.f("ck_configuration_area_range_valid")
        ),
        sa.CheckConstraint(
            "price_min_inr <= price_max_inr", name=op.f("ck_configuration_price_range_valid")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_configuration_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tower_id"],
            ["tower.id"],
            name=op.f("fk_configuration_tower_id_tower"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_configuration")),
        sa.UniqueConstraint("project_id", "slug", name=op.f("uq_configuration_project_id_slug")),
    )
    op.create_index(op.f("ix_configuration_tower_id"), "configuration", ["tower_id"], unique=False)
    op.create_table(
        "construction_update",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("tower_id", sa.UUID(), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("update_date", sa.Date(), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column(
            "publish_state", sa.String(length=12), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "publish_state IN ('draft', 'published', 'archived')",
            name=op.f("ck_construction_update_publish_state_valid"),
        ),
        sa.CheckConstraint(
            "progress_percent BETWEEN 0 AND 100",
            name=op.f("ck_construction_update_progress_percent_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_construction_update_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tower_id"],
            ["tower.id"],
            name=op.f("fk_construction_update_tower_id_tower"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_construction_update")),
    )
    op.create_index(
        "ix_construction_update_project_id_sort_order",
        "construction_update",
        ["project_id", "sort_order"],
        unique=False,
    )
    op.create_index(
        op.f("ix_construction_update_tower_id"), "construction_update", ["tower_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_construction_update_tower_id"), table_name="construction_update")
    op.drop_index("ix_construction_update_project_id_sort_order", table_name="construction_update")
    op.drop_table("construction_update")
    op.drop_index(op.f("ix_configuration_tower_id"), table_name="configuration")
    op.drop_table("configuration")
    op.drop_index("ix_tower_project_id_sort_order", table_name="tower")
    op.drop_table("tower")
    op.drop_index("ix_specification_project_id_sort_order", table_name="specification")
    op.drop_table("specification")
    op.drop_index(op.f("ix_project_amenity_amenity_id"), table_name="project_amenity")
    op.drop_table("project_amenity")
    op.drop_index("ix_payment_plan_project_id_sort_order", table_name="payment_plan")
    op.drop_table("payment_plan")
    op.drop_index("ix_location_advantage_project_id_sort_order", table_name="location_advantage")
    op.drop_table("location_advantage")
    op.drop_index("ix_project_publish_state_sales_status", table_name="project")
    op.drop_index("ix_project_locality_id", table_name="project")
    op.drop_index("ix_project_city_id_locality_id", table_name="project")
    op.drop_table("project")
    op.drop_table("locality")
    op.drop_table("city")
    op.drop_table("amenity")
