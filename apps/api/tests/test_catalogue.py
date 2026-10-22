"""The catalogue: cities, localities and amenities (projects/catalogue.py) — CRUD, slugs,
"used by N projects" guards, permissions and audit rows."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.projects.models import Locality
from projects_support import (
    PROJECTS,
    audit_rows,
    create_amenity,
    create_city,
    create_locality,
    create_project,
    ok,
)

CITIES = "/api/v1/admin/cities"
LOCALITIES = "/api/v1/admin/localities"
AMENITIES = "/api/v1/admin/amenities"


# --- Cities ----------------------------------------------------------------------------------


def test_city_crud(owner: SignedIn, db: Session) -> None:
    city = create_city(owner, "Greater Noida")
    assert (city["slug"], city["state"], city["project_count"]) == (
        "greater-noida",
        "Uttar Pradesh",
        0,
    )
    renamed = ok(
        owner.client.patch(
            f"{CITIES}/{city['id']}",
            json={"name": "Greater Noida West", "state": "Uttar Pradesh"},
            headers=owner.headers(),
        )
    )
    assert renamed["slug"] == "greater-noida"  # links stay stable after a rename
    reslugged = ok(
        owner.client.patch(
            f"{CITIES}/{city['id']}",
            json={"name": "Greater Noida West", "state": "Uttar Pradesh", "slug": "gnw"},
            headers=owner.headers(),
        )
    )
    assert reslugged["slug"] == "gnw"
    assert audit_rows(db, "city.created") and len(audit_rows(db, "city.updated")) == 2
    gone = owner.client.delete(f"{CITIES}/{city['id']}", headers=owner.headers())
    assert gone.status_code == 204
    assert audit_rows(db, "city.deleted")[0].changes["name"] == ["Greater Noida West", None]


def test_city_slug_clash(owner: SignedIn) -> None:
    create_city(owner, "Noida")
    clash = owner.client.post(
        CITIES, json={"name": "Noida", "state": "Uttar Pradesh"}, headers=owner.headers()
    )
    assert clash.status_code == 409
    assert clash.json()["errors"][0]["field"] == "slug"


def test_city_list_counts_projects_and_pages(owner: SignedIn) -> None:
    lucknow = create_city(owner, "Lucknow")
    create_city(owner, "Agra")
    create_project(owner, location={"city_id": lucknow["id"]})
    body = ok(owner.client.get(CITIES))
    assert [(c["name"], c["project_count"]) for c in body["items"]] == [("Agra", 0), ("Lucknow", 1)]
    paged = ok(owner.client.get(f"{CITIES}?per_page=1&page=2"))
    assert paged["meta"]["total"] == 2 and paged["items"][0]["name"] == "Lucknow"


def test_city_in_use_cannot_be_deleted(owner: SignedIn) -> None:
    city = create_city(owner, "Noida")
    create_project(owner, location={"city_id": city["id"]})
    refused = owner.client.delete(f"{CITIES}/{city['id']}", headers=owner.headers())
    assert refused.status_code == 409
    assert "used by 1 project." in refused.json()["detail"]


def test_deleting_a_city_takes_its_unused_localities(owner: SignedIn, db: Session) -> None:
    city = create_city(owner, "Noida")
    locality = create_locality(owner, city["id"], "Sector 1")
    assert owner.client.delete(f"{CITIES}/{city['id']}", headers=owner.headers()).status_code == 204
    assert db.get(Locality, uuid.UUID(locality["id"])) is None
    assert audit_rows(db, "city.deleted")[0].changes["localities_removed"] == [1, None]


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "state": "Uttar Pradesh"},
        {"name": "Noida"},
        {"name": "Noida", "state": "UP", "slug": "No Ida"},
        {"name": "Noida", "state": "UP", "population": 1},
    ],
)
def test_city_validation(owner: SignedIn, body: dict[str, Any]) -> None:
    assert owner.client.post(CITIES, json=body, headers=owner.headers()).status_code == 422


# --- Localities ------------------------------------------------------------------------------


def test_locality_slug_is_unique_per_city(owner: SignedIn) -> None:
    noida = create_city(owner, "Noida")
    gurugram = create_city(owner, "Gurugram", state="Haryana")
    create_locality(owner, noida["id"], "Sector 50")
    clash = owner.client.post(
        LOCALITIES, json={"city_id": noida["id"], "name": "Sector 50"}, headers=owner.headers()
    )
    assert clash.status_code == 409
    assert clash.json()["errors"][0]["field"] == "slug"
    assert create_locality(owner, gurugram["id"], "Sector 50")["slug"] == "sector-50"


def test_locality_needs_a_real_city(owner: SignedIn) -> None:
    response = owner.client.post(
        LOCALITIES, json={"city_id": str(uuid.uuid4()), "name": "Nowhere"}, headers=owner.headers()
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "city_id"


def test_locality_list_filters_by_city(owner: SignedIn) -> None:
    noida = create_city(owner, "Noida")
    lucknow = create_city(owner, "Lucknow")
    sector = create_locality(owner, noida["id"], "Sector 150")
    create_locality(owner, lucknow["id"], "Gomti Nagar")
    create_project(owner, location={"city_id": noida["id"], "locality_id": sector["id"]})
    body = ok(owner.client.get(f"{LOCALITIES}?city_id={noida['id']}"))
    assert [(row["name"], row["project_count"]) for row in body["items"]] == [("Sector 150", 1)]
    assert ok(owner.client.get(LOCALITIES))["meta"]["total"] == 2


def test_locality_in_use_cannot_move_or_go(owner: SignedIn) -> None:
    noida = create_city(owner, "Noida")
    lucknow = create_city(owner, "Lucknow")
    sector = create_locality(owner, noida["id"], "Sector 150")
    create_project(owner, location={"city_id": noida["id"], "locality_id": sector["id"]})
    moved = owner.client.patch(
        f"{LOCALITIES}/{sector['id']}",
        json={"city_id": lucknow["id"], "name": "Sector 150"},
        headers=owner.headers(),
    )
    assert moved.status_code == 409
    assert "used by 1 project" in moved.json()["detail"]
    gone = owner.client.delete(f"{LOCALITIES}/{sector['id']}", headers=owner.headers())
    assert gone.status_code == 409
    renamed = ok(
        owner.client.patch(
            f"{LOCALITIES}/{sector['id']}",
            json={"city_id": noida["id"], "name": "Sector 150 (Noida Expressway)"},
            headers=owner.headers(),
        )
    )
    assert renamed["slug"] == "sector-150"


def test_unused_locality_moves_and_deletes(owner: SignedIn, db: Session) -> None:
    noida = create_city(owner, "Noida")
    lucknow = create_city(owner, "Lucknow")
    sector = create_locality(owner, noida["id"], "Hazratganj")
    moved = ok(
        owner.client.patch(
            f"{LOCALITIES}/{sector['id']}",
            json={"city_id": lucknow["id"], "name": "Hazratganj"},
            headers=owner.headers(),
        )
    )
    assert moved["city_id"] == lucknow["id"]
    gone = owner.client.delete(f"{LOCALITIES}/{sector['id']}", headers=owner.headers())
    assert gone.status_code == 204
    assert audit_rows(db, "locality.deleted")


# --- Amenities -------------------------------------------------------------------------------


def test_amenity_crud(owner: SignedIn, db: Session) -> None:
    pool = create_amenity(owner, "Swimming pool", icon="swimming-pool", category="lifestyle")
    assert (pool["slug"], pool["icon"], pool["category"]) == (
        "swimming-pool",
        "swimming-pool",
        "lifestyle",
    )
    updated = ok(
        owner.client.patch(
            f"{AMENITIES}/{pool['id']}",
            json={"name": "Infinity pool", "icon": "pool", "category": "lifestyle"},
            headers=owner.headers(),
        )
    )
    assert (updated["name"], updated["slug"]) == ("Infinity pool", "swimming-pool")
    listed = ok(owner.client.get(AMENITIES))
    assert [a["name"] for a in listed["items"]] == ["Infinity pool"]
    assert (
        owner.client.delete(f"{AMENITIES}/{pool['id']}", headers=owner.headers()).status_code == 204
    )
    assert audit_rows(db, "amenity.created") and audit_rows(db, "amenity.deleted")


def test_amenity_name_clash(owner: SignedIn) -> None:
    create_amenity(owner, "Gym")
    clash = owner.client.post(
        AMENITIES,
        json={"name": "GYM", "icon": "gym", "category": "sports"},
        headers=owner.headers(),
    )
    assert clash.status_code == 409
    assert clash.json()["errors"][0]["field"] == "name"
    pool = create_amenity(owner, "Pool")
    renamed = owner.client.patch(
        f"{AMENITIES}/{pool['id']}",
        json={"name": "gym", "icon": "pool", "category": "lifestyle"},
        headers=owner.headers(),
    )
    assert renamed.status_code == 409
    same = owner.client.patch(  # changing only the case of its own name is fine
        f"{AMENITIES}/{pool['id']}",
        json={"name": "POOL", "icon": "pool", "category": "lifestyle"},
        headers=owner.headers(),
    )
    assert same.status_code == 200


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "Gym", "icon": "Gym Icon", "category": "sports"}, "icon"),
        ({"name": "Gym", "icon": "gym", "category": "fitness"}, "category"),
        ({"name": "Gym", "icon": "gym"}, "category"),
        ({"name": "Gym", "icon": "gym", "category": "sports", "slug": "gym"}, "slug"),
    ],
)
def test_amenity_validation(owner: SignedIn, body: dict[str, Any], field: str) -> None:
    response = owner.client.post(AMENITIES, json=body, headers=owner.headers())
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


def test_amenity_in_use_cannot_be_deleted(owner: SignedIn) -> None:
    gym = create_amenity(owner, "Gym")
    for name in ("One", "Two"):
        project = create_project(owner, name)
        ok(
            owner.client.put(
                f"{PROJECTS}/{project['id']}/amenities",
                json={"amenity_ids": [gym["id"]]},
                headers=owner.headers(),
            )
        )
    refused = owner.client.delete(f"{AMENITIES}/{gym['id']}", headers=owner.headers())
    assert refused.status_code == 409
    assert (
        refused.json()["detail"] == "This amenity is used by 2 projects. Remove it from them first."
    )


# --- Permissions and 404s --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "body"),
    [
        (CITIES, {"name": "Agra", "state": "Uttar Pradesh"}),
        (AMENITIES, {"name": "Gym", "icon": "gym", "category": "sports"}),
    ],
)
def test_catalogue_permissions(app: FastAPI, path: str, body: dict[str, Any]) -> None:
    for role, can_write in (("sales", False), ("marketing", False), ("content_editor", True)):
        client = new_client(app)
        signed = sign_in(client, make_user(role))
        assert client.get(path).status_code == 200
        status = client.post(
            path, json={**body, "name": f"{body['name']} {role}"}, headers=signed.headers()
        ).status_code
        assert status == (201 if can_write else 403), role
    anonymous = new_client(app)
    assert anonymous.get(path).status_code == 401


@pytest.mark.parametrize("path", [CITIES, LOCALITIES, AMENITIES])
def test_unknown_catalogue_rows_are_404(owner: SignedIn, path: str) -> None:
    missing = str(uuid.uuid4())
    assert owner.client.delete(f"{path}/{missing}", headers=owner.headers()).status_code == 404


@pytest.mark.parametrize("target", ["city", "locality", "amenity"])
def test_catalogue_slug_race_at_flush_is_409_not_500(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    """Two requests passed the pre-check at once: the unique index answers with 409."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from empire_api.projects import catalogue  # noqa: PLC0415

    racer = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    signed = sign_in(racer, make_user("admin", email="racer@example.com"))
    city = create_city(signed, "Noida")
    if target == "city":
        monkeypatch.setattr(catalogue, "_city_slug_free", lambda *a, **k: None)
        response = racer.post(
            CITIES, json={"name": "Noida", "state": "Uttar Pradesh"}, headers=signed.headers()
        )
        field = "slug"
    elif target == "locality":
        create_locality(signed, city["id"], "Sector 1")
        monkeypatch.setattr(catalogue, "_locality_slug_free", lambda *a, **k: None)
        response = racer.post(
            LOCALITIES, json={"city_id": city["id"], "name": "Sector 1"}, headers=signed.headers()
        )
        field = "slug"
    else:
        create_amenity(signed, "Gym")
        monkeypatch.setattr(catalogue, "_amenity_name_free", lambda *a, **k: None)
        response = racer.post(
            AMENITIES,
            json={"name": "Gym", "icon": "gym", "category": "sports"},
            headers=signed.headers(),
        )
        field = "name"
    assert response.status_code == 409, response.text
    assert response.json()["errors"][0]["field"] == field
