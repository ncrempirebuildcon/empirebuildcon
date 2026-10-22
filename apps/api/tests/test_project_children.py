"""A project's ordered children (projects/children.py, child_kinds.py): towers, configurations,
specifications, location advantages, construction updates, payment plans, reorder and the
amenity list, with validation, permissions, events and audit rows."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.projects.models import Project
from projects_support import (
    PROJECTS,
    add_child,
    add_configuration,
    audit_rows,
    create_amenity,
    create_project,
    events,
    get_project,
    make_ready,
    ok,
    patch_project,
    publish,
)

COLLECTIONS = [
    ("towers", {"name": "Tower A", "kind": "tower"}),
    ("configurations", {"name": "2 BHK", "property_type": "apartment"}),
    ("specifications", {"category": "Flooring", "text": "[Vitrified tiles]"}),
    ("location-advantages", {"label": "[Metro station]", "kind": "transport"}),
    ("construction-updates", {"title": "Slab cast", "update_date": "2026-09-30"}),
    ("payment-plans", {"name": "CLP", "stages": [{"label": "On booking", "percent": 100}]}),
]


def url(project_id: str, path: str, item_id: str | None = None) -> str:
    base = f"{PROJECTS}/{project_id}/{path}"
    return f"{base}/{item_id}" if item_id else base


@pytest.fixture
def project(owner: SignedIn) -> Any:
    return create_project(owner)


# --- The same five operations for every collection -------------------------------------------


@pytest.mark.parametrize(("path", "body"), COLLECTIONS)
def test_crud_and_reorder_for_every_collection(
    owner: SignedIn, project: Any, db: Session, path: str, body: dict[str, Any]
) -> None:
    first = add_child(owner, project["id"], path, body)
    second = add_child(owner, project["id"], path, body | _rename(path, "Second"))
    assert (first["sort_order"], second["sort_order"]) == (0, 1)
    listed = ok(owner.client.get(url(project["id"], path)))
    assert [item["id"] for item in listed] == [first["id"], second["id"]]

    patch = body | _rename(path, "Renamed")
    updated = ok(
        owner.client.patch(
            url(project["id"], path, first["id"]), json=patch, headers=owner.headers()
        )
    )
    assert updated["id"] == first["id"]

    order = {"ids": [second["id"], first["id"]]}
    reordered = owner.client.put(
        url(project["id"], f"{path}/order"), json=order, headers=owner.headers()
    )
    assert reordered.status_code == 204
    listed = ok(owner.client.get(url(project["id"], path)))
    assert [item["id"] for item in listed] == [second["id"], first["id"]]

    gone = owner.client.delete(url(project["id"], path, first["id"]), headers=owner.headers())
    assert gone.status_code == 204
    assert [i["id"] for i in ok(owner.client.get(url(project["id"], path)))] == [second["id"]]

    key = path.replace("-", "_").rstrip("s")
    for action in ("created", "updated", "reordered", "deleted"):
        assert audit_rows(db, f"{key}.{action}"), action
    full = get_project(owner, project["id"])
    assert len(full[path.replace("-", "_")]) == 1


def _rename(path: str, text: str) -> dict[str, Any]:
    field = {
        "towers": "name",
        "configurations": "name",
        "specifications": "text",
        "location-advantages": "label",
        "construction-updates": "title",
        "payment-plans": "name",
    }[path]
    return {field: text}


@pytest.mark.parametrize(("path", "body"), COLLECTIONS)
def test_unknown_items_and_projects_are_404(
    owner: SignedIn, project: Any, path: str, body: dict[str, Any]
) -> None:
    missing = str(uuid.uuid4())
    assert owner.client.get(url(missing, path)).status_code == 404
    assert (
        owner.client.post(url(missing, path), json=body, headers=owner.headers()).status_code == 404
    )
    response = owner.client.patch(
        url(project["id"], path, missing), json=body, headers=owner.headers()
    )
    assert response.status_code == 404
    other = create_project(owner, "Other project")
    item = add_child(owner, other["id"], path, body)
    # An item of another project is not found through this project.
    stolen = owner.client.delete(url(project["id"], path, item["id"]), headers=owner.headers())
    assert stolen.status_code == 404


@pytest.mark.parametrize(("path", "body"), COLLECTIONS)
def test_permissions_on_children(
    app: FastAPI, project: Any, path: str, body: dict[str, Any]
) -> None:
    sales = new_client(app)
    signed = sign_in(sales, make_user("sales"))
    assert sales.get(url(project["id"], path)).status_code == 200
    assert (
        sales.post(url(project["id"], path), json=body, headers=signed.headers()).status_code == 403
    )
    editor = new_client(app)
    signed = sign_in(editor, make_user("content_editor"))
    created = editor.post(url(project["id"], path), json=body, headers=signed.headers())
    assert created.status_code == 201


def test_reorder_needs_every_item_exactly_once(owner: SignedIn, project: Any) -> None:
    a = add_child(owner, project["id"], "towers", {"name": "A", "kind": "tower"})
    b = add_child(owner, project["id"], "towers", {"name": "B", "kind": "tower"})
    order_url = url(project["id"], "towers/order")
    for ids in ([a["id"]], [a["id"], b["id"], str(uuid.uuid4())], [a["id"], a["id"]], []):
        response = owner.client.put(order_url, json={"ids": ids}, headers=owner.headers())
        assert response.status_code == 422, ids
        assert response.json()["errors"][0]["field"] == "ids"


# --- Towers ----------------------------------------------------------------------------------


def test_tower_patch_keeps_fields_not_sent(owner: SignedIn, project: Any, db: Session) -> None:
    tower = add_child(
        owner, project["id"], "towers", {"name": "Tower A", "kind": "tower", "floors": 18}
    )
    assert tower["status"] == "planned"
    updated = ok(
        owner.client.patch(
            url(project["id"], "towers", tower["id"]),
            json={"name": "Tower A1", "kind": "tower"},
            headers=owner.headers(),
        )
    )
    assert (updated["name"], updated["floors"]) == ("Tower A1", 18)
    assert audit_rows(db, "tower.updated")[0].changes == {"name": ["Tower A", "Tower A1"]}


@pytest.mark.parametrize(
    "body",
    [
        {"name": "T", "kind": "skyscraper"},
        {"name": "T", "kind": "tower", "floors": 301},
        {"name": "", "kind": "tower"},
        {"name": "T", "kind": "tower", "status": "done"},
        {"name": "T", "kind": "tower", "colour": "gold"},
    ],
)
def test_tower_validation(owner: SignedIn, project: Any, body: dict[str, Any]) -> None:
    response = owner.client.post(url(project["id"], "towers"), json=body, headers=owner.headers())
    assert response.status_code == 422


def test_tower_progress_comes_from_the_latest_published_update(
    owner: SignedIn, project: Any
) -> None:
    tower = add_child(owner, project["id"], "towers", {"name": "Tower A", "kind": "tower"})
    for date, percent, state in (
        ("2026-08-31", 30, "published"),
        ("2026-09-30", 45, "published"),
        ("2026-10-31", 60, "draft"),
    ):
        add_child(
            owner,
            project["id"],
            "construction-updates",
            {
                "title": f"Progress {date}",
                "update_date": date,
                "tower_id": tower["id"],
                "progress_percent": percent,
                "publish_state": state,
            },
        )
    assert get_project(owner, project["id"])["towers"][0]["progress_percent"] == 45
    assert ok(owner.client.get(url(project["id"], "towers")))[0]["progress_percent"] == 45


def test_deleting_a_tower_unlinks_its_configurations(owner: SignedIn, project: Any) -> None:
    tower = add_child(owner, project["id"], "towers", {"name": "Tower A", "kind": "tower"})
    config = add_configuration(owner, project["id"], tower_id=tower["id"])
    owner.client.delete(url(project["id"], "towers", tower["id"]), headers=owner.headers())
    assert get_project(owner, project["id"])["configurations"][0]["id"] == config["id"]
    assert get_project(owner, project["id"])["configurations"][0]["tower_id"] is None


# --- Configurations --------------------------------------------------------------------------


def test_configuration_area_price_and_slug(owner: SignedIn, project: Any, db: Session) -> None:
    config = add_configuration(
        owner,
        project["id"],
        "3 BHK Premium",
        bhk=3,
        area={"min_sqm": 91.04, "max_sqm": 104.05},
        price={"min_inr": 1_08_00_000, "max_inr": 1_25_00_000},
    )
    assert config["slug"] == "3-bhk-premium"
    assert config["area"]["display"] == "980 – 1,120 sq ft · 91.0 – 104.1 sq m (carpet)"
    assert config["price"]["display"] == "₹ 1.08 Cr – ₹ 1.25 Cr"
    assert config["is_sample"] is False
    assert config["floor_plans"] == []
    # PATCH merges the nested area: only max changes.
    updated = ok(
        owner.client.patch(
            url(project["id"], "configurations", config["id"]),
            json={"name": "3 BHK Premium", "property_type": "apartment", "area": {"max_sqm": 110}},
            headers=owner.headers(),
        )
    )
    assert (updated["area"]["min_sqm"], updated["area"]["max_sqm"]) == (91.04, 110.0)
    assert updated["slug"] == "3-bhk-premium"


def test_configuration_slug_is_unique_per_project(owner: SignedIn, project: Any) -> None:
    add_configuration(owner, project["id"], "2 BHK")
    clash = owner.client.post(
        url(project["id"], "configurations"),
        json={"name": "2 BHK", "property_type": "apartment"},
        headers=owner.headers(),
    )
    assert clash.status_code == 409
    assert clash.json()["errors"][0]["field"] == "slug"
    other = create_project(owner, "Other")
    assert add_configuration(owner, other["id"], "2 BHK")["slug"] == "2-bhk"


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"price": {"min_inr": 9_00_000, "max_inr": 1_00_000}}, "price.max_inr"),
        ({"area": {"min_sqm": 120, "max_sqm": 90}}, "area.max_sqm"),
        ({"bhk": 2.3}, "bhk"),
        ({"bathrooms": 21}, "bathrooms"),
        ({"property_type": "castle"}, "property_type"),
        ({"translations": {"hi": {"tagline": "x"}}}, "translations"),
        ({"tower_id": str(uuid.uuid4())}, "tower_id"),
    ],
)
def test_configuration_validation(
    owner: SignedIn, project: Any, body: dict[str, Any], field: str
) -> None:
    payload = {"name": "2 BHK", "property_type": "apartment", **body}
    response = owner.client.post(
        url(project["id"], "configurations"), json=payload, headers=owner.headers()
    )
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["field"] == field


def test_configuration_tower_must_be_in_the_same_project(owner: SignedIn, project: Any) -> None:
    other = create_project(owner, "Other")
    foreign = add_child(owner, other["id"], "towers", {"name": "Tower Z", "kind": "tower"})
    response = owner.client.post(
        url(project["id"], "configurations"),
        json={"name": "2 BHK", "property_type": "apartment", "tower_id": foreign["id"]},
        headers=owner.headers(),
    )
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "tower_id", "message": "Choose a tower of this project."}
    ]


def test_configurations_of_a_sample_project_are_samples(
    owner: SignedIn, project: Any, db: Session
) -> None:
    row = db.get(Project, uuid.UUID(project["id"]))
    assert row is not None
    row.is_sample = True
    db.commit()
    assert add_configuration(owner, project["id"])["is_sample"] is True


def test_configuration_events_only_on_published_projects(
    owner: SignedIn, project: Any, db: Session, qr_present: None
) -> None:
    config = add_configuration(owner, project["id"])
    assert events(db, "configuration.changed") == []
    ok(patch_project(owner, project["id"], {"rera_number": "UPRERAPRJ-TEST-01"}))
    ok(publish(owner, project["id"]))
    second = add_configuration(owner, project["id"], "3 BHK")
    ok(
        owner.client.patch(
            url(project["id"], "configurations", second["id"]),
            json={"name": "3 BHK", "property_type": "apartment", "sales_status": "sold_out"},
            headers=owner.headers(),
        )
    )
    owner.client.delete(url(project["id"], "configurations", config["id"]), headers=owner.headers())
    changed = events(db, "configuration.changed")
    assert [e.payload["change"] for e in changed] == ["created", "updated", "deleted"]
    assert changed[0].aggregate_type == "configuration"
    assert changed[0].payload["project_id"] == project["id"]


def test_a_live_project_keeps_one_configuration(
    owner: SignedIn, project: Any, qr_present: None
) -> None:
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    only = get_project(owner, project["id"])["configurations"][0]
    response = owner.client.delete(
        url(project["id"], "configurations", only["id"]), headers=owner.headers()
    )
    assert response.status_code == 409
    assert "at least one configuration" in response.json()["detail"]


# --- Specifications, location advantages ----------------------------------------------------


def test_location_advantage_distances(owner: SignedIn, project: Any) -> None:
    place = add_child(
        owner,
        project["id"],
        "location-advantages",
        {"label": "[Metro]", "kind": "transport", "distance_km": 1.856, "travel_minutes": 6},
    )
    assert (place["distance_km"], place["travel_minutes"]) == (1.86, 6)
    too_far = owner.client.post(
        url(project["id"], "location-advantages"),
        json={"label": "[Airport]", "kind": "transport", "distance_km": 1200},
        headers=owner.headers(),
    )
    assert too_far.status_code == 422


def test_specification_text_may_span_lines(owner: SignedIn, project: Any) -> None:
    spec = add_child(
        owner, project["id"], "specifications", {"category": "Kitchen", "text": "- [Hob]\n- [Sink]"}
    )
    assert spec["text"] == "- [Hob]\n- [Sink]"


# --- Construction updates --------------------------------------------------------------------


def test_construction_update_events(
    owner: SignedIn, project: Any, db: Session, qr_present: None
) -> None:
    add_child(
        owner,
        project["id"],
        "construction-updates",
        {"title": "Draft-time", "update_date": "2026-08-31", "publish_state": "published"},
    )
    assert events(db, "construction_update.published") == []  # project not live yet
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    update = add_child(
        owner, project["id"], "construction-updates", {"title": "Slab", "update_date": "2026-09-30"}
    )
    assert events(db, "construction_update.published") == []  # still a draft update
    body = {"title": "Slab", "update_date": "2026-09-30", "publish_state": "published"}
    ok(
        owner.client.patch(
            url(project["id"], "construction-updates", update["id"]),
            json=body,
            headers=owner.headers(),
        )
    )
    went_live = events(db, "construction_update.published")
    assert len(went_live) == 1
    assert went_live[0].aggregate_id == update["id"]
    assert went_live[0].aggregate_type == "construction_update"
    body["title"] = "Slab cast"
    ok(
        owner.client.patch(
            url(project["id"], "construction-updates", update["id"]),
            json=body,
            headers=owner.headers(),
        )
    )
    assert len(events(db, "construction_update.published")) == 1  # an edit isn't "going live"
    assert events(db, "project.updated")[-1].payload["changed"] == ["construction_updates"]
    assert update["photos"] == []


# --- Payment plans ---------------------------------------------------------------------------


def test_payment_plan_stages_must_total_100(owner: SignedIn, project: Any) -> None:
    """INVARIANT (schemas_children.py): a plan's stages add up to exactly 100%."""
    response = owner.client.post(
        url(project["id"], "payment-plans"),
        json={
            "name": "CLP",
            "stages": [{"label": "Booking", "percent": 10}, {"label": "Rest", "percent": 80}],
        },
        headers=owner.headers(),
    )
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {"field": "stages", "message": "The stages add up to 90%. They must total exactly 100%."}
    ]
    thirds = [{"label": f"Part {i}", "percent": p} for i, p in enumerate((33.33, 33.33, 33.34))]
    plan = add_child(owner, project["id"], "payment-plans", {"name": "Thirds", "stages": thirds})
    assert [s["sort_order"] for s in plan["stages"]] == [0, 1, 2]
    assert plan["is_visible"] is True
    three_decimals = owner.client.post(
        url(project["id"], "payment-plans"),
        json={
            "name": "X",
            "stages": [{"label": "A", "percent": 99.995}, {"label": "B", "percent": 0.005}],
        },
        headers=owner.headers(),
    )
    assert three_decimals.status_code == 422
    empty = owner.client.post(
        url(project["id"], "payment-plans"),
        json={"name": "X", "stages": []},
        headers=owner.headers(),
    )
    assert empty.status_code == 422


