"""Leads: consent texts (`consent_text`, owned by the content module), and `lead`,
`lead_consent`, `lead_note`, `lead_activity` and `site_visit` (the leads module).

Revision ID: 0004
Revises: 0003
Created: 2026-10-23 10:47:31.234529+00:00

What changes and why: Phase 4 part 3 (handbook/ARCHITECTURE.md §6, §8; SECURITY.md §8; D-016,
D-017). `consent_text` keeps every version of the wording a form shows; a partial unique index
allows one current text per kind, and a CHECK keeps a current text published. `lead` has the
four indexes ARCHITECTURE §6 names (created_at desc; status + created_at desc; owner +
created_at desc; phone) plus one on project_id for its foreign key; `reference` is unique.
CHECKs tie `lost` to a reason code from a fixed list (staff's own words go in
`lost_reason_note`, which only a lost lead has) and keep BHK whole or half from 0.5 to 20.
`lead.project_id` and `site_visit.project_id` are RESTRICT, so a project with leads can't be
deleted (it is archived instead). `lead_consent` records the text id, version and label shown
(or staff's note for manual leads), one row per kind and lead. `lead_activity` is the timeline
(ids, stages, times, and the lost-reason note, which erasure replaces). No existing table
changes.
Downgrade safe: only before real leads exist. It drops the six tables with their rows,
including consent records that DPDP expects to be kept, so never run it on production data.
Earlier tables are untouched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "consent_text",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("checkbox_label", sa.String(length=300), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_current", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            "kind IN ('lead_form', 'marketing', 'brochure', 'cookies', 'chat')",
            name=op.f("ck_consent_text_kind_valid"),
        ),
        sa.CheckConstraint(
            "NOT is_current OR published_at IS NOT NULL",
            name=op.f("ck_consent_text_current_is_published"),
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_consent_text_version_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consent_text")),
        sa.UniqueConstraint("kind", "version", name=op.f("uq_consent_text_kind_version")),
    )
    op.create_index(
        "uq_consent_text_current_kind",
        "consent_text",
        ["kind"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_table(
        "lead",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("reference", sa.String(length=9), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("phone_e164", sa.String(length=16), nullable=False),
        sa.Column("email", sa.String(length=200), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("project_id", sa.UUID(), nullable=True),
        sa.Column("configuration_id", sa.UUID(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=12), server_default=sa.text("'new'"), nullable=False),
        sa.Column("lost_reason", sa.String(length=20), nullable=True),
        sa.Column("lost_reason_note", sa.String(length=200), nullable=True),
        sa.Column("owner_user_id", sa.UUID(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("page_url", sa.String(length=1000), nullable=True),
        sa.Column("referrer", sa.String(length=1000), nullable=True),
        sa.Column("utm_source", sa.String(length=200), nullable=True),
        sa.Column("utm_medium", sa.String(length=200), nullable=True),
        sa.Column("utm_campaign", sa.String(length=200), nullable=True),
        sa.Column("utm_term", sa.String(length=200), nullable=True),
        sa.Column("utm_content", sa.String(length=200), nullable=True),
        sa.Column("gclid", sa.String(length=500), nullable=True),
        sa.Column("gbraid", sa.String(length=500), nullable=True),
        sa.Column("wbraid", sa.String(length=500), nullable=True),
        sa.Column("fbclid", sa.String(length=500), nullable=True),
        sa.Column("msclkid", sa.String(length=500), nullable=True),
        sa.Column("preferred_bhk", sa.Numeric(precision=3, scale=1), nullable=True),
        sa.Column("budget_max_inr", sa.BigInteger(), nullable=True),
        sa.Column("preferred_contact_time", sa.String(length=60), nullable=True),
        sa.Column("language", sa.String(length=2), server_default=sa.text("'en'"), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("is_spam", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("duplicate_of_id", sa.UUID(), nullable=True),
        sa.Column("erased_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
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
        sa.CheckConstraint(
            "(status = 'lost') = (lost_reason IS NOT NULL)", name=op.f("ck_lead_lost_has_reason")
        ),
        sa.CheckConstraint("language IN ('en', 'hi')", name=op.f("ck_lead_language_valid")),
        sa.CheckConstraint(
            "source IN ('project_form', 'contact_form', 'brochure', 'site_visit', 'campaign', 'chat', 'whatsapp', 'phone', 'manual')",
            name=op.f("ck_lead_source_valid"),
        ),
        sa.CheckConstraint(
            "status IN ('new', 'contacted', 'site_visit', 'negotiation', 'booked', 'lost')",
            name=op.f("ck_lead_status_valid"),
        ),
        sa.CheckConstraint(
            "COALESCE(budget_max_inr, 0) >= 0", name=op.f("ck_lead_budget_not_negative")
        ),
        sa.CheckConstraint("duplicate_of_id <> id", name=op.f("ck_lead_not_own_duplicate")),
        sa.CheckConstraint(
            "preferred_bhk BETWEEN 0.5 AND 20 AND mod(preferred_bhk * 2, 1) = 0",
            name=op.f("ck_lead_preferred_bhk_half_steps"),
        ),
        sa.CheckConstraint(
            "lost_reason IN ('bought_elsewhere', 'budget', 'location', 'not_reachable', "
            "'not_looking', 'duplicate', 'other')",
            name=op.f("ck_lead_lost_reason_valid"),
        ),
        sa.CheckConstraint(
            "lost_reason_note IS NULL OR status = 'lost'",
            name=op.f("ck_lead_lost_reason_note_only_lost"),
        ),
        sa.ForeignKeyConstraint(
            ["configuration_id"],
            ["configuration.id"],
            name=op.f("fk_lead_configuration_id_configuration"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["duplicate_of_id"],
            ["lead.id"],
            name=op.f("fk_lead_duplicate_of_id_lead"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["app_user.id"],
            name=op.f("fk_lead_owner_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_lead_project_id_project")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead")),
        sa.UniqueConstraint("reference", name=op.f("uq_lead_reference")),
    )
    op.create_index(
        "ix_lead_created_at", "lead", [sa.literal_column("created_at DESC")], unique=False
    )
    op.create_index(
        "ix_lead_owner_user_id_created_at",
        "lead",
        ["owner_user_id", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_index("ix_lead_phone_e164", "lead", ["phone_e164"], unique=False)
    op.create_index(op.f("ix_lead_project_id"), "lead", ["project_id"], unique=False)
    op.create_index(
        "ix_lead_status_created_at",
        "lead",
        ["status", sa.literal_column("created_at DESC")],
        unique=False,
    )
    op.create_table(
        "lead_activity",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column(
            "data",
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
        sa.CheckConstraint(
            "kind IN ('created', 'status_changed', 'assigned', 'note_added', 'visit_requested', 'visit_updated', 'alert_sent', 'webhook_sent', 'exported', 'read', 'unread', 'details_changed', 'spam_marked', 'duplicate_linked', 'erased')",
            name=op.f("ck_lead_activity_kind_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["lead.id"], name=op.f("fk_lead_activity_lead_id_lead"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_activity")),
    )
    op.create_index(
        "ix_lead_activity_lead_id_created_at",
        "lead_activity",
        ["lead_id", "created_at"],
        unique=False,
    )
    op.create_table(
        "lead_consent",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("consent_text_id", sa.UUID(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("page_url", sa.String(length=1000), nullable=True),
        sa.Column("checkbox_label", sa.String(length=300), nullable=True),
        sa.Column("consent_note", sa.String(length=500), nullable=True),
        sa.CheckConstraint(
            "kind IN ('lead_form', 'marketing')", name=op.f("ck_lead_consent_kind_valid")
        ),
        sa.CheckConstraint(
            "(consent_text_id IS NULL) = (version IS NULL)",
            name=op.f("ck_lead_consent_text_has_version"),
        ),
        sa.CheckConstraint(
            "consent_text_id IS NOT NULL OR consent_note IS NOT NULL",
            name=op.f("ck_lead_consent_text_or_note"),
        ),
        sa.ForeignKeyConstraint(
            ["consent_text_id"],
            ["consent_text.id"],
            name=op.f("fk_lead_consent_consent_text_id_consent_text"),
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["lead.id"], name=op.f("fk_lead_consent_lead_id_lead"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_consent")),
        sa.UniqueConstraint("lead_id", "kind", name=op.f("uq_lead_consent_lead_id_kind")),
    )
    op.create_index(
        op.f("ix_lead_consent_consent_text_id"), "lead_consent", ["consent_text_id"], unique=False
    )
    op.create_table(
        "lead_note",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["lead.id"], name=op.f("fk_lead_note_lead_id_lead"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_lead_note")),
    )
    op.create_index(
        "ix_lead_note_lead_id_created_at", "lead_note", ["lead_id", "created_at"], unique=False
    )
    op.create_table(
        "site_visit",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("lead_id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("preferred_date", sa.Date(), nullable=False),
        sa.Column("preferred_slot", sa.String(length=10), nullable=False),
        sa.Column("confirmed_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=12), server_default=sa.text("'requested'"), nullable=False
        ),
        sa.Column("handled_by_user_id", sa.UUID(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_sample", sa.Boolean(), server_default=sa.text("false"), nullable=False),
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
            "preferred_slot IN ('morning', 'afternoon', 'evening')",
            name=op.f("ck_site_visit_preferred_slot_valid"),
        ),
        sa.CheckConstraint(
            "status <> 'confirmed' OR confirmed_for IS NOT NULL",
            name=op.f("ck_site_visit_confirmed_has_time"),
        ),
        sa.CheckConstraint(
            "status IN ('requested', 'confirmed', 'completed', 'no_show', 'cancelled')",
            name=op.f("ck_site_visit_status_valid"),
        ),
        sa.ForeignKeyConstraint(
            ["handled_by_user_id"],
            ["app_user.id"],
            name=op.f("fk_site_visit_handled_by_user_id_app_user"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["lead_id"], ["lead.id"], name=op.f("fk_site_visit_lead_id_lead"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["project_id"], ["project.id"], name=op.f("fk_site_visit_project_id_project")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_site_visit")),
    )
    op.create_index(
        op.f("ix_site_visit_confirmed_for"), "site_visit", ["confirmed_for"], unique=False
    )
    op.create_index(op.f("ix_site_visit_lead_id"), "site_visit", ["lead_id"], unique=False)
    op.create_index(
        op.f("ix_site_visit_preferred_date"), "site_visit", ["preferred_date"], unique=False
    )
    op.create_index(op.f("ix_site_visit_project_id"), "site_visit", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_site_visit_project_id"), table_name="site_visit")
    op.drop_index(op.f("ix_site_visit_preferred_date"), table_name="site_visit")
    op.drop_index(op.f("ix_site_visit_lead_id"), table_name="site_visit")
    op.drop_index(op.f("ix_site_visit_confirmed_for"), table_name="site_visit")
    op.drop_table("site_visit")
    op.drop_index("ix_lead_note_lead_id_created_at", table_name="lead_note")
    op.drop_table("lead_note")
    op.drop_index(op.f("ix_lead_consent_consent_text_id"), table_name="lead_consent")
    op.drop_table("lead_consent")
    op.drop_index("ix_lead_activity_lead_id_created_at", table_name="lead_activity")
    op.drop_table("lead_activity")
    op.drop_index("ix_lead_status_created_at", table_name="lead")
    op.drop_index(op.f("ix_lead_project_id"), table_name="lead")
    op.drop_index("ix_lead_phone_e164", table_name="lead")
    op.drop_index("ix_lead_owner_user_id_created_at", table_name="lead")
    op.drop_index("ix_lead_created_at", table_name="lead")
    op.drop_table("lead")
    op.drop_index(
        "uq_consent_text_current_kind",
        table_name="consent_text",
        postgresql_where=sa.text("is_current"),
    )
    op.drop_table("consent_text")
