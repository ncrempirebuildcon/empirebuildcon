"""Staff administration, roles and the audit log (ARCHITECTURE §11)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.platform.models import AuditLog, OutboxEvent
from empire_api.users.models import PasswordResetToken, User, UserSession
from empire_api.users.roles import PERMISSIONS, ROLE_KEYS, has_permission, permissions_for

INVITE = {"email": "New.Sales@Example.com", "name": "Sales 1", "role": "sales"}


def test_matrix_spot_checks() -> None:
    assert permissions_for("super_admin") == sorted(PERMISSIONS)
    assert "users.manage" not in permissions_for("admin")
    assert not has_permission("sales", "audit.read")
    assert has_permission("sales", "leads.read") and not has_permission("sales", "leads.read_all")
    assert has_permission("marketing", "offers.manage")
    assert not has_permission("content_editor", "projects.publish")
    assert has_permission("content_editor", "media.manage")
    assert permissions_for("unknown-role") == []


def test_invite_creates_account_without_password(owner: SignedIn, db: Session) -> None:
    response = owner.client.post("/api/v1/admin/users", json=INVITE, headers=owner.headers())
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["email"] == "new.sales@example.com"
    user = db.get(User, body["id"])
    assert user is not None and user.password_hash is None
    token = db.scalar(select(PasswordResetToken).where(PasswordResetToken.user_id == user.id))
    assert token is not None and token.purpose == "setup"
    types = set(db.scalars(select(OutboxEvent.type)).all())
    assert {"user.created", "user.setup_link_issued"} <= types
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "user.created"))
    assert audit is not None and audit.actor_user_id == owner.user.id
    assert audit.changes["role"] == [None, "sales"]


def test_duplicate_email_conflicts(owner: SignedIn) -> None:
    owner.client.post("/api/v1/admin/users", json=INVITE, headers=owner.headers())
    again = owner.client.post("/api/v1/admin/users", json=INVITE, headers=owner.headers())
    assert again.status_code == 409


def test_unknown_fields_are_rejected(owner: SignedIn) -> None:
    body = {**INVITE, "password": "admins never set passwords"}
    response = owner.client.post("/api/v1/admin/users", json=body, headers=owner.headers())
    assert response.status_code == 422


def test_only_super_admin_manages_users(app: FastAPI) -> None:
    for role in ("admin", "sales", "marketing", "content_editor"):
        client = new_client(app)
        signed = sign_in(client, make_user(role))
        assert client.get("/api/v1/admin/users").status_code == 403
        assert (
            client.post("/api/v1/admin/users", json=INVITE, headers=signed.headers()).status_code
            == 403
        )


def test_signed_out_requests_get_401(client: TestClient) -> None:
    assert client.get("/api/v1/admin/users").status_code == 401
    assert client.get("/api/v1/admin/audit-log").status_code == 401


def test_sales_cannot_read_the_audit_log_but_admin_can(app: FastAPI) -> None:
    sales = new_client(app)
    sign_in(sales, make_user("sales"))
    assert sales.get("/api/v1/admin/audit-log").status_code == 403
    admin = new_client(app)
    sign_in(admin, make_user("admin"))
    assert admin.get("/api/v1/admin/audit-log").status_code == 200


def test_role_change_signs_the_person_out(app: FastAPI, owner: SignedIn, db: Session) -> None:
    person = make_user("sales")
    theirs = new_client(app)
    sign_in(theirs, person)
    response = owner.client.patch(
        f"/api/v1/admin/users/{person.id}", json={"role": "admin"}, headers=owner.headers()
    )
    assert response.status_code == 200
    assert response.json()["role"] == "admin"
    assert theirs.get("/api/v1/auth/me").status_code == 401
    row = db.scalar(select(AuditLog).where(AuditLog.action == "user.role_changed"))
    assert row is not None and row.changes == {"role": ["sales", "admin"]}


def test_last_super_admin_cannot_be_demoted(owner: SignedIn) -> None:
    response = owner.client.patch(
        f"/api/v1/admin/users/{owner.user.id}", json={"role": "admin"}, headers=owner.headers()
    )
    assert response.status_code == 409


def test_unlock_and_revoke_sessions(app: FastAPI, owner: SignedIn, db: Session) -> None:
    person = make_user("sales")
    theirs = new_client(app)
    sign_in(theirs, person)
    for action in ("unlock", "revoke-sessions", "send-reset"):
        r = owner.client.post(f"/api/v1/admin/users/{person.id}/{action}", headers=owner.headers())
        assert r.status_code == 204, action
    assert theirs.get("/api/v1/auth/me").status_code == 401
    assert (
        db.scalars(
            select(UserSession).where(
                UserSession.revoked_at.is_(None), UserSession.user_id == person.id
            )
        ).all()
        == []
    )
    assert db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.user_id == person.id, PasswordResetToken.purpose == "reset"
        )
    )


def test_missing_user_is_404(owner: SignedIn) -> None:
    response = owner.client.get("/api/v1/admin/users/0199e000-0000-7000-8000-000000000000")
    assert response.status_code == 404


def test_list_users_pages(owner: SignedIn) -> None:
    for i in range(3):
        make_user("sales", email=f"s{i}@example.com", name=f"Sales {i}")
    body = owner.client.get("/api/v1/admin/users", params={"per_page": 2}).json()
    assert body["meta"] == {"page": 1, "per_page": 2, "total": 4, "pages": 2}
    assert len(body["items"]) == 2
    found = owner.client.get("/api/v1/admin/users", params={"q": "sales 2"}).json()
    assert [u["name"] for u in found["items"]] == ["Sales 2"]


def test_roles_endpoint_mirrors_the_matrix(owner: SignedIn) -> None:
    roles = owner.client.get("/api/v1/admin/roles").json()
    assert [r["key"] for r in roles] == list(ROLE_KEYS)
    by_key = {r["key"]: r for r in roles}
    assert by_key["marketing"]["permissions"] == permissions_for("marketing")


def test_audit_log_filters_and_names_actors(owner: SignedIn) -> None:
    owner.client.post("/api/v1/admin/users", json=INVITE, headers=owner.headers())
    body = owner.client.get("/api/v1/admin/audit-log", params={"action": "user.created"}).json()
    assert body["meta"]["total"] == 1
    entry = body["items"][0]
    assert entry["actor"]["name"] == owner.user.name
    assert entry["entity_type"] == "user"
    everything = owner.client.get("/api/v1/admin/audit-log").json()
    assert [i["action"] for i in everything["items"]][:2] == ["user.created", "auth.login"]
