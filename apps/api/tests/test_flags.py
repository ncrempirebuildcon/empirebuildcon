"""Feature flags: who may read and switch them, locks, audit and events."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.platform.models import AuditLog, OutboxEvent
from empire_api.site_settings.flags import DEFAULT_FLAGS, is_enabled


def test_defaults_are_seeded_off(owner: SignedIn) -> None:
    flags = owner.client.get("/api/v1/admin/flags").json()
    assert {f["key"] for f in flags} == {d.key for d in DEFAULT_FLAGS}
    assert not any(f["enabled"] for f in flags)
    locked = {f["key"] for f in flags if f["is_locked"]}
    assert locked == {"listings", "unit_inventory"}


def test_marketing_can_read_but_not_switch(app: FastAPI) -> None:
    client = new_client(app)
    signed = sign_in(client, make_user("marketing"))
    assert client.get("/api/v1/admin/flags").status_code == 200
    r = client.patch(
        "/api/v1/admin/flags/chat_widget", json={"enabled": True}, headers=signed.headers()
    )
    assert r.status_code == 403


def test_sales_cannot_read_flags(app: FastAPI) -> None:
    client = new_client(app)
    sign_in(client, make_user("sales"))
    assert client.get("/api/v1/admin/flags").status_code == 403


def test_switching_a_flag_is_audited_and_emits_an_event(owner: SignedIn, db: Session) -> None:
    r = owner.client.patch(
        "/api/v1/admin/flags/chat_widget", json={"enabled": True}, headers=owner.headers()
    )
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["updated_by"]["id"] == str(owner.user.id)
    assert is_enabled(db, "chat_widget")
    audit = db.scalar(select(AuditLog).where(AuditLog.action == "flag.changed"))
    assert audit is not None and audit.changes == {"enabled": [False, True]}
    event = db.scalar(select(OutboxEvent).where(OutboxEvent.type == "flag.changed"))
    assert event is not None and event.payload == {"key": "chat_widget", "enabled": True}


def test_locked_flags_cannot_be_switched_on(owner: SignedIn) -> None:
    r = owner.client.patch(
        "/api/v1/admin/flags/listings", json={"enabled": True}, headers=owner.headers()
    )
    assert r.status_code == 409
    assert "not built yet" in r.json()["detail"]


def test_unknown_flag_is_404(owner: SignedIn) -> None:
    r = owner.client.patch(
        "/api/v1/admin/flags/nope", json={"enabled": True}, headers=owner.headers()
    )
    assert r.status_code == 404


def test_flag_switch_needs_csrf(owner: SignedIn) -> None:
    r = owner.client.patch("/api/v1/admin/flags/chat_widget", json={"enabled": True})
    assert r.status_code == 403
