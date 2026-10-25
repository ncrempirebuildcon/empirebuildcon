"""Content and SEO: `page` with its ordered `block` rows, `post`, `faq`, `offer`, `testimonial`
(the content module) and `redirect` (the SEO module); `media_link` gains `page_id` and `post_id`.

Revision ID: 0005
Revises: 0004
Created: 2026-10-24 15:48:46.059873+00:00

What changes and why: Phase 4 part 4 (handbook/ARCHITECTURE.md §4, §6, §9, §10, §16; D-014,
D-015, D-017, D-018). Pages, posts and FAQs carry `translations` (D-014) and pages/posts `seo`
JSON; every table has `created_by`/`updated_by`, and pages, posts, FAQs and offers `is_sample`
(D-015). Testimonials have no sample flag on purpose (a sample testimonial must never exist) and a
CHECK that a visible one has a consent date and a source. Offers keep `went_live_at` and
`is_live_announced` for the schedule tick; there is no countdown column. Redirects are unique by
`from_path`, 301 or 308, never to themselves, and `to_path` is always a site path (one leading
`/`, no `//`, no backslash: no open redirect, review H1); `hits`/`last_hit_at` wait for Phase 5.
Pages carry `is_required` (system pages and the seeded legal pages; review L8). Offer images and
testimonial photos are RESTRICT foreign keys to `media`; FAQs cascade with their project (only
never-published drafts can be deleted); an offer's project is RESTRICT and a project-placement
offer must name one (review L12); testimonials keep themselves and lose the project (SET NULL). `media_link`'s exclusive arc adds `page_id` and `post_id` (CASCADE): the
CHECK `ck_media_link_one_owner` now counts five owners and `ck_media_link_role_valid` adds the
content roles `block` and `cover`, with the per-owner unique indexes for the new owners.
Downgrade safe: only before real content exists. It deletes every page and post media link and
drops the seven new tables with their rows (pages, posts, FAQs, offers, testimonials and
redirects), then restores the 0003 constraints. Earlier tables are otherwise untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OWNERS_BEFORE = "project_id, configuration_id, construction_update_id"
_OWNERS_AFTER = f"{_OWNERS_BEFORE}, page_id, post_id"
_ROLES_BEFORE = (
    "'gallery', 'floor_plan', 'brochure', 'rera_qr', 'video', 'document', 'hero', 'og_image'"
)
_ROLES_AFTER = f"{_ROLES_BEFORE}, 'block', 'cover'"


def upgrade() -> None:
    op.create_table(
        "page",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column(
            "kind", sa.String(length=10), server_default=sa.text("'standard'"), nullable=False
        ),
        sa.Column(
            "publish_state", sa.String(length=12), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("unpublish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("show_in_nav", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("nav_order", sa.Integer(), nullable=True),
        sa.Column("legal_version", sa.String(length=20), nullable=True),
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
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.CheckConstraint(
            "kind IN ('standard', 'landing', 'legal', 'system')", name=op.f("ck_page_kind_valid")
        ),
        sa.CheckConstraint(
            "kind <> 'system' OR is_required", name=op.f("ck_page_system_is_required")
        ),
        sa.CheckConstraint(
            "NOT is_required OR kind IN ('system', 'legal')",
            name=op.f("ck_page_required_is_system_or_legal"),
        ),
        sa.CheckConstraint(
            "legal_version IS NULL OR kind = 'legal'", name=op.f("ck_page_legal_version_on_legal")
        ),
        sa.CheckConstraint(
            "publish_state IN ('draft', 'published', 'archived')",
            name=op.f("ck_page_publish_state_valid"),
        ),
        sa.CheckConstraint(
            "nav_order IS NULL OR nav_order >= 0", name=op.f("ck_page_nav_order_not_negative")
        ),
        sa.CheckConstraint(
            "publish_at IS NULL OR unpublish_at IS NULL OR unpublish_at > publish_at",
            name=op.f("ck_page_unpublish_after_publish"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_page")),
        sa.UniqueConstraint("slug", name=op.f("uq_page_slug")),
    )
    op.create_table(
        "post",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("excerpt", sa.String(length=300), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=40), nullable=True),
        sa.Column(
            "tags",
            postgresql.ARRAY(sa.String(length=40)),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("author_id", sa.UUID(), nullable=True),
        sa.Column(
            "publish_state", sa.String(length=12), server_default=sa.text("'draft'"), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "publish_state IN ('draft', 'published', 'archived')",
            name=op.f("ck_post_publish_state_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_post")),
        sa.UniqueConstraint("slug", name=op.f("uq_post_slug")),
    )
    op.create_index(
        "ix_post_publish_state_published_at",
        "post",
        ["publish_state", sa.literal_column("published_at DESC")],
        unique=False,
    )
    op.create_table(
        "redirect",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("from_path", sa.String(length=500), nullable=False),
        sa.Column("to_path", sa.String(length=500), nullable=False),
        sa.Column("status_code", sa.SmallInteger(), server_default=sa.text("308"), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "origin", sa.String(length=10), server_default=sa.text("'manual'"), nullable=False
        ),
        sa.Column("hits", sa.BigInteger(), server_default=sa.text("0"), nullable=False),
        sa.Column("last_hit_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("left(from_path, 1) = '/'", name=op.f("ck_redirect_from_path_is_path")),
        sa.CheckConstraint(
            "left(to_path, 1) = '/' AND left(to_path, 2) <> '//' AND strpos(to_path, '\\') = 0",
            name=op.f("ck_redirect_to_path_is_site_path"),
        ),
        sa.CheckConstraint(
            "origin IN ('manual', 'page', 'post', 'project')", name=op.f("ck_redirect_origin_valid")
        ),
        sa.CheckConstraint("from_path <> to_path", name=op.f("ck_redirect_not_to_itself")),
        sa.CheckConstraint("hits >= 0", name=op.f("ck_redirect_hits_not_negative")),
        sa.CheckConstraint("status_code IN (301, 308)", name=op.f("ck_redirect_status_code_valid")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_redirect")),
        sa.UniqueConstraint("from_path", name=op.f("uq_redirect_from_path")),
    )
    op.create_table(
        "block",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=16), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
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
            "type IN ('hero', 'rich_text', 'image', 'gallery', 'video', 'project_grid', 'property_grid', 'cta', 'lead_form', 'faq_list', 'stats', 'testimonials', 'offer_banner', 'map', 'steps', 'columns', 'divider')",
            name=op.f("ck_block_type_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["page_id"], ["page.id"], name=op.f("fk_block_page_id_page"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_block")),
    )
    op.create_index("ix_block_page_id_sort_order", "block", ["page_id", "sort_order"], unique=False)
    op.create_table(
        "faq",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("question", sa.String(length=200), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
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
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_faq_project_id_project"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_faq")),
    )
    op.create_index(
        "ix_faq_project_id_sort_order", "faq", ["project_id", "sort_order"], unique=False
    )
    op.create_table(
        "offer",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.String(length=500), nullable=True),
        sa.Column("image_media_id", sa.UUID(), nullable=True),
        sa.Column("cta_label", sa.String(length=40), nullable=True),
        sa.Column("cta_url", sa.String(length=500), nullable=True),
        sa.Column("terms", sa.String(length=250), nullable=True),
        sa.Column("terms_url", sa.String(length=500), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("placement", sa.String(length=10), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("priority", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("went_live_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_live_announced", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
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
        sa.CheckConstraint(
            "placement IN ('banner', 'home', 'project')", name=op.f("ck_offer_placement_valid")
        ),
        sa.CheckConstraint(
            "(cta_label IS NULL) = (cta_url IS NULL)", name=op.f("ck_offer_cta_label_with_url")
        ),
        sa.CheckConstraint("priority BETWEEN 0 AND 1000", name=op.f("ck_offer_priority_range")),
        sa.CheckConstraint(
            "placement <> 'project' OR project_id IS NOT NULL",
            name=op.f("ck_offer_project_placement_has_project"),
        ),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name=op.f("ck_offer_ends_after_starts"),
        ),
        sa.ForeignKeyConstraint(
            ["image_media_id"], ["media.id"], name=op.f("fk_offer_image_media_id_media")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_offer_project_id_project")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_offer")),
    )
    op.create_index(op.f("ix_offer_image_media_id"), "offer", ["image_media_id"], unique=False)
    op.create_index(op.f("ix_offer_project_id"), "offer", ["project_id"], unique=False)
    op.create_table(
        "testimonial",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("person_name", sa.String(length=80), nullable=False),
        sa.Column("person_detail", sa.String(length=120), nullable=True),
        sa.Column("quote", sa.Text(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=160), nullable=False),
        sa.Column("source_url", sa.String(length=500), nullable=True),
        sa.Column("consent_date", sa.Date(), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=True),
        sa.Column("photo_media_id", sa.UUID(), nullable=True),
        sa.Column("is_visible", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
        sa.CheckConstraint(
            "NOT is_visible OR (consent_date IS NOT NULL AND length(btrim(source)) >= 3)",
            name=op.f("ck_testimonial_visible_needs_consent"),
        ),
        sa.CheckConstraint(
            "rating IS NULL OR rating BETWEEN 1 AND 5", name=op.f("ck_testimonial_rating_range")
        ),
        sa.ForeignKeyConstraint(
            ["photo_media_id"], ["media.id"], name=op.f("fk_testimonial_photo_media_id_media")
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["project.id"],
            name=op.f("fk_testimonial_project_id_project"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_testimonial")),
    )
    op.create_index(
        op.f("ix_testimonial_photo_media_id"), "testimonial", ["photo_media_id"], unique=False
    )
    op.create_index(op.f("ix_testimonial_project_id"), "testimonial", ["project_id"], unique=False)
    op.add_column("media_link", sa.Column("page_id", sa.UUID(), nullable=True))
    op.add_column("media_link", sa.Column("post_id", sa.UUID(), nullable=True))
    op.drop_constraint(op.f("ck_media_link_one_owner"), "media_link", type_="check")
    op.create_check_constraint(
        op.f("ck_media_link_one_owner"), "media_link", f"num_nonnulls({_OWNERS_AFTER}) = 1"
    )
    op.drop_constraint(op.f("ck_media_link_role_valid"), "media_link", type_="check")
    op.create_check_constraint(
        op.f("ck_media_link_role_valid"), "media_link", f"role IN ({_ROLES_AFTER})"
    )
    op.create_index(
        "uq_media_link_page_cover",
        "media_link",
        ["page_id", "role"],
        unique=True,
        postgresql_where=sa.text("is_cover AND page_id IS NOT NULL"),
    )
    op.create_unique_constraint(
        op.f("uq_media_link_page_id_role_media_id"), "media_link", ["page_id", "role", "media_id"]
    )
    op.create_index(
        "uq_media_link_post_cover",
        "media_link",
        ["post_id", "role"],
        unique=True,
        postgresql_where=sa.text("is_cover AND post_id IS NOT NULL"),
    )
    op.create_unique_constraint(
        op.f("uq_media_link_post_id_role_media_id"), "media_link", ["post_id", "role", "media_id"]
    )
    op.create_index(
        "uq_media_link_post_single_role",
        "media_link",
        ["post_id", "role"],
        unique=True,
        postgresql_where=sa.text("role IN ('cover') AND post_id IS NOT NULL"),
    )
    op.create_foreign_key(
        op.f("fk_media_link_post_id_post"),
        "media_link",
        "post",
        ["post_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        op.f("fk_media_link_page_id_page"),
        "media_link",
        "page",
        ["page_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    # Content links can't exist without their columns; the files stay in the library.
    op.execute("DELETE FROM media_link WHERE page_id IS NOT NULL OR post_id IS NOT NULL")
    op.drop_constraint(op.f("ck_media_link_role_valid"), "media_link", type_="check")
    op.create_check_constraint(
        op.f("ck_media_link_role_valid"), "media_link", f"role IN ({_ROLES_BEFORE})"
    )
    op.drop_constraint(op.f("ck_media_link_one_owner"), "media_link", type_="check")
    op.create_check_constraint(
        op.f("ck_media_link_one_owner"), "media_link", f"num_nonnulls({_OWNERS_BEFORE}) = 1"
    )
    op.drop_constraint(op.f("fk_media_link_page_id_page"), "media_link", type_="foreignkey")
    op.drop_constraint(op.f("fk_media_link_post_id_post"), "media_link", type_="foreignkey")
    op.drop_index(
        "uq_media_link_post_single_role",
        table_name="media_link",
        postgresql_where=sa.text("role IN ('cover') AND post_id IS NOT NULL"),
    )
    op.drop_constraint(op.f("uq_media_link_post_id_role_media_id"), "media_link", type_="unique")
    op.drop_index(
        "uq_media_link_post_cover",
        table_name="media_link",
        postgresql_where=sa.text("is_cover AND post_id IS NOT NULL"),
    )
    op.drop_constraint(op.f("uq_media_link_page_id_role_media_id"), "media_link", type_="unique")
    op.drop_index(
        "uq_media_link_page_cover",
        table_name="media_link",
        postgresql_where=sa.text("is_cover AND page_id IS NOT NULL"),
    )
    op.drop_column("media_link", "post_id")
    op.drop_column("media_link", "page_id")
    op.drop_index(op.f("ix_testimonial_project_id"), table_name="testimonial")
    op.drop_index(op.f("ix_testimonial_photo_media_id"), table_name="testimonial")
    op.drop_table("testimonial")
    op.drop_index(op.f("ix_offer_project_id"), table_name="offer")
    op.drop_index(op.f("ix_offer_image_media_id"), table_name="offer")
    op.drop_table("offer")
    op.drop_index("ix_faq_project_id_sort_order", table_name="faq")
    op.drop_table("faq")
    op.drop_index("ix_block_page_id_sort_order", table_name="block")
    op.drop_table("block")
    op.drop_table("redirect")
    op.drop_index("ix_post_publish_state_published_at", table_name="post")
    op.drop_table("post")
    op.drop_table("page")
