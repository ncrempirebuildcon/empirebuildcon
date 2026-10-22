"""Helpers for the projects module's tests: create catalogue rows and projects through the API,
and read events and audit rows. The `qr_present` fixture is in conftest.py."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.platform.models import AuditLog, OutboxEvent

PROJECTS = "/api/v1/admin/projects"


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json() if status != 204 else None


def create_city(signed: SignedIn, name: str = "Noida", state: str = "Uttar Pradesh") -> Any:
    body = {"name": name, "state": state}
    return ok(signed.client.post("/api/v1/admin/cities", json=body, headers=signed.headers()), 201)


def create_locality(signed: SignedIn, city_id: str, name: str = "Sector 150") -> Any:
    body = {"city_id": city_id, "name": name}
    return ok(
        signed.client.post("/api/v1/admin/localities", json=body, headers=signed.headers()), 201
    )


def create_amenity(signed: SignedIn, name: str, icon: str = "star", category: str = "other") -> Any:
    body = {"name": name, "icon": icon, "category": category}
    return ok(
        signed.client.post("/api/v1/admin/amenities", json=body, headers=signed.headers()), 201
    )


def create_project(signed: SignedIn, name: str = "Aurum Heights", **fields: Any) -> Any:
    body = {"name": name, "status": "ongoing", **fields}
    return ok(signed.client.post(PROJECTS, json=body, headers=signed.headers()), 201)


def patch_project(signed: SignedIn, project_id: str, body: dict[str, Any]) -> Any:
    return signed.client.patch(f"{PROJECTS}/{project_id}", json=body, headers=signed.headers())


def get_project(signed: SignedIn, project_id: str) -> Any:
    return ok(signed.client.get(f"{PROJECTS}/{project_id}"))


def add_child(signed: SignedIn, project_id: str, path: str, body: dict[str, Any]) -> Any:
    url = f"{PROJECTS}/{project_id}/{path}"
    return ok(signed.client.post(url, json=body, headers=signed.headers()), 201)


def add_configuration(signed: SignedIn, project_id: str, name: str = "2 BHK", **fields: Any) -> Any:
    body = {"name": name, "property_type": "apartment", **fields}
    return add_child(signed, project_id, "configurations", body)


def publish(signed: SignedIn, project_id: str) -> Any:
    return signed.client.post(f"{PROJECTS}/{project_id}/publish", headers=signed.headers())


def make_ready(signed: SignedIn, project_id: str) -> None:
    """Fill what the blockers ask for (the QR check needs `qr_present` too)."""
    ok(patch_project(signed, project_id, {"rera_number": "UPRERAPRJ-TEST-01"}))
    add_configuration(signed, project_id)


def events(db: Session, type_: str | None = None) -> list[OutboxEvent]:
    db.expire_all()
    stmt = select(OutboxEvent).order_by(OutboxEvent.id)
    if type_:
        stmt = stmt.where(OutboxEvent.type == type_)
    return list(db.scalars(stmt))


def audit_rows(db: Session, action: str) -> list[AuditLog]:
    db.expire_all()
    return list(db.scalars(select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.id)))
