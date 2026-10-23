"""Media: the library (`media`), signed direct uploads (`upload_intent`) and the links that
attach library items to projects, configurations and construction updates (`media_link`).

Revision ID: 0003
Revises: 0002
Created: 2026-10-22 19:00:57.043322+00:00

What changes and why: the Phase 4 media module (handbook/ARCHITECTURE.md §6, §12; D-033).
`media_link` is an exclusive arc: one nullable foreign key per owner type, cascading on owner
delete, with `ck_media_link_one_owner` requiring exactly one; `media_id` is RESTRICT, so a file in
use can't be deleted. Partial unique indexes allow one cover per owner and role, and one link per
owner in each single-valued role (a project's brochure, RERA QR, hero and share image; a
configuration's floor plan). CHECKs keep the honest labels consistent (a progress photo has a
month, the month is a first day, documents have no label). `page_id` / `post_id` come with
part 4. No existing table changes.
Downgrade safe: only before real media exists. It drops the three tables with their rows (the
files at the store stay where they are); Phase 3 and catalogue tables are untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "media",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("store", sa.String(length=12), nullable=False),
        sa.Column("public_id", sa.String(length=255), nullable=False),
        sa.Column("resource_type", sa.String(length=8), nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("format", sa.String(length=10), nullable=False),
        sa.Column("bytes", sa.BigInteger(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("duration_s", sa.Numeric(precision=10, scale=2), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("alt_text", sa.String(length=250), nullable=True),
        sa.Column("label", sa.String(length=20), nullable=True),
        sa.Column("label_month", sa.Date(), nullable=True),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
            "kind <> 'document' OR label IS NULL", name=op.f("ck_media_document_has_no_label")
        ),
        sa.CheckConstraint(
            "kind IN ('image', 'video', 'document')", name=op.f("ck_media_kind_valid")
        ),
        sa.CheckConstraint(
            "label IN ('artist_impression', 'actual_photo', 'progress_photo')",
            name=op.f("ck_media_label_valid"),
        ),
        sa.CheckConstraint(
            "label IS DISTINCT FROM 'progress_photo' OR label_month IS NOT NULL",
            name=op.f("ck_media_progress_photo_has_month"),
        ),
        sa.CheckConstraint(
            "label_month IS NULL OR label IN ('actual_photo', 'progress_photo')",
            name=op.f("ck_media_label_month_needs_dated_label"),
        ),
        sa.CheckConstraint(
            "resource_type IN ('image', 'video', 'raw')", name=op.f("ck_media_resource_type_valid")
        ),
        sa.CheckConstraint("store IN ('cloudinary', 'fake')", name=op.f("ck_media_store_valid")),
        sa.CheckConstraint("bytes >= 0", name=op.f("ck_media_bytes_not_negative")),
        sa.CheckConstraint(
            "label_month IS NULL OR EXTRACT(DAY FROM label_month) = 1",
            name=op.f("ck_media_label_month_first_day"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media")),
        sa.UniqueConstraint("public_id", name=op.f("uq_media_public_id")),
    )
    op.create_index(
        "ix_media_created_at", "media", [sa.literal_column("created_at DESC")], unique=False
    )
    op.create_table(
        "upload_intent",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("public_id", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=10), nullable=False),
        sa.Column("resource_type", sa.String(length=8), nullable=False),
        sa.Column("max_bytes", sa.BigInteger(), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('video', 'document')", name=op.f("ck_upload_intent_kind_valid")
        ),
        sa.CheckConstraint(
            "resource_type IN ('image', 'video', 'raw')",
            name=op.f("ck_upload_intent_resource_type_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_upload_intent")),
        sa.UniqueConstraint("public_id", name=op.f("uq_upload_intent_public_id")),
    )
    op.create_index(
        op.f("ix_upload_intent_expires_at"), "upload_intent", ["expires_at"], unique=False
    )
    op.create_table(
        "media_link",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("configuration_id", sa.UUID(), nullable=True),
        sa.Column("construction_update_id", sa.UUID(), nullable=True),
        sa.Column("role", sa.String(length=12), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_cover", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
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
            "role IN ('gallery', 'floor_plan', 'brochure', 'rera_qr', 'video', 'document', 'hero', 'og_image')",
            name=op.f("ck_media_link_role_valid"),
        ),
        sa.CheckConstraint(
            "is_visible OR NOT is_cover", name=op.f("ck_media_link_cover_is_visible")
        ),
        sa.CheckConstraint(
            "num_nonnulls(project_id, configuration_id, construction_update_id) = 1",
            name=op.f("ck_media_link_one_owner"),
        ),
        sa.ForeignKeyConstraint(
            ["configuration_id"],
            ["configuration.id"],
            name=op.f("fk_media_link_configuration_id_configuration"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["construction_update_id"],
            ["construction_update.id"],
            name=op.f("fk_media_link_construction_update_id_construction_update"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["media_id"], ["media.id"], name=op.f("fk_media_link_media_id_media")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_media_link_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_media_link")),
        sa.UniqueConstraint(
            "configuration_id",
            "role",
            "media_id",
            name=op.f("uq_media_link_configuration_id_role_media_id"),
        ),
        sa.UniqueConstraint(
            "construction_update_id",
            "role",
            "media_id",
            name=op.f("uq_media_link_construction_update_id_role_media_id"),
        ),
        sa.UniqueConstraint(
            "project_id", "role", "media_id", name=op.f("uq_media_link_project_id_role_media_id")
        ),
    )
    op.create_index(op.f("ix_media_link_media_id"), "media_link", ["media_id"], unique=False)
    op.create_index(
        "uq_media_link_configuration_cover",
        "media_link",
        ["configuration_id", "role"],
        unique=True,
        postgresql_where=sa.text("is_cover AND configuration_id IS NOT NULL"),
    )
    op.create_index(
        "uq_media_link_configuration_single_role",
        "media_link",
        ["configuration_id", "role"],
        unique=True,
        postgresql_where=sa.text("role IN ('floor_plan') AND configuration_id IS NOT NULL"),
    )
    op.create_index(
        "uq_media_link_construction_update_cover",
        "media_link",
        ["construction_update_id", "role"],
        unique=True,
        postgresql_where=sa.text("is_cover AND construction_update_id IS NOT NULL"),
    )
    op.create_index(
        "uq_media_link_project_cover",
        "media_link",
        ["project_id", "role"],
        unique=True,
        postgresql_where=sa.text("is_cover AND project_id IS NOT NULL"),
    )
    op.create_index(
        "uq_media_link_project_single_role",
        "media_link",
        ["project_id", "role"],
        unique=True,
        postgresql_where=sa.text(
            "role IN ('brochure', 'hero', 'og_image', 'rera_qr') AND project_id IS NOT NULL"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_media_link_project_single_role",
        table_name="media_link",
        postgresql_where=sa.text(
            "role IN ('brochure', 'hero', 'og_image', 'rera_qr') AND project_id IS NOT NULL"
        ),
    )
    op.drop_index(
        "uq_media_link_project_cover",
        table_name="media_link",
        postgresql_where=sa.text("is_cover AND project_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_media_link_construction_update_cover",
        table_name="media_link",
        postgresql_where=sa.text("is_cover AND construction_update_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_media_link_configuration_single_role",
        table_name="media_link",
        postgresql_where=sa.text("role IN ('floor_plan') AND configuration_id IS NOT NULL"),
    )
    op.drop_index(
        "uq_media_link_configuration_cover",
        table_name="media_link",
        postgresql_where=sa.text("is_cover AND configuration_id IS NOT NULL"),
    )
    op.drop_index(op.f("ix_media_link_media_id"), table_name="media_link")
    op.drop_table("media_link")
    op.drop_index(op.f("ix_upload_intent_expires_at"), table_name="upload_intent")
    op.drop_table("upload_intent")
    op.drop_index("ix_media_created_at", table_name="media")
    op.drop_table("media")
