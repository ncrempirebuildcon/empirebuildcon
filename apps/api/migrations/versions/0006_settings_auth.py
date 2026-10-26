"""Two-factor sign-in, the sent-mail log, and who published a consent text: `user_two_factor`,
`two_factor_recovery_code`, `sign_in_challenge`, `email_message`; `consent_text.published_by`.

Revision ID: 0006
Revises: 0005
Created: 2026-10-25 17:47:51.200207+00:00

What changes and why: Phase 4 part 5 (handbook/SECURITY.md §1 two-factor, ARCHITECTURE §9
email consumers, D-007 Resend, D-017 consent texts). `user_two_factor` keeps one encrypted TOTP
secret per account with the last accepted time step (replay protection); recovery codes are
stored only as keyed hashes; a `sign_in_challenge` is the 5-minute second step of a sign-in,
stored as the hash of the `__Host-empire_2fa` cookie's token and bound to a network. All three
cascade with their account. `email_message` records which event's email reached which recipient
(a keyed hash, no address or content), unique per event, template and recipient, so a retried
event never sends twice. `consent_text.published_by` (nullable, no foreign key, like
`created_by`) names who first published a version.
The audit log becomes append-only in the database too (part 5 review L8): a row trigger refuses
every UPDATE and DELETE on `audit_log` (platform/models.AuditLog INVARIANT), so the CMS's "the
database refuses edits and deletes" is true. WHY a row trigger and not REVOKE: the API connects
as the table's owner, and owners keep their rights. TRUNCATE is not blocked (row triggers don't
fire on it): the test suite empties tables with TRUNCATE, and only the owner can run it.
Downgrade safe: yes, but it drops every two-factor set-up (accounts sign in with the password
only, as before), the sent-mail log, the consent texts' publisher and the audit-log trigger;
nothing else is touched.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_message",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("template", sa.String(length=40), nullable=False),
        sa.Column("recipient_key", sa.String(length=64), nullable=False),
        sa.Column("transport", sa.String(length=10), nullable=False),
        sa.Column("provider_message_id", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_email_message")),
        sa.UniqueConstraint(
            "event_id",
            "template",
            "recipient_key",
            name=op.f("uq_email_message_event_id_template_recipient_key"),
        ),
    )
    op.create_index(
        "ix_email_message_recipient_template",
        "email_message",
        ["recipient_key", "template", "created_at"],
        unique=False,
    )
    op.create_table(
        "sign_in_challenge",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("step", sa.String(length=8), nullable=False),
        sa.Column("network_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "step IN ('verify', 'setup')", name=op.f("ck_sign_in_challenge_step_valid")
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_sign_in_challenge_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sign_in_challenge")),
        sa.UniqueConstraint("token_hash", name=op.f("uq_sign_in_challenge_token_hash")),
    )
    op.create_index(
        op.f("ix_sign_in_challenge_expires_at"), "sign_in_challenge", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_sign_in_challenge_user_id"), "sign_in_challenge", ["user_id"], unique=False
    )
    op.create_table(
        "two_factor_recovery_code",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_two_factor_recovery_code_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_two_factor_recovery_code")),
        sa.UniqueConstraint("code_hash", name=op.f("uq_two_factor_recovery_code_code_hash")),
    )
    op.create_index(
        op.f("ix_two_factor_recovery_code_user_id"),
        "two_factor_recovery_code",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "user_two_factor",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_step", sa.BigInteger(), nullable=True),
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
            ["user_id"],
            ["app_user.id"],
            name=op.f("fk_user_two_factor_user_id_app_user"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_user_two_factor")),
    )
    op.add_column("consent_text", sa.Column("published_by", sa.UUID(), nullable=True))
    op.execute(
        """
        CREATE FUNCTION audit_log_refuse_change() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % refused', TG_OP
                USING ERRCODE = 'insufficient_privilege';
        END
        $$
        """
    )
    op.execute(
        "CREATE TRIGGER audit_log_append_only BEFORE UPDATE OR DELETE ON audit_log "
        "FOR EACH ROW EXECUTE FUNCTION audit_log_refuse_change()"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_log_append_only ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS audit_log_refuse_change()")
    op.drop_column("consent_text", "published_by")
    op.drop_table("user_two_factor")
    op.drop_index(
        op.f("ix_two_factor_recovery_code_user_id"), table_name="two_factor_recovery_code"
    )
    op.drop_table("two_factor_recovery_code")
    op.drop_index(op.f("ix_sign_in_challenge_user_id"), table_name="sign_in_challenge")
    op.drop_index(op.f("ix_sign_in_challenge_expires_at"), table_name="sign_in_challenge")
    op.drop_table("sign_in_challenge")
    op.drop_index("ix_email_message_recipient_template", table_name="email_message")
    op.drop_table("email_message")
