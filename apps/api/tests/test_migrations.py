"""The migrations create exactly what the models describe (no drift)."""

from __future__ import annotations

import uuid
from pathlib import Path

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from empire_api.config import get_settings
from empire_api.db import get_engine
from empire_api.models import Base, include_object


def test_models_match_the_migrated_database() -> None:
    with get_engine().connect() as conn:
        context = MigrationContext.configure(
            conn, opts={"compare_type": True, "include_object": include_object}
        )
        assert compare_metadata(context, Base.metadata) == []


def test_trigram_extension_is_installed() -> None:
    with get_engine().connect() as conn:
        names = set(conn.execute(text("SELECT extname FROM pg_extension")).scalars())
    assert "pg_trgm" in names


def test_migration_0007_upgrade_downgrade_cycle() -> None:
    """Part B Item 4: Run migration up/down cycle on an isolated throwaway database."""
    base_url = make_url(get_settings().database_url)
    db_name = f"empire_throwaway_{uuid.uuid4().hex[:8]}"

    # Connect with AUTOCOMMIT isolation to create and drop database
    admin_engine = create_engine(base_url, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{db_name}"'))

    throwaway_url = base_url.set(database=db_name)
    url_str = throwaway_url.render_as_string(hide_password=False)
    throwaway_engine = create_engine(url_str)
    ini_path = Path(__file__).resolve().parents[1] / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("sqlalchemy.url", url_str.replace("%", "%%"))

    try:
        # 1. Upgrade throwaway db to head
        command.upgrade(cfg, "head")

        with throwaway_engine.connect() as conn:
            col_names = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'project'"
                    )
                ).scalars()
            )
            assert "search_vector" in col_names

        # 2. Downgrade to 0006 (drops search_vector and trigram indexes)
        command.downgrade(cfg, "0006")

        with throwaway_engine.connect() as conn:
            col_names = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'project'"
                    )
                ).scalars()
            )
            assert "search_vector" not in col_names
            # 0008 (D-059) went down too
            assert conn.scalar(text("SELECT to_regclass('public.ai_usage_day')")) is None
            assert conn.scalar(text("SELECT to_regclass('public.knowledge_chunk')")) is None

        # 3. Upgrade back to head (recreates search_vector and indexes)
        command.upgrade(cfg, "head")
        with throwaway_engine.connect() as conn:
            assert conn.scalar(text("SELECT to_regclass('public.ai_usage_day')")) is not None

        with throwaway_engine.connect() as conn:
            col_names = set(
                conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'project'"
                    )
                ).scalars()
            )
            assert "search_vector" in col_names
    finally:
        throwaway_engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin_engine.dispose()


def test_knowledge_table_follows_pgvector() -> None:
    """Migration 0008 (D-059): the AI table exists exactly where pgvector does."""
    with get_engine().connect() as conn:
        has_vector = bool(conn.scalar(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")))
        table = conn.scalar(text("SELECT to_regclass('public.knowledge_chunk') IS NOT NULL"))
        usage = conn.scalar(text("SELECT to_regclass('public.ai_usage_day') IS NOT NULL"))
    assert table is has_vector
    assert usage is True