def test_payment_plan_stage_order_follows_the_list(owner: SignedIn, project: Any) -> None:
    plan = add_child(
        owner,
        project["id"],
        "payment-plans",
        {
            "name": "CLP",
            "stages": [
                {"label": "A", "percent": 40, "sort_order": 7},
                {"label": "B", "percent": 60},
            ],
        },
    )
    stages = [{"label": "B", "percent": 60}, {"label": "A", "percent": 40}]
    updated = ok(
        owner.client.patch(
            url(project["id"], "payment-plans", plan["id"]),
            json={"name": "CLP", "stages": stages},
            headers=owner.headers(),
        )
    )
    assert [(s["label"], s["sort_order"]) for s in updated["stages"]] == [("B", 0), ("A", 1)]


# --- Amenities -------------------------------------------------------------------------------


def test_set_amenities_keeps_the_order(owner: SignedIn, project: Any, db: Session) -> None:
    gym, pool, cctv = (create_amenity(owner, n) for n in ("Gym", "Pool", "CCTV"))
    amenities_url = f"{PROJECTS}/{project['id']}/amenities"
    body = {"amenity_ids": [pool["id"], cctv["id"], gym["id"]]}
    listed = ok(owner.client.put(amenities_url, json=body, headers=owner.headers()))
    assert [a["name"] for a in listed] == ["Pool", "CCTV", "Gym"]
    assert [a["name"] for a in get_project(owner, project["id"])["amenities"]] == [
        "Pool",
        "CCTV",
        "Gym",
    ]
    ok(owner.client.put(amenities_url, json={"amenity_ids": [gym["id"]]}, headers=owner.headers()))
    assert [a["name"] for a in get_project(owner, project["id"])["amenities"]] == ["Gym"]
    assert len(audit_rows(db, "project.amenities_set")) == 2
    ok(owner.client.put(amenities_url, json={"amenity_ids": [gym["id"]]}, headers=owner.headers()))
    assert len(audit_rows(db, "project.amenities_set")) == 2  # no change, no audit row
    ok(owner.client.put(amenities_url, json={"amenity_ids": []}, headers=owner.headers()))
    assert get_project(owner, project["id"])["amenities"] == []


