"""Shared test fixtures: a real PostgreSQL test database, the app, and signed-in clients.

How it works:
  1. Before anything imports the app, point settings at the test database (TEST_DATABASE_URL,
     default empire_test on localhost) with APP_ENV=test and throwaway secrets.
  2. Once per test session: drop and recreate the `public` schema, then run Alembic to head.
     The migration itself is under test, not `create_all()`.
  3. Before every test: truncate every table (fast, and works even though app code commits),
     then seed the feature flags.
  4. Media: the fake store (no CLOUDINARY_URL), writing to a temporary MEDIA_DEV_DIR; the
     Cloudinary SDK's HTTP clients fail any test that would reach the network.
  5. Email: the dev transport (no EMAIL_API_KEY), writing to a temporary MAIL_DEV_DIR that is
     emptied before every test; httpx calls to Resend fail any test that doesn't mock them.
"""

from __future__ import annotations

import os
import shutil
import tempfile
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
os.environ.pop("CLOUDINARY_URL", None)
os.environ.pop("MEDIA_STORE", None)
os.environ["MEDIA_DEV_DIR"] = tempfile.mkdtemp(prefix="empire-media-test-")
os.environ.pop("EMAIL_API_KEY", None)
os.environ.pop("EMAIL_FROM", None)
os.environ.pop("EMAIL_TRANSPORT", None)
os.environ["MAIL_DEV_DIR"] = tempfile.mkdtemp(prefix="empire-mail-test-")

# The imports below come after the environment on purpose: settings are read at import time.
import cloudinary.api_client.call_api
import cloudinary.uploader
import httpx
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content.consent import seed_consent_texts
from empire_api.content.models import ConsentText
from empire_api.db import get_engine, get_sessionmaker, reset_engine
from empire_api.leads import intake as lead_intake
from empire_api.mail import resend
from empire_api.mail.transport import get_transport
from empire_api.main import create_app
from empire_api.media.store import get_store
from empire_api.projects import blockers, maps, routes_catalogue
from empire_api.site_settings.flags import seed_flags
from empire_api.users import passwords
from empire_api.users.models import User

API_ROOT = Path(__file__).resolve().parents[1]
GOOD_PASSWORD = "correct horse battery staple"
TABLES = (
    "email_message",
    "sign_in_challenge",
    "two_factor_recovery_code",
    "user_two_factor",
    "block",
    "page",
    "post",
    "faq",
    "offer",
    "testimonial",
    "redirect",
    "lead_activity",
    "lead_note",
    "lead_consent",
    "site_visit",
    "lead",
    "consent_text",
    "media_link",
    "upload_intent",
    "media",
    "app_user",
    "user_session",
    "password_reset_token",
    "audit_log",
    "outbox_event",
    "ai_usage_day",
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
    get_store.cache_clear()
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
        # Only where pgvector is installed (migration 0008); CI's database has it.
        if conn.scalar(text("SELECT to_regclass('public.knowledge_chunk') IS NOT NULL")):
            conn.execute(text("TRUNCATE knowledge_chunk"))
    with get_sessionmaker()() as db:
        seed_flags(db)
        db.commit()
    get_transport.cache_clear()
    shutil.rmtree(os.environ["MAIL_DEV_DIR"], ignore_errors=True)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never reach the network: the maps resolver's real HTTP client is replaced by one
    that fails the test. Tests that follow short links inject a fake client instead."""

    def refuse() -> httpx.Client:
        raise AssertionError("A test tried to reach the network through the maps resolver.")

    monkeypatch.setattr(maps, "default_client", refuse)
    monkeypatch.setattr(routes_catalogue, "resolver_client", refuse)

    def no_cloudinary(*args: object, **kwargs: object) -> None:
        raise AssertionError("A test tried to reach Cloudinary through its SDK.")

    monkeypatch.setattr(cloudinary.uploader._http, "request", no_cloudinary)
    monkeypatch.setattr(cloudinary.api_client.call_api._http, "request", no_cloudinary)

    def no_resend() -> httpx.Client:
        raise AssertionError("A test tried to reach Resend; pass a mocked client instead.")

    monkeypatch.setattr(resend, "_default_client", no_resend)


@pytest.fixture
def qr_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pretend every project has its RERA QR image, for publish tests that aren't about media.
    tests/test_media_projects.py uploads a real QR through the fake store instead."""
    monkeypatch.setattr(blockers, "projects_with_rera_qr", lambda db, ids: set(ids))


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


# --- Leads (Phase 4 part 3; helpers in tests/leads_support.py) -------------------------------


@pytest.fixture
def texts() -> dict[str, dict[str, object]]:
    """The draft lead-form and marketing texts, current (as `empire-api seed` in dev/test)."""
    with get_sessionmaker()() as session:
        seed_consent_texts(session)
        session.commit()
        rows = session.scalars(select(ConsentText).where(ConsentText.is_current.is_(True))).all()
        return {row.kind: {"id": str(row.id), "version": row.version} for row in rows}


@pytest.fixture
def intake_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    """Lift the public intake limit (all TestClient calls share one IP)."""
    monkeypatch.setattr(lead_intake, "INTAKE_LIMIT", 10_000)


@pytest.fixture
def sales_pair(app: FastAPI) -> Iterator[tuple[SignedIn, SignedIn]]:
    """Two sales users, "Sales 1" and "Sales 2", each signed in with their own client."""
    pair = []
    for number in (1, 2):
        user = make_user("sales", email=f"sales{number}@example.com", name=f"Sales {number}")
        pair.append(sign_in(new_client(app), user))
    yield pair[0], pair[1]
    for signed in pair:
        signed.client.close()
