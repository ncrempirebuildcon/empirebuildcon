"""Regression tests for the Phase 3 security review (handbook/DECISIONS.md D-027).

Each test names the finding it guards: edge-only access and trusted client IPs, lockout that
can't be raced, can't lock the owner out from another network and can't reveal accounts,
no secrets in error reports, 500s that keep their headers, single-use reset links, a usable
super-admin, masked phones in the audit log, markers that always enforce, and the two-factor
switch reserved for super-admins.
"""

from __future__ import annotations

import concurrent.futures
from collections.abc import Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from conftest import GOOD_PASSWORD, SignedIn, make_user, new_client, sign_in
from empire_api import observability
from empire_api.config import Settings, get_settings
from empire_api.db import get_sessionmaker
from empire_api.main import create_app
from empire_api.platform.models import AuditLog
from empire_api.users import service
from empire_api.users.deps import staff
from empire_api.users.schemas import LoginRequest, PasswordChange
from empire_api.users.service import GENERIC_LOGIN_ERROR, LOCKED_MESSAGE

EDGE_KEY = "test-edge-key-0123456789-abcdefghijklmnopqrstuvwxyz"


@pytest.fixture
def edge_app() -> Iterator[FastAPI]:
    """The app as deployed: only requests carrying our web proxy's key are served."""
    settings = Settings(**{**get_settings().model_dump(), "edge_proxy_key": SecretStr(EDGE_KEY)})
    yield create_app(settings)


def edge_client(app: FastAPI, ip: str) -> TestClient:
    client = TestClient(app, base_url="https://testserver", follow_redirects=False)
    client.headers.update({"X-Empire-Edge-Key": EDGE_KEY, "X-Empire-Client-IP": ip})
    return client


def login(client: TestClient, email: str, password: str) -> int:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    return response.status_code


# --- 1. Only our web proxy may call the API; client IP comes from our proxy only ------------


def test_direct_calls_without_the_edge_key_are_refused(edge_app: FastAPI) -> None:
    with TestClient(edge_app, base_url="https://testserver") as direct:
        response = direct.post(
            "/api/v1/auth/login", json={"email": "a@example.com", "password": "x"}
        )
        assert response.status_code == 403
        assert response.headers["content-type"].startswith("application/problem+json")
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "x-request-id" in response.headers
        # Health checks and the scheduler's internal calls don't go through the web proxy.
        assert direct.get("/api/health/live").status_code == 200
        assert direct.post("/api/v1/internal/outbox/drain").status_code == 401


def test_wrong_edge_key_is_refused(edge_app: FastAPI) -> None:
    with TestClient(edge_app, base_url="https://testserver") as c:
        c.headers.update({"X-Empire-Edge-Key": "guess"})
        assert c.get("/api/v1/auth/me").status_code == 403


def test_forged_forwarded_for_is_ignored_without_the_edge(client: TestClient) -> None:
    """Without the edge key (local dev) every request counts as the socket address."""
    for i in range(10):
        r = client.post(
            "/api/v1/auth/login",
            json={"email": f"x{i}@example.com", "password": "x"},
            headers={"X-Forwarded-For": f"203.0.113.{i}", "X-Empire-Client-IP": f"198.51.100.{i}"},
        )
        assert r.status_code == 401
    blocked = client.post("/api/v1/auth/login", json={"email": "y@example.com", "password": "x"})
    assert blocked.status_code == 429


# --- 2 and 3. Lockout: no races, no owner lock-out from elsewhere, no account discovery ---------


def test_a_stranger_cannot_lock_the_owner_out(edge_app: FastAPI) -> None:
    owner = make_user("super_admin", email="owner@example.com")
    attacker = edge_client(edge_app, "203.0.113.7")
    for _ in range(5):
        assert login(attacker, owner.email, "wrong password!") == 401
    assert login(attacker, owner.email, GOOD_PASSWORD) == 429
    # The owner, on another network, still gets in.
    assert login(edge_client(edge_app, "198.51.100.20"), owner.email, GOOD_PASSWORD) == 200


def test_unknown_and_real_emails_answer_the_same(edge_app: FastAPI) -> None:
    real = make_user("sales", email="real@example.com")
    answers = {}
    for email in (real.email, "nobody-here@example.com"):
        c = edge_client(edge_app, "203.0.113.50" if email == real.email else "203.0.113.51")
        codes = [login(c, email, "wrong password!") for _ in range(6)]
        last = c.post("/api/v1/auth/login", json={"email": email, "password": "wrong password!"})
        answers[email] = (codes, last.status_code, last.json()["detail"])
    assert answers[real.email][0] == answers["nobody-here@example.com"][0] == [401] * 5 + [429]
    assert (
        answers[real.email][1:] == answers["nobody-here@example.com"][1:] == (429, LOCKED_MESSAGE)
    )


def test_parallel_guesses_cannot_get_past_five(app: FastAPI) -> None:
    """INVARIANT: at most 5 password checks per account, per network, per 15 minutes."""
    user = make_user("sales", email="target@example.com")

    def attempt(_: int) -> int:
        with new_client(app) as c:
            return login(c, user.email, "wrong password!")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(attempt, range(10)))
    assert codes.count(401) <= 5
    assert set(codes) <= {401, 429}


