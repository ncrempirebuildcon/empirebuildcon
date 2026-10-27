"""Full-text search vector on project and trigram indexes on project, locality, and city.

Revision ID: 0007
Revises: 0006
Created: 2026-10-26 19:30:00.000000+00:00

What changes and why: Phase 5 task 5.1 (handbook/ARCHITECTURE.md §13, §14). Adds a generated
`search_vector` tsvector column on `project` indexing name and tagline, indexed with GIN, plus
`pg_trgm` GIN indexes on `project.name`, `locality.name`, and `city.name` for typo-tolerant
catalogue search.
Downgrade safe: drops the added indexes and the `search_vector` column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "project",
        sa.Column(
            "search_vector",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('english', coalesce(name, '') || ' ' || coalesce(tagline, ''))",
                persisted=True,
            ),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_project_search_vector",
        "project",
        ["search_vector"],
        unique=False,
        postgresql_using="gin",
    )
    op.create_index(
        "ix_project_name_trgm",
        "project",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_locality_name_trgm",
        "locality",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.create_index(
        "ix_city_name_trgm",
        "city",
        ["name"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )


def downgrade() -> None:
    op.drop_index(
        "ix_city_name_trgm",
        table_name="city",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_locality_name_trgm",
        table_name="locality",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_index(
        "ix_project_name_trgm",
        table_name="project",
        postgresql_using="gin",
        postgresql_ops={"name": "gin_trgm_ops"},
    )
    op.drop_index("ix_project_search_vector", table_name="project", postgresql_using="gin")
    op.drop_column("project", "search_vector")
