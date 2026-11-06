"""Database engine, sessions and the declarative base shared by every module's models.

Collaborators: models in users/, site_settings/, integrations/, platform/; migrations/env.py.
Implements: ARCHITECTURE §6 conventions (UUID v7 ids, timestamptz in UTC), D-010.

WHY sync SQLAlchemy: traffic is small (a handful of staff, hundreds of leads a month), FastAPI
runs plain `def` endpoints in a thread pool, and one sync code path is easier for the next
developer to read and test than mixing sync (Alembic, CLI) and async.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import datetime
from functools import lru_cache
from typing import Any, Final

from sqlalchemy import DateTime, Engine, MetaData, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from empire_api.config import get_settings
from empire_api.ids import new_id

# DO NOT CHANGE: constraint names are part of every migration. Changing this convention makes
# Alembic see "new" constraints everywhere and generate a destructive migration.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    """Declarative base: typed columns, JSONB for dicts, timestamptz for datetimes."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {  # noqa: RUF012 — SQLAlchemy reads this class attribute
        dict[str, Any]: JSONB,
        datetime: DateTime(timezone=True),
        uuid.UUID: UUID(as_uuid=True),
    }


def uuid_pk() -> Mapped[uuid.UUID]:
    """A UUID v7 primary key generated in Python (so the id is known before the INSERT)."""
    return mapped_column(primary_key=True, default=new_id)


def created_at_column() -> Mapped[datetime]:
    return mapped_column(server_default=func.now(), nullable=False)


# Per process: at most 4 connections (2 + 2 overflow); each write takes milliseconds.
SIDE_POOL_SIZE: Final = 2


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    """The process-wide engine. Tests dispose and clear it when they switch databases."""
    settings = get_settings()
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        # SECURITY (L2 security review): SQL errors otherwise print the bound values
        # ("[parameters: {'phone': '+91…'}]"), which would put lead data in logs and Sentry.
        hide_parameters=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_pool_size,
        # WHY: Neon's pooled endpoint is PgBouncer in transaction mode, which breaks
        # server-side prepared statements. psycopg prepares nothing when this is None.
        connect_args={"prepare_threshold": None},
    )
    return engine


@lru_cache(maxsize=1)
def get_side_engine() -> Engine:
    """A small second pool for the short writes that must commit on their own connection while a
    request's session is open (rate-limit counters, the sent-email record).

    WHY (L7a load test): with one pool, every request held its session's connection and then
    waited for a second one for the rate limit. Ten enquiries at once used up the pool, each
    waited for the others, and all of them failed after 30 s (sqlalchemy TimeoutError).
    INVARIANT: code using this engine never waits for the main pool while holding one of these
    connections, so the two pools can't wait on each other.
    """
    settings = get_settings()
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        hide_parameters=True,  # SECURITY: as get_engine
        pool_size=SIDE_POOL_SIZE,
        max_overflow=SIDE_POOL_SIZE,
        pool_timeout=10,
        connect_args={"prepare_threshold": None},  # WHY: as get_engine (PgBouncer)
    )


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request. Handlers commit explicitly.

    INVARIANT: anything not committed by the handler is rolled back when the request ends,
    so a handler that raises never leaves half-written rows behind.
    """
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def rows_affected(result: Any) -> int:
    """`rowcount` of an UPDATE/DELETE result (typed as a plain Result by SQLAlchemy's stubs)."""
    return int(getattr(result, "rowcount", 0) or 0)


def reset_engine() -> None:
    """Dispose pooled connections and forget the cached engine (tests, CLI env switches)."""
    if get_engine.cache_info().currsize:
        get_engine().dispose()
    if get_side_engine.cache_info().currsize:
        get_side_engine().dispose()
    get_engine.cache_clear()
    get_side_engine.cache_clear()
    get_sessionmaker.cache_clear()
