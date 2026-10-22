"""The migrations create exactly what the models describe (no drift)."""

from __future__ import annotations

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import text

from empire_api.db import get_engine
from empire_api.models import Base


def test_models_match_the_migrated_database() -> None:
    with get_engine().connect() as conn:
        context = MigrationContext.configure(conn, opts={"compare_type": True})
        assert compare_metadata(context, Base.metadata) == []


def test_trigram_extension_is_installed() -> None:
    with get_engine().connect() as conn:
        names = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert "pg_trgm" in names
