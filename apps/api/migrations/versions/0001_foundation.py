"""Foundation: staff accounts, sessions, reset tokens, audit log, outbox, rate limits,
feature flags and settings, plus the pg_trgm (and, where available, vector) extensions.

Revision ID: 0001
Revises: (none)
Created: 2026-10-22 09:42:53.935958+00:00

What changes and why: the Phase 3 platform tables (handbook/ARCHITECTURE.md §6, §9–11).
Downgrade safe: only on an empty database. It drops every table this creates.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    # WHY: pgvector is enabled from the first migration so Phase 7 needs no database change
    # (D-013). Neon and CI's database image have it; a developer's local PostgreSQL may not,
    # so we only create it when the server offers it.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
                CREATE EXTENSION IF NOT EXISTS vector;
            END IF;
        END
        $$;
        """
    )
    op.create_table(
        "app_user",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
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
            "role IN ('super_admin', 'admin', 'sales', 'marketing', 'content_editor')",
            name=op.f("ck_app_user_role_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_app_user")),
    )
    op.create_index(
        "uq_app_user_email_lower", "app_user", [sa.literal_column("lower(email)")], unique=True
    )
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("actor_user_id", sa.UUID(), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=64), nullable=False),
        sa.Column(
            "changes",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_audit_log")),
    )
    op.create_index(
        op.f("ix_audit_log_actor_user_id"), "audit_log", ["actor_user_id"], unique=False
    )
    op.create_index(
        "ix_audit_log_created_at", "audit_log", [sa.literal_column("created_at DESC")], unique=False
    )
    op.create_index("ix_audit_log_entity", "audit_log", ["entity_type", "entity_id"], unique=False)
    op.create_table(
        "feature_flag",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("is_locked", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_feature_flag")),
    )
    op.create_table(
        "outbox_event",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=True), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("type", sa.String(length=80), nullable=False),
        sa.Column("aggregate_type", sa.String(length=40), nullable=False),
        sa.Column("aggregate_id", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.UUID(), nullable=True),
        sa.Column(
            "contains_personal_data", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(length=16), server_default=sa.text("'pending'"), nullable=False
        ),
        sa.Column("attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "available_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'dead')",
            name=op.f("ck_outbox_event_status_valid"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_outbox_event")),
        sa.UniqueConstraint("event_id", name=op.f("uq_outbox_event_event_id")),
    )
    op.create_index(
        "ix_outbox_event_status_available_at",
        "outbox_event",
        ["status", "available_at"],
        unique=False,
    )
    op.create_table(
        "rate_limit_bucket",
        sa.Column("key", sa.String(length=200), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", "window_start", name=op.f("pk_rate_limit_bucket")),
    )
    op.create_index(
        op.f("ix_rate_limit_bucket_expires_at"), "rate_limit_bucket", ["expires_at"], unique=False
    )
    op.create_table(
        "setting",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column(
            "value",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_setting")),
    )
    op.create_table(
        "password_reset_token",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "purpose IN ('reset', 'setup')", name=op.f("ck_password_reset_token_purpose_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_password_reset_token_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_password_reset_token")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_password_reset_token_token_hash")),
    )
    op.create_index(
        op.f("ix_password_reset_token_expires_at"),
        "password_reset_token",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_password_reset_token_user_id"), "password_reset_token", ["user_id"], unique=False
    )
    op.create_table(
        "user_session",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_session_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_session")),
    )
    op.create_index(
        op.f("ix_user_session_expires_at"), "user_session", ["expires_at"], unique=False
    )
    op.create_index(op.f("ix_user_session_user_id"), "user_session", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_user_session_user_id"), table_name="user_session")
    op.drop_index(op.f("ix_user_session_expires_at"), table_name="user_session")
    op.drop_table("user_session")
    op.drop_index(op.f("ix_password_reset_token_user_id"), table_name="password_reset_token")
    op.drop_index(op.f("ix_password_reset_token_expires_at"), table_name="password_reset_token")
    op.drop_table("password_reset_token")
    op.drop_table("setting")
    op.drop_index(op.f("ix_rate_limit_bucket_expires_at"), table_name="rate_limit_bucket")
    op.drop_table("rate_limit_bucket")
    op.drop_index("ix_outbox_event_status_available_at", table_name="outbox_event")
    op.drop_table("outbox_event")
    op.drop_table("feature_flag")
    op.drop_index("ix_audit_log_entity", table_name="audit_log")
    op.drop_index("ix_audit_log_created_at", table_name="audit_log")
    op.drop_index(op.f("ix_audit_log_actor_user_id"), table_name="audit_log")
    op.drop_table("audit_log")
    op.drop_index("uq_app_user_email_lower", table_name="app_user")
    op.drop_table("app_user")
    op.execute("DROP EXTENSION IF EXISTS vector")
    op.execute("DROP EXTENSION IF EXISTS pg_trgm")
