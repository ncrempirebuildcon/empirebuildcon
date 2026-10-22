"""Shared test fixtures: a real PostgreSQL test database, the app, and signed-in clients.

How it works:
  1. Before anything imports the app, point settings at the test database (TEST_DATABASE_URL,
     default empire_test on localhost) with APP_ENV=test and throwaway secrets.
  2. Once per test session: drop and recreate the `public` schema, then run Alembic to head.
     The migration itself is under test, not `create_all()`.
  3. Before every test: truncate every table (fast, and works even though app code commits),
     then seed the feature flags.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest

os.environ["APP_ENV"] = "test"
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://empire:empire@localhost:5432/empire_test"
)
os.environ["SESSION_SECRET"] = "test-session-secret-0123456789-abcdefghijklmnop"
os.environ["INTERNAL_API_KEY"] = "test-internal-key-0123456789-abcdefghijklmnop"
os.environ["IP_HASH_SALT"] = "test-ip-salt-0123456789-abcdefghijklmnop"
os.environ["DATA_ENCRYPTION_KEY"] = "test-data-key"
os.environ["CORS_ALLOWED_ORIGINS"] = ""
os.environ["EDGE_PROXY_KEY"] = ""

# The imports below come after the environment on purpose: settings are read at import time.
import httpx
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.db import get_engine, get_sessionmaker, reset_engine
from empire_api.main import create_app
from empire_api.projects import blockers, maps, routes_catalogue
from empire_api.site_settings.flags import seed_flags
from empire_api.users import passwords
from empire_api.users.models import User

API_ROOT = Path(__file__).resolve().parents[1]
GOOD_PASSWORD = "correct horse battery staple"
TABLES = (
    "app_user",
    "user_session",
    "password_reset_token",
    "audit_log",
    "outbox_event",
    "rate_limit_bucket",
    "feature_flag",
    "setting",
    "project_amenity",
    "payment_plan",
    "construction_update",
    "location_advantage",
    "specification",
    "configuration",
    "tower",
    "project",
    "amenity",
    "locality",
    "city",
)


@pytest.fixture(scope="session", autouse=True)
def database() -> Iterator[None]:
    get_settings.cache_clear()
    reset_engine()
    with get_engine().begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "migrations"))
    command.upgrade(config, "head")
    yield
    reset_engine()


@pytest.fixture(autouse=True)
def clean_tables(database: None) -> None:
    with get_engine().begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(TABLES)} RESTART IDENTITY CASCADE"))
    with get_sessionmaker()() as db:
        seed_flags(db)
        db.commit()


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach the network: the maps resolver's real HTTP client is replaced by one
    that fails the test. Tests that follow short links inject a fake client instead."""

    def refuse() -> httpx.Client:
        raise AssertionError("A test tried to reach the network through the maps resolver.")

    monkeypatch.setattr(maps, "default_client", refuse)
    monkeypatch.setattr(routes_catalogue, "resolver_client", refuse)


@pytest.fixture
def qr_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend every project has its RERA QR image (the QR upload arrives with media, part 2)."""
    monkeypatch.setattr(blockers, "rera_qr_present", lambda db, project: True)


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    # https so the cookie jar sends the Secure `__Host-` session cookie back.
    with TestClient(app, base_url="https://testserver", follow_redirects=False) as c:
        yield c


@pytest.fixture
def db() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


def make_user(
    role: str = "super_admin",
    *,
    email: str | None = None,
    password: str | None = GOOD_PASSWORD,
    name: str = "Test Person",
    is_active: bool = True,
) -> User:
    """Insert a staff account directly (tests only; the app itself never takes a password)."""
    email = email or f"{role}@example.com"
    with get_sessionmaker()() as session:
        user = User(
            email=email.lower(),
            name=name,
            role=role,
            is_active=is_active,
            password_hash=passwords.hash_password(password) if password else None,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        session.expunge(user)
        return user


@dataclass
class SignedIn:
    client: TestClient
    user: User
    csrf: str

    def headers(self) -> dict[str, str]:
        return {"X-CSRF-Token": self.csrf}


def sign_in(client: TestClient, user: User, password: str = GOOD_PASSWORD) -> SignedIn:
    response = client.post("/api/v1/auth/login", json={"email": user.email, "password": password})
    assert response.status_code == 200, response.text
    return SignedIn(client=client, user=user, csrf=response.json()["csrf_token"])


@pytest.fixture
def owner(client: TestClient) -> SignedIn:
    return sign_in(client, make_user("super_admin", email="owner@example.com"))


def new_client(app: FastAPI) -> TestClient:
    return TestClient(app, base_url="https://testserver", follow_redirects=False)