@pytest.mark.parametrize("bad", ["unknown", "duplicate"])
def test_set_amenities_validation(owner: SignedIn, project: Any, bad: str) -> None:
    gym = create_amenity(owner, "Gym")
    ids = [gym["id"], str(uuid.uuid4())] if bad == "unknown" else [gym["id"], gym["id"]]
    response = owner.client.put(
        f"{PROJECTS}/{project['id']}/amenities", json={"amenity_ids": ids}, headers=owner.headers()
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "amenity_ids"


def test_child_edits_on_a_live_project_emit_project_updated(
    owner: SignedIn, project: Any, db: Session, qr_present: None
) -> None:
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    tower = add_child(owner, project["id"], "towers", {"name": "Tower A", "kind": "tower"})
    gym = create_amenity(owner, "Gym")
    ok(
        owner.client.put(
            f"{PROJECTS}/{project['id']}/amenities",
            json={"amenity_ids": [gym["id"]]},
            headers=owner.headers(),
        )
    )
    owner.client.put(
        url(project["id"], "towers/order"), json={"ids": [tower["id"]]}, headers=owner.headers()
    )
    changed = [e.payload["changed"] for e in events(db, "project.updated")]
    assert changed == [["towers"], ["amenities"], ["towers"]]
    full = get_project(owner, project["id"])
    assert full["updated_by"] == str(owner.user.id)


def test_configuration_slug_race_at_flush_is_409_not_500(
    app: FastAPI, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two requests passed the slug pre-check at once: the unique index answers with 409."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from empire_api.projects import child_kinds  # noqa: PLC0415

    racer = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    signed = sign_in(racer, make_user("admin", email="racer@example.com"))
    project = create_project(signed)
    add_configuration(signed, project["id"], "2 BHK")
    other = add_configuration(signed, project["id"], "3 BHK")
    monkeypatch.setattr(child_kinds, "configuration_slug_must_be_free", lambda *a, **k: None)
    created = racer.post(
        url(project["id"], "configurations"),
        json={"name": "2 BHK", "property_type": "apartment"},
        headers=signed.headers(),
    )
    assert created.status_code == 409, created.text
    assert created.json()["errors"][0]["field"] == "slug"
    renamed = racer.patch(
        url(project["id"], "configurations", other["id"]),
        json={"name": "3 BHK", "property_type": "apartment", "slug": "2-bhk"},
        headers=signed.headers(),
    )
    assert renamed.status_code == 409, renamed.text
    assert renamed.json()["errors"][0]["field"] == "slug"