def test_generic_message_for_unknown_email(client: TestClient) -> None:
    r = client.post("/api/v1/auth/login", json={"email": "ghost@example.com", "password": "x"})
    assert r.json()["detail"] == GENERIC_LOGIN_ERROR


# --- 4. No passwords in error reports ----------------------------------------------------------


def test_password_fields_are_hidden_from_repr() -> None:
    assert "hunter2-secret" not in repr(
        LoginRequest(email="a@example.com", password="hunter2-secret")
    )
    change = PasswordChange(current_password="old-secret-123", new_password="new-secret-12345")
    assert "old-secret-123" not in repr(change) and "new-secret-12345" not in repr(change)


def test_sentry_never_sends_local_variables(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_init(**kwargs: object) -> None:
        captured.update(kwargs)

    monkeypatch.setattr(observability.sentry_sdk, "init", fake_init)
    monkeypatch.setattr(observability.sentry_sdk, "set_tag", lambda *a, **k: None)
    settings = Settings(
        **{**get_settings().model_dump(), "sentry_dsn_api": "https://k@o0.ingest.example/1"}
    )
    assert observability.init_sentry(settings, component="api")
    assert captured["include_local_variables"] is False
    assert captured["send_default_pii"] is False


# --- 5. Unexpected errors keep the security headers and request id ----------------------------


def test_500_keeps_headers_and_request_id() -> None:
    app = create_app()
    boom = APIRouter()

    @boom.get("/api/v1/test-boom", openapi_extra={"x-public": True})
    def explode() -> None:
        raise RuntimeError("database woke up slowly")

    app.include_router(boom)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as c:
        r = c.get("/api/v1/test-boom")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "database woke up" not in r.text
    assert r.headers["x-content-type-options"] == "nosniff"
    assert "x-request-id" in r.headers


# --- 6. Reset links are single-use and old links die -------------------------------------------


def test_older_reset_link_dies_after_a_newer_reset(client: TestClient) -> None:
    user = make_user("sales", email="resetme@example.com")
    with get_sessionmaker()() as db:
        row = db.get(type(user), user.id)
        assert row is not None
        old = service.issue_password_token(db, row, purpose="reset", actor_id=None)
        new = service.issue_password_token(db, row, purpose="reset", actor_id=None)
        db.commit()
    ok = client.post(
        "/api/v1/auth/password/reset", json={"token": new, "new_password": "a brand new passphrase"}
    )
    assert ok.status_code == 204
    stale = client.post(
        "/api/v1/auth/password/reset", json={"token": old, "new_password": "another new passphrase"}
    )
    assert stale.status_code == 400


# --- 7. There is always a super-admin who can sign in ------------------------------------------


def test_invited_super_admin_does_not_count(owner: SignedIn) -> None:
    invited = owner.client.post(
        "/api/v1/admin/users",
        json={"email": "second@example.com", "name": "Second", "role": "super_admin"},
        headers=owner.headers(),
    )
    assert invited.status_code == 201, invited.text
    me = owner.client.patch(
        f"/api/v1/admin/users/{owner.user.id}", json={"role": "admin"}, headers=owner.headers()
    )
    assert me.status_code == 409


# --- 8. Phones are masked in the audit log -----------------------------------------------------


def test_audit_masks_phone_numbers(owner: SignedIn) -> None:
    r = owner.client.post(
        "/api/v1/admin/users",
        json={
            "email": "phone@example.com",
            "name": "Phone",
            "role": "sales",
            "phone": "+919876543210",
        },
        headers=owner.headers(),
    )
    assert r.status_code == 201, r.text
    with get_sessionmaker()() as db:
        changes = db.scalars(
            select(AuditLog.changes).where(AuditLog.action == "user.created")
        ).all()
    assert changes and "9876543210" not in str(changes)


# --- 9. A permission marker always enforces ----------------------------------------------------


def test_staff_marker_enforces_even_without_a_parameter() -> None:
    app = create_app()
    extra = APIRouter()

    @extra.get("/api/v1/admin/test-marker", **staff("users.manage"))
    def no_param() -> dict[str, str]:  # forgot to take require(...) as a parameter
        return {"ok": "yes"}

    app.include_router(extra)
    with TestClient(app, base_url="https://testserver") as c:
        assert c.get("/api/v1/admin/test-marker").status_code == 401
        sales = sign_in(c, make_user("sales"))
        assert sales and c.get("/api/v1/admin/test-marker").status_code == 403


# --- 10. Only a super-admin can change two-factor ----------------------------------------------


def test_admin_cannot_switch_two_factor(app: FastAPI) -> None:
    c = new_client(app)
    admin = sign_in(c, make_user("admin"))
    r = c.patch("/api/v1/admin/flags/admin_2fa", json={"enabled": False}, headers=admin.headers())
    assert r.status_code == 403
