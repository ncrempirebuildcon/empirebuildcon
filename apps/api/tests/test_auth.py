"""Sign-in, sessions, CSRF, lockout and rate limits (D-009, SECURITY.md §1–3)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from conftest import GOOD_PASSWORD, make_user, new_client, sign_in
from empire_api.platform.models import AuditLog
from empire_api.timeutil import utcnow
from empire_api.users.models import User, UserSession
from empire_api.users.service import GENERIC_LOGIN_ERROR, LOCKED_MESSAGE
from empire_api.users.sessions import COOKIE_NAME


def test_login_sets_a_host_only_secure_cookie(client: TestClient) -> None:
    user = make_user("sales")
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": GOOD_PASSWORD}
    )
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}=")
    for flag in ("HttpOnly", "Secure", "Path=/", "SameSite=lax"):
        assert flag.lower() in cookie.lower()
    assert "domain=" not in cookie.lower()
    body = response.json()
    assert body["role"] == "sales"
    assert "leads.read" in body["permissions"]
    assert "users.manage" not in body["permissions"]
    assert body["csrf_token"]


def test_me_returns_user_permissions_and_csrf(client: TestClient) -> None:
    signed = sign_in(client, make_user("marketing"))
    body = client.get("/api/v1/auth/me").json()
    assert body["email"] == "marketing@example.com"
    assert body["csrf_token"] == signed.csrf
    assert "settings.read" in body["permissions"]


def test_email_is_case_insensitive(client: TestClient) -> None:
    make_user("admin", email="Mixed@Example.com")
    response = client.post(
        "/api/v1/auth/login", json={"email": "MIXED@example.COM", "password": GOOD_PASSWORD}
    )
    assert response.status_code == 200


def test_wrong_password_and_unknown_email_look_the_same(client: TestClient) -> None:
    user = make_user("sales")
    wrong = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "nope nope nope"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "nope nope nope"}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["detail"] == unknown.json()["detail"] == GENERIC_LOGIN_ERROR


def test_account_without_password_cannot_sign_in(client: TestClient) -> None:
    user = make_user("sales", password=None)
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": "anything at all"}
    )
    assert response.status_code == 401


def test_inactive_account_cannot_sign_in(client: TestClient) -> None:
    user = make_user("sales", is_active=False)
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": GOOD_PASSWORD}
    )
    assert response.status_code == 401


def test_five_failures_lock_the_account_for_15_minutes(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    for _ in range(5):
        r = client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": "wrong password!"}
        )
        assert r.status_code == 401
    locked = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": GOOD_PASSWORD}
    )
    assert locked.status_code == 429
    assert locked.json()["detail"] == LOCKED_MESSAGE
    assert 800 < int(locked.headers["retry-after"]) <= 900
    row = db.get(User, user.id)
    assert row is not None and row.locked_until is not None
    actions = set(db.scalars(select(AuditLog.action)).all())
    assert {"auth.login_failed", "user.locked"} <= actions


def test_lock_expires(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    db.execute(
        update(User).where(User.id == user.id).values(locked_until=utcnow() - timedelta(seconds=1))
    )
    db.commit()
    response = client.post(
        "/api/v1/auth/login", json={"email": user.email, "password": GOOD_PASSWORD}
    )
    assert response.status_code == 200


def test_login_rate_limit_per_ip(client: TestClient) -> None:
    for i in range(10):
        r = client.post("/api/v1/auth/login", json={"email": f"u{i}@example.com", "password": "x"})
        assert r.status_code == 401
    blocked = client.post("/api/v1/auth/login", json={"email": "u99@example.com", "password": "x"})
    assert blocked.status_code == 429
    assert "retry-after" in blocked.headers


def test_writes_need_the_csrf_token(client: TestClient) -> None:
    signed = sign_in(client, make_user("sales"))
    assert client.post("/api/v1/auth/logout").status_code == 403
    assert client.post("/api/v1/auth/logout", headers={"X-CSRF-Token": "forged"}).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=signed.headers()).status_code == 204


def test_logout_revokes_the_session_immediately(app: FastAPI, client: TestClient) -> None:
    signed = sign_in(client, make_user("sales"))
    token = client.cookies.get(COOKIE_NAME)
    assert client.post("/api/v1/auth/logout", headers=signed.headers()).status_code == 204
    replay = new_client(app)
    replay.cookies.set(COOKIE_NAME, token or "")
    assert replay.get("/api/v1/auth/me").status_code == 401


def test_each_login_gets_a_new_session_id(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    first = sign_in(client, user)
    second = sign_in(client, user)
    assert first.csrf != second.csrf
    count = db.scalar(
        select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)
    )
    assert count == 2


def test_idle_sessions_expire_after_8_hours(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    sign_in(client, user)
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id)
        .values(last_seen_at=utcnow() - timedelta(hours=8, minutes=1))
    )
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_sessions_end_after_7_days_whatever_activity(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    sign_in(client, user)
    db.execute(
        update(UserSession)
        .where(UserSession.user_id == user.id)
        .values(expires_at=utcnow() - timedelta(seconds=1))
    )
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_tampered_token_is_rejected(app: FastAPI, client: TestClient) -> None:
    sign_in(client, make_user("sales"))
    token = client.cookies.get(COOKIE_NAME) or ""
    forged = new_client(app)
    forged.cookies.set(COOKIE_NAME, token[:-3] + ("abc" if not token.endswith("abc") else "xyz"))
    assert forged.get("/api/v1/auth/me").status_code == 401


def test_deactivated_user_is_signed_out(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    sign_in(client, user)
    db.execute(update(User).where(User.id == user.id).values(is_active=False))
    db.commit()
    assert client.get("/api/v1/auth/me").status_code == 401


def test_successful_login_is_audited(client: TestClient, db: Session) -> None:
    user = make_user("admin")
    sign_in(client, user)
    row = db.scalar(select(AuditLog).where(AuditLog.action == "auth.login"))
    assert row is not None and row.actor_user_id == user.id


def test_signed_in_calls_work_with_a_trailing_slash(client: TestClient) -> None:
    signed = sign_in(client, make_user("super_admin"))
    assert client.get("/api/v1/auth/me/").status_code == 200
    assert client.get("/api/v1/admin/users/").status_code == 200
    assert client.post("/api/v1/auth/logout/", headers=signed.headers()).status_code == 204


def test_unknown_email_locks_like_a_real_account(client: TestClient) -> None:
    """SECURITY: the lockout answer must not reveal whether an email has an account."""
    for _ in range(5):
        r = client.post(
            "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
        )
        assert r.status_code == 401
    locked = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": "wrong-password"}
    )
    assert locked.status_code == 429
    assert locked.json()["detail"] == LOCKED_MESSAGE
    assert int(locked.headers["retry-after"]) <= 900
