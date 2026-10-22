"""Password policy, change, forgot and reset (SECURITY.md §1)."""

from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from conftest import GOOD_PASSWORD, make_user, new_client, sign_in
from empire_api.config import get_settings
from empire_api.platform.models import OutboxEvent
from empire_api.timeutil import utcnow
from empire_api.users import service
from empire_api.users.models import PasswordResetToken, UserSession
from empire_api.users.passwords import policy_errors

NEW_PASSWORD = "a quiet river at dawn"


def test_policy() -> None:
    assert policy_errors("short") == ["Use at least 12 characters."]
    assert policy_errors("x" * 201)
    assert any("too common" in e for e in policy_errors("Password@1234"))
    assert any("too common" in e for e in policy_errors("qwertyuiop123"))
    assert policy_errors("owner@example.com", email="owner@example.com")
    assert policy_errors(NEW_PASSWORD) == []


def test_change_password_keeps_this_session_and_ends_others(
    app: FastAPI, client: TestClient
) -> None:
    user = make_user("admin")
    other = new_client(app)
    sign_in(other, user)
    signed = sign_in(client, user)
    response = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": GOOD_PASSWORD, "new_password": NEW_PASSWORD},
        headers=signed.headers(),
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 200
    assert other.get("/api/v1/auth/me").status_code == 401
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


def test_change_password_needs_the_current_one(client: TestClient) -> None:
    signed = sign_in(client, make_user("admin"))
    response = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": "not my password", "new_password": NEW_PASSWORD},
        headers=signed.headers(),
    )
    assert response.status_code == 400


def test_change_password_applies_the_policy(client: TestClient) -> None:
    signed = sign_in(client, make_user("admin"))
    response = client.post(
        "/api/v1/auth/password/change",
        json={"current_password": GOOD_PASSWORD, "new_password": "password1234"},
        headers=signed.headers(),
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "new_password"


def test_forgot_answers_the_same_for_unknown_emails(client: TestClient, db: Session) -> None:
    make_user("sales")
    known = client.post("/api/v1/auth/password/forgot", json={"email": "sales@example.com"})
    unknown = client.post("/api/v1/auth/password/forgot", json={"email": "ghost@example.com"})
    assert known.status_code == unknown.status_code == 204
    events = db.scalars(
        select(OutboxEvent).where(OutboxEvent.type == "user.password_reset_requested")
    ).all()
    assert len(events) == 1
    event = events[0]
    assert event.contains_personal_data is True
    link = get_settings().fernet().decrypt(event.payload["link_encrypted"].encode()).decode()
    assert "/admin/reset?token=" in link
    assert "token" not in str({k: v for k, v in event.payload.items() if k != "link_encrypted"})


def test_forgot_is_rate_limited_per_email(client: TestClient) -> None:
    make_user("sales")
    for _ in range(3):
        assert (
            client.post(
                "/api/v1/auth/password/forgot", json={"email": "sales@example.com"}
            ).status_code
            == 204
        )
    assert (
        client.post("/api/v1/auth/password/forgot", json={"email": "sales@example.com"}).status_code
        == 429
    )


def _token_for(db: Session, email: str, purpose: str = "reset") -> str:
    user = service.find_user_by_email(db, email)
    assert user is not None
    token = service.issue_password_token(db, user, purpose=purpose, actor_id=None)
    db.commit()
    return token


def test_reset_sets_password_once_and_signs_out_everywhere(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    sign_in(client, user)
    token = _token_for(db, user.email)
    response = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
    )
    assert response.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    live = db.scalars(select(UserSession).where(UserSession.revoked_at.is_(None))).all()
    assert live == []
    again = client.post(
        "/api/v1/auth/password/reset", json={"token": token, "new_password": "another long phrase"}
    )
    assert again.status_code == 400
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


def test_expired_and_unknown_tokens_are_refused(client: TestClient, db: Session) -> None:
    user = make_user("sales")
    token = _token_for(db, user.email)
    db.execute(update(PasswordResetToken).values(expires_at=utcnow() - timedelta(seconds=1)))
    db.commit()
    assert (
        client.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/auth/password/reset", json={"token": "x" * 43, "new_password": NEW_PASSWORD}
        ).status_code
        == 400
    )


def test_setup_link_lets_a_new_account_choose_a_password(client: TestClient, db: Session) -> None:
    user = make_user("content_editor", password=None)
    token = _token_for(db, user.email, purpose="setup")
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert row is not None and row.expires_at - utcnow() > timedelta(hours=23)
    assert (
        client.post(
            "/api/v1/auth/password/reset", json={"token": token, "new_password": NEW_PASSWORD}
        ).status_code
        == 204
    )
    assert (
        client.post(
            "/api/v1/auth/login", json={"email": user.email, "password": NEW_PASSWORD}
        ).status_code
        == 200
    )


def test_tokens_are_stored_hashed(db: Session) -> None:
    user = make_user("sales")
    token = _token_for(db, user.email)
    stored = db.scalars(select(PasswordResetToken.token_hash)).all()
    assert token not in stored
    assert all(len(h) == 64 for h in stored)
