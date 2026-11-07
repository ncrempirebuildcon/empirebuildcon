"""AI assistant: the knowledge index and daily usage counts (Phase 7 task 7.1, D-059).

Revision ID: 0008
Revises: 0007
Created: 2026-11-07 18:30:00.000000+00:00

What changes and why: `ai_usage_day` holds counts only (no message text, ever). `knowledge_chunk`
holds text from live public content with a 1024-dimension embedding (bge-m3) and an HNSW cosine
index. It needs pgvector, so it is created only where the extension is installed (Neon, CI, the
Docker database). Elsewhere the assistant simply stays unavailable (`ai.store.available`).
Downgrade safe: drops both tables; they hold no source data (the index is rebuilt from content).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ai_usage_day",
        sa.Column("day", sa.Date(), primary_key=True),
        sa.Column("answers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("no_answer", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("busy", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("neurons", sa.Numeric(10, 2), nullable=False, server_default="0"),
    )
    # The same permission-aware attempt as 0001, for databases created before that fix.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
                BEGIN
                    CREATE EXTENSION IF NOT EXISTS vector;
                EXCEPTION WHEN insufficient_privilege THEN
                    RAISE NOTICE 'pgvector is available but this user cannot create it';
                END;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
                CREATE TABLE knowledge_chunk (
                    id uuid PRIMARY KEY,
                    source_type varchar(20) NOT NULL,
                    source_id uuid NOT NULL,
                    url varchar(300) NOT NULL,
                    title varchar(200) NOT NULL,
                    locale varchar(8) NOT NULL DEFAULT 'en',
                    position integer NOT NULL,
                    body text NOT NULL,
                    tokens integer NOT NULL,
                    content_hash varchar(64) NOT NULL,
                    embedding vector(1024) NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT now(),
                    CONSTRAINT ck_knowledge_chunk_source_type CHECK (
                        source_type IN ('project', 'page', 'post', 'faq')
                    )
                );
                -- INVARIANT: one row per position of an item (the indexer also locks per item).
                CREATE UNIQUE INDEX uq_knowledge_chunk_source
                    ON knowledge_chunk (source_type, source_id, position);
                -- HNSW needs pgvector 0.5 or newer; without it, search scans (a few hundred rows).
                IF (SELECT string_to_array(extversion, '.')::int[] FROM pg_extension
                    WHERE extname = 'vector') >= ARRAY[0, 5] THEN
                    CREATE INDEX ix_knowledge_chunk_embedding ON knowledge_chunk
                        USING hnsw (embedding vector_cosine_ops);
                END IF;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS knowledge_chunk")
    op.drop_table("ai_usage_day")
