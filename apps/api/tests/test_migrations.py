"""The migrations create exactly what the models describe (no drift)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
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


def test_migration_0007_upgrade_downgrade_cycle() -> None:
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    cfg = Config(str(ini_path))

    with get_engine().connect() as conn:
        col_names = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'project'"
                )
            ).scalars()
        )
        assert "search_vector" in col_names

    # Downgrade to 0006 (drops search_vector and trigram indexes)
    command.downgrade(cfg, "0006")

    with get_engine().connect() as conn:
        col_names = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'project'"
                )
            ).scalars()
        )
        assert "search_vector" not in col_names

    # Upgrade back to head (recreates search_vector and indexes)
    command.upgrade(cfg, "head")

    with get_engine().connect() as conn:
        col_names = set(
            conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'project'"
                )
            ).scalars()
        )
        assert "search_vector" in col_names
