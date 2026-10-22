"""Projects as a whole: create, read, list, update, archive, delete, publish, unpublish and
duplicate (projects/service.py), with their validation, permissions, events and audit rows."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user, new_client, sign_in
from empire_api.config import get_settings
from empire_api.projects import blockers, service
from empire_api.projects.models import Configuration, Project, Tower
from projects_support import (
    PROJECTS,
    add_child,
    add_configuration,
    audit_rows,
    create_amenity,
    create_city,
    create_locality,
    create_project,
    events,
    get_project,
    make_ready,
    ok,
    patch_project,
    publish,
)


def signed(app: FastAPI, role: str) -> SignedIn:
    client = new_client(app)
    return sign_in(client, make_user(role, email=f"{role}-{uuid.uuid4().hex[:6]}@example.com"))


# --- Create and read -------------------------------------------------------------------------


def test_new_project_is_a_draft_with_defaults_and_placeholders(
    owner: SignedIn, db: Session
) -> None:
    project = create_project(owner, "Aurum Heights")
    assert project["slug"] == "aurum-heights"
    assert project["publish_state"] == "draft"
    assert project["published_at"] is None
    assert (project["sales_status"], project["project_type"]) == ("available", "residential")
    assert project["rera"] == {"authority": "UP-RERA", "number": None, "url": None, "qr": None}
    assert project["location"]["state"] == "Uttar Pradesh"
    assert project["location"]["directions_url"] is None
    assert project["price"]["display"] == ""
    for empty in ("gallery", "videos", "documents", "faqs", "towers", "configurations"):
        assert project[empty] == []
    assert project["brochure"] is None and project["cover"] is None
    assert project["created_by"] == str(owner.user.id)
    assert project["publish_blockers"] == [
        blockers.RERA_NUMBER_MISSING,
        blockers.RERA_QR_MISSING,
        blockers.NO_CONFIGURATION,
    ]
    created = audit_rows(db, "project.created")
    assert len(created) == 1 and created[0].changes["slug"] == [None, "aurum-heights"]
    assert events(db) == []  # drafts emit nothing


def test_full_create_round_trips(owner: SignedIn) -> None:
    city = create_city(owner, "Greater Noida")
    locality = create_locality(owner, city["id"], "Knowledge Park")
    project = create_project(
        owner,
        "Sample — Project Z",
        slug="project-z",
        tagline="[Tagline]",
        description="*Bold* line\n- bullet",
        sales_status="sold_out",
        project_type="mixed",
        rera_number="UPRERAPRJ-SAMPLE-09",
        rera_url="https://www.up-rera.in",
        rera_account={"bank_name": "[Bank]", "account_name": "[Name]", "account_number": "[No.]"},
        possession_date="2029-06-30",
        price={"min_inr": 7_800_000, "max_inr": 12_500_000, "note": "+ GST"},
        land_area={"min_sqm": 20234.28},
        location={
            "city_id": city["id"],
            "locality_id": locality["id"],
            "pincode": "201306",
            "lat": 28.4744,
            "lng": 77.504,
            "google_maps_url": "https://maps.app.goo.gl/AbCdEf",
            "pin_source": "url",
        },
        is_featured=True,
        featured_order=2,
        seo={"title": "Project Z | Empire", "noindex": True, "canonical_path": "/projects/z"},
        translations={"hi": {"name": "प्रोजेक्ट ज़ेड"}},
    )
    assert project["slug"] == "project-z"
    assert project["price"]["display"] == "₹ 78 L – ₹ 1.25 Cr"
    assert project["land_area"]["basis"] == "plot"
    assert project["land_area"]["display"].endswith("(plot)")
    assert project["location"]["city"]["name"] == "Greater Noida"
    assert project["location"]["locality"]["slug"] == "knowledge-park"
    assert project["location"]["pin_source"] == "url"
    assert project["location"]["directions_url"] == (
        "https://www.google.com/maps/dir/?api=1&destination=28.474400,77.504000"
    )
    assert project["rera_account"]["bank_name"] == "[Bank]"
    assert project["featured_order"] == 2
    assert project["seo"]["noindex"] is True
    assert project["translations"] == {"hi": {"name": "प्रोजेक्ट ज़ेड"}}
    assert blockers.RERA_NUMBER_MISSING not in project["publish_blockers"]


def test_city_brings_its_state(owner: SignedIn) -> None:
    city = create_city(owner, "Gurugram", state="Haryana")
    project = create_project(owner, location={"city_id": city["id"]})
    assert project["location"]["state"] == "Haryana"


def test_get_unknown_project_is_404(owner: SignedIn) -> None:
    response = owner.client.get(f"{PROJECTS}/{uuid.uuid4()}")
    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")


# --- Slugs -----------------------------------------------------------------------------------


def test_slug_clash_is_409_with_a_field_error(owner: SignedIn, db: Session) -> None:
    create_project(owner, "Aurum Heights")
    response = owner.client.post(
        PROJECTS, json={"name": "Aurum Heights", "status": "ongoing"}, headers=owner.headers()
    )
    assert response.status_code == 409
    assert response.json()["errors"][0]["field"] == "slug"
    other = create_project(owner, "Other")
    clash = patch_project(owner, other["id"], {"slug": "aurum-heights"})
    assert clash.status_code == 409
    assert clash.json()["errors"][0]["field"] == "slug"
    # INVARIANT (common.py): a refused change writes nothing, not even an audit row.
    assert db.scalar(select(Project).where(Project.slug == "aurum-heights-2")) is None
    assert len(audit_rows(db, "project.created")) == 2


def test_slug_needs_latin_letters_or_digits(owner: SignedIn) -> None:
    response = owner.client.post(
        PROJECTS, json={"name": "सैंपल", "status": "ongoing"}, headers=owner.headers()
    )
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "slug"


def test_renaming_keeps_the_slug(owner: SignedIn) -> None:
    project = create_project(owner, "Aurum Heights")
    renamed = ok(patch_project(owner, project["id"], {"name": "Aurum Heights Phase 2"}))
    assert renamed["slug"] == "aurum-heights"


# --- Validation ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"price": {"min_inr": 2_00_00_000, "max_inr": 1_00_00_000}}, "price.max_inr"),
        ({"price": {"rate_inr": 5400}}, "price.rate_unit"),
        ({"price": {"min_inr": -1}}, "price.min_inr"),
        ({"land_area": {"min_sqm": 500, "max_sqm": 100}}, "land_area.max_sqm"),
        ({"location": {"lat": 28.5}}, "location.lng"),
        ({"location": {"lat": 120, "lng": 77}}, "location.lat"),
        ({"location": {"pincode": "012345"}}, "location.pincode"),
        (
            {"location": {"google_maps_url": "https://evil.example/maps"}},
            "location.google_maps_url",
        ),
        ({"location": {"city_id": str(uuid.uuid4())}}, "location.city_id"),
        ({"rera_url": "javascript:alert(1)"}, "rera_url"),
        ({"slug": "Not A Slug"}, "slug"),
        ({"name": "x" * 121}, "name"),
        ({"name": "line\x00break"}, "name"),
        ({"tagline": "two\nlines"}, "tagline"),
        ({"status": "finished"}, "status"),
        ({"total_units": -5}, "total_units"),
        ({"seo": {"canonical_path": "https://evil.example/"}}, "seo.canonical_path"),
        ({"seo": {"title": "t" * 71}}, "seo.title"),
        ({"translations": {"hi": {"price": "x"}}}, "translations"),
        ({"translations": {"en": {"name": "x"}}}, "translations"),
        ({"surprise": True}, "surprise"),
    ],
)
def test_create_validation_errors(owner: SignedIn, body: dict[str, Any], field: str) -> None:
    payload = {"name": "Valid Name", "status": "ongoing", **body}
    response = owner.client.post(PROJECTS, json=payload, headers=owner.headers())
    assert response.status_code == 422, response.text
    assert field in [e["field"] for e in response.json()["errors"]]


def test_locality_must_belong_to_the_chosen_city(owner: SignedIn) -> None:
    noida = create_city(owner, "Noida")
    lucknow = create_city(owner, "Lucknow")
    gomti = create_locality(owner, lucknow["id"], "Gomti Nagar")
    wrong = owner.client.post(
        PROJECTS,
        json={
            "name": "Mismatch",
            "status": "ongoing",
            "location": {"city_id": noida["id"], "locality_id": gomti["id"]},
        },
        headers=owner.headers(),
    )
    assert wrong.status_code == 422
    assert wrong.json()["errors"] == [
        {"field": "location.locality_id", "message": "This locality is not in the chosen city."}
    ]
    no_city = owner.client.post(
        PROJECTS,
        json={"name": "No city", "status": "ongoing", "location": {"locality_id": gomti["id"]}},
        headers=owner.headers(),
    )
    assert no_city.status_code == 422
    assert no_city.json()["errors"][0]["field"] == "location.city_id"
    project = create_project(owner, location={"city_id": lucknow["id"], "locality_id": gomti["id"]})
    moved = patch_project(owner, project["id"], {"location": {"city_id": noida["id"]}})
    assert moved.status_code == 422  # the old locality isn't in the new city


def test_invariant_locality_belongs_to_city_in_the_database(owner: SignedIn, db: Session) -> None:
    """INVARIANT (models.py): the composite foreign key refuses a locality of another city."""
    noida = create_city(owner, "Noida")
    lucknow = create_city(owner, "Lucknow")
    gomti = create_locality(owner, lucknow["id"], "Gomti Nagar")
    db.add(
        Project(
            slug="direct",
            name="Direct",
            status="ongoing",
            city_id=uuid.UUID(noida["id"]),
            locality_id=uuid.UUID(gomti["id"]),
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


# --- Update ----------------------------------------------------------------------------------


def test_patch_changes_only_what_is_sent(owner: SignedIn, db: Session) -> None:
    project = create_project(owner, price={"min_inr": 7_800_000, "max_inr": 12_500_000})
    updated = ok(patch_project(owner, project["id"], {"price": {"min_inr": 8_500_000}}))
    assert updated["price"]["min_inr"] == 8_500_000
    assert updated["price"]["max_inr"] == 12_500_000
    assert updated["price"]["display"] == "₹ 85 L – ₹ 1.25 Cr"
    assert updated["name"] == "Aurum Heights"
    row = audit_rows(db, "project.updated")[0]
    assert row.changes == {"price_min_inr": [7_800_000, 8_500_000]}
    assert row.actor_user_id == owner.user.id


def test_patch_merges_against_stored_values(owner: SignedIn) -> None:
    project = create_project(owner, price={"min_inr": 7_800_000, "max_inr": 12_500_000})
    response = patch_project(owner, project["id"], {"price": {"min_inr": 13_000_000}})
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "price.max_inr"


def test_patch_with_no_change_writes_nothing(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    ok(patch_project(owner, project["id"], {"name": "Aurum Heights"}))
    assert audit_rows(db, "project.updated") == []


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": None}, "name"),
        ({"price": None}, "price"),
        ({"publish_state": "published"}, "publish_state"),
        ({"slug": ""}, "slug"),
    ],
)
def test_patch_refuses(owner: SignedIn, body: dict[str, Any], field: str) -> None:
    project = create_project(owner)
    response = patch_project(owner, project["id"], body)
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == field


def test_pin_source_follows_the_pin(owner: SignedIn) -> None:
    project = create_project(owner)
    typed = ok(patch_project(owner, project["id"], {"location": {"lat": 28.5, "lng": 77.3}}))
    assert typed["location"]["pin_source"] == "manual"
    from_link = ok(
        patch_project(
            owner,
            project["id"],
            {"location": {"lat": 28.51, "lng": 77.31, "pin_source": "plus_code"}},
        )
    )
    assert from_link["location"]["pin_source"] == "plus_code"
    assert from_link["location"]["directions_url"].endswith("destination=28.510000,77.310000")
    cleared = ok(patch_project(owner, project["id"], {"location": {"lat": None, "lng": None}}))
    assert cleared["location"]["pin_source"] is None
    assert cleared["location"]["directions_url"] is None


def test_seo_merges_and_rera_account_clears(owner: SignedIn) -> None:
    project = create_project(
        owner,
        seo={"title": "First", "description": "Kept"},
        rera_account={"bank_name": "[Bank]"},
    )
    updated = ok(
        patch_project(owner, project["id"], {"seo": {"title": "Second"}, "rera_account": None})
    )
    assert updated["seo"]["title"] == "Second"
    assert updated["seo"]["description"] == "Kept"
    assert updated["rera_account"] is None


# --- List ------------------------------------------------------------------------------------


def test_list_searches_filters_and_pages(owner: SignedIn) -> None:
    noida = create_city(owner, "Noida")
    first = create_project(owner, "Aurum Heights", location={"city_id": noida["id"]})
    create_project(owner, "Bodhi Gardens", status="completed", sales_status="sold_out")
    create_project(owner, "Cedar_Park 100%")

    def names(query: str) -> list[str]:
        body = ok(owner.client.get(f"{PROJECTS}?{query}"))
        return [item["name"] for item in body["items"]]

    assert names("q=AURUM") == ["Aurum Heights"]
    assert names("q=bodhi-gar") == ["Bodhi Gardens"]  # slug match
    assert names("q=100%25") == ["Cedar_Park 100%"]
    assert names("q=_") == ["Cedar_Park 100%"]  # "_" is literal, not a wildcard
    assert names("status=completed") == ["Bodhi Gardens"]
    assert names("sales_status=sold_out") == ["Bodhi Gardens"]
    assert names(f"city={noida['id']}") == ["Aurum Heights"]
    assert names("publish_state=published") == []
    # Most recently edited first.
    ok(patch_project(owner, first["id"], {"tagline": "[Edited]"}))
    assert names("")[0] == "Aurum Heights"
    paged = ok(owner.client.get(f"{PROJECTS}?per_page=2&page=2"))
    assert paged["meta"] == {"page": 2, "per_page": 2, "total": 3, "pages": 2}
    assert len(paged["items"]) == 1
    row = paged["items"][0]
    assert {"publish_state", "updated_at", "is_sample", "configuration_labels"} <= set(row)


def test_list_rejects_bad_filters(owner: SignedIn) -> None:
    assert owner.client.get(f"{PROJECTS}?status=finished").status_code == 422
    assert owner.client.get(f"{PROJECTS}?per_page=101").status_code == 422
    assert owner.client.get(f"{PROJECTS}?q={'x' * 101}").status_code == 422


def test_list_shows_configuration_labels(owner: SignedIn) -> None:
    project = create_project(owner)
    add_configuration(owner, project["id"], "2 BHK", bhk=2)
    add_configuration(owner, project["id"], "2.5 BHK", bhk=2.5)
    add_configuration(owner, project["id"], "Corner villa", property_type="villa")
    item = ok(owner.client.get(PROJECTS))["items"][0]
    assert item["configuration_labels"] == ["2 BHK", "2.5 BHK", "Villa"]
    assert item["property_types"] == ["apartment", "villa"]


# --- Permissions -----------------------------------------------------------------------------


def test_sales_and_marketing_can_read_but_not_write(app: FastAPI, owner: SignedIn) -> None:
    project = create_project(owner)
    for role in ("sales", "marketing"):
        person = signed(app, role)
        assert person.client.get(PROJECTS).status_code == 200
        assert person.client.get(f"{PROJECTS}/{project['id']}").status_code == 200
        body = {"name": "New", "status": "ongoing"}
        assert person.client.post(PROJECTS, json=body, headers=person.headers()).status_code == 403
        assert patch_project(person, project["id"], {"name": "x"}).status_code == 403
        assert publish(person, project["id"]).status_code == 403
        url = f"{PROJECTS}/{project['id']}"
        assert person.client.delete(url, headers=person.headers()).status_code == 403


def test_content_editor_writes_but_cannot_publish_or_delete(
    app: FastAPI, owner: SignedIn, qr_present: None
) -> None:
    editor = signed(app, "content_editor")
    project = create_project(editor, "Editor's project")
    make_ready(editor, project["id"])
    assert publish(editor, project["id"]).status_code == 403
    url = f"{PROJECTS}/{project['id']}"
    assert editor.client.post(f"{url}/unpublish", headers=editor.headers()).status_code == 403
    assert editor.client.delete(url, headers=editor.headers()).status_code == 403
    assert editor.client.post(f"{url}/duplicate", headers=editor.headers()).status_code == 201


def test_signed_out_and_missing_csrf(client: Any, owner: SignedIn) -> None:
    anonymous = new_client(client.app)
    assert anonymous.get(PROJECTS).status_code == 401
    no_csrf = owner.client.post(PROJECTS, json={"name": "X", "status": "ongoing"})
    assert no_csrf.status_code == 403


# --- Publish ---------------------------------------------------------------------------------


def test_publish_is_blocked_until_ready(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    response = publish(owner, project["id"])
    assert response.status_code == 409
    body = response.json()
    assert body["title"] == "Publish blocked"
    assert [e["field"] for e in body["errors"]] == ["rera_number", "rera.qr", "configurations"]
    assert [e["message"] for e in body["errors"]] == get_project(owner, project["id"])[
        "publish_blockers"
    ]
    make_ready(owner, project["id"])
    # The QR code comes with the media manager (part 2), so it always blocks in this part.
    assert get_project(owner, project["id"])["publish_blockers"] == [blockers.RERA_QR_MISSING]
    assert publish(owner, project["id"]).status_code == 409
    assert events(db, "project.published") == []


def test_publish_and_unpublish(owner: SignedIn, db: Session, qr_present: None) -> None:
    project = create_project(owner)
    make_ready(owner, project["id"])
    live = ok(publish(owner, project["id"]))
    assert live["publish_state"] == "published"
    assert live["published_at"] is not None
    assert live["publish_blockers"] == []
    published = events(db, "project.published")
    assert len(published) == 1
    assert published[0].aggregate_id == project["id"]
    assert published[0].payload == {"project_id": project["id"], "slug": "aurum-heights"}
    assert published[0].actor_id == owner.user.id
    assert audit_rows(db, "project.published")[0].changes["publish_state"] == [
        "draft",
        "published",
    ]
    again = ok(publish(owner, project["id"]))  # safe to retry: nothing new happens
    assert again["published_at"] == live["published_at"]
    assert len(events(db, "project.published")) == 1
    url = f"{PROJECTS}/{project['id']}/unpublish"
    draft = ok(owner.client.post(url, headers=owner.headers()))
    assert draft["publish_state"] == "draft"
    assert draft["published_at"] == live["published_at"]  # INVARIANT: never cleared
    assert len(events(db, "project.unpublished")) == 1
    assert len(audit_rows(db, "project.unpublished")) == 1


def test_sample_data_cannot_be_published_in_production(
    owner: SignedIn, db: Session, qr_present: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = create_project(owner, "Sample — Project A")
    make_ready(owner, project["id"])
    row = db.get(Project, uuid.UUID(project["id"]))
    assert row is not None
    row.is_sample = True
    db.commit()
    assert get_project(owner, project["id"])["publish_blockers"] == []  # fine in development
    monkeypatch.setattr(get_settings(), "app_env", "production")
    response = publish(owner, project["id"])
    assert response.status_code == 409
    assert response.json()["errors"] == [
        {"field": "is_sample", "message": blockers.SAMPLE_ON_LIVE_SITE}
    ]


def test_updates_emit_events_only_while_published(
    owner: SignedIn, db: Session, qr_present: None
) -> None:
    project = create_project(owner)
    ok(patch_project(owner, project["id"], {"tagline": "[Draft edit]"}))
    assert events(db, "project.updated") == []
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    ok(patch_project(owner, project["id"], {"tagline": "[Live edit]", "slug": "aurum-live"}))
    updated = events(db, "project.updated")
    assert len(updated) == 1
    assert updated[0].payload["changed"] == ["slug", "tagline"]
    assert updated[0].payload["previous_slug"] == "aurum-heights"
    assert updated[0].payload["slug"] == "aurum-live"


def test_a_live_project_keeps_its_rera_number(owner: SignedIn, qr_present: None) -> None:
    project = create_project(owner)
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    response = patch_project(owner, project["id"], {"rera_number": None})
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "rera_number"


# --- Archive and delete ----------------------------------------------------------------------


def test_archive_and_restore(app: FastAPI, owner: SignedIn, db: Session, qr_present: None) -> None:
    editor = signed(app, "content_editor")
    draft = create_project(editor, "Draft one")
    archived = ok(patch_project(editor, draft["id"], {"publish_state": "archived"}))
    assert archived["publish_state"] == "archived"
    assert len(audit_rows(db, "project.archived")) == 1
    restored = ok(patch_project(editor, draft["id"], {"publish_state": "draft"}))
    assert restored["publish_state"] == "draft"
    assert len(audit_rows(db, "project.restored")) == 1
    live = create_project(owner, "Live one")
    make_ready(owner, live["id"])
    ok(publish(owner, live["id"]))
    # SECURITY: taking a live project off the site needs projects.publish.
    refused = patch_project(editor, live["id"], {"publish_state": "archived"})
    assert refused.status_code == 403
    ok(patch_project(owner, live["id"], {"publish_state": "archived"}))
    off = events(db, "project.unpublished")
    assert len(off) == 1 and off[0].payload["reason"] == "archived"
    assert events(db, "project.published")[0].payload["slug"] == "live-one"


def test_delete_only_never_published_drafts(owner: SignedIn, db: Session, qr_present: None) -> None:
    draft = create_project(owner, "Draft")
    tower = add_child(owner, draft["id"], "towers", {"name": "Tower A", "kind": "tower"})
    url = f"{PROJECTS}/{draft['id']}"
    assert owner.client.delete(url, headers=owner.headers()).status_code == 204
    assert db.get(Project, uuid.UUID(draft["id"])) is None
    assert db.get(Tower, uuid.UUID(tower["id"])) is None  # children go with it
    deleted = audit_rows(db, "project.deleted")
    assert len(deleted) == 1 and deleted[0].changes["slug"] == ["draft", None]
    assert owner.client.get(url).status_code == 404

    was_live = create_project(owner, "Was live")
    make_ready(owner, was_live["id"])
    ok(publish(owner, was_live["id"]))
    url = f"{PROJECTS}/{was_live['id']}"
    ok(owner.client.post(f"{url}/unpublish", headers=owner.headers()))
    refused = owner.client.delete(url, headers=owner.headers())
    assert refused.status_code == 409
    assert "Archive it instead" in refused.json()["detail"]

    archived = create_project(owner, "Archived")
    ok(patch_project(owner, archived["id"], {"publish_state": "archived"}))
    url = f"{PROJECTS}/{archived['id']}"
    assert owner.client.delete(url, headers=owner.headers()).status_code == 409


# --- Duplicate -------------------------------------------------------------------------------


def test_duplicate_copies_children_as_a_draft(
    owner: SignedIn, db: Session, qr_present: None
) -> None:
    source = create_project(owner, "Aurum Heights", is_featured=True, featured_order=1)
    tower = add_child(owner, source["id"], "towers", {"name": "Tower A", "kind": "tower"})
    add_configuration(owner, source["id"], "2 BHK", bhk=2, tower_id=tower["id"])
    add_child(owner, source["id"], "specifications", {"category": "Flooring", "text": "[Tiles]"})
    add_child(
        owner,
        source["id"],
        "construction-updates",
        {"title": "Slab", "update_date": "2026-09-30", "tower_id": tower["id"]},
    )
    add_child(
        owner,
        source["id"],
        "payment-plans",
        {"name": "CLP", "stages": [{"label": "All", "percent": 100}]},
    )
    add_child(owner, source["id"], "location-advantages", {"label": "[Metro]", "kind": "transport"})
    gym, pool = create_amenity(owner, "Gym"), create_amenity(owner, "Pool")
    ok(
        owner.client.put(
            f"{PROJECTS}/{source['id']}/amenities",
            json={"amenity_ids": [pool["id"], gym["id"]]},
            headers=owner.headers(),
        )
    )
    ok(patch_project(owner, source["id"], {"rera_number": "UPRERAPRJ-X"}))
    ok(publish(owner, source["id"]))

    url = f"{PROJECTS}/{source['id']}/duplicate"
    copy = ok(owner.client.post(url, headers=owner.headers()), 201)
    assert copy["slug"] == "aurum-heights-copy"
    assert copy["name"] == "Aurum Heights (copy)"
    assert copy["publish_state"] == "draft" and copy["published_at"] is None
    assert copy["is_featured"] is False and copy["featured_order"] is None
    assert copy["rera"]["number"] is None  # COMPLIANCE: never copied (see the test below)
    assert [t["name"] for t in copy["towers"]] == ["Tower A"]
    assert copy["towers"][0]["id"] != tower["id"]
    assert copy["configurations"][0]["tower_id"] == copy["towers"][0]["id"]
    assert copy["construction_updates"][0]["tower_id"] == copy["towers"][0]["id"]
    assert [a["name"] for a in copy["amenities"]] == ["Pool", "Gym"]
    assert len(copy["specifications"]) == len(copy["payment_plans"]) == 1
    assert len(copy["location_advantages"]) == 1
    second = ok(owner.client.post(url, headers=owner.headers()), 201)
    assert second["slug"] == "aurum-heights-copy-2"
    row = audit_rows(db, "project.duplicated")[0]
    assert row.changes["duplicated_from"] == [None, source["id"]]
    # The source is untouched.
    assert get_project(owner, source["id"])["publish_state"] == "published"
    assert db.scalar(select(Configuration).where(Configuration.slug == "2-bhk")) is not None


def test_duplicate_keeps_long_slugs_within_limits(owner: SignedIn) -> None:
    source = create_project(owner, "Long", slug="a" * 120)
    url = f"{PROJECTS}/{source['id']}/duplicate"
    first = ok(owner.client.post(url, headers=owner.headers()), 201)
    second = ok(owner.client.post(url, headers=owner.headers()), 201)
    assert first["slug"] == "a" * 115 + "-copy"
    assert second["slug"] == "a" * 113 + "-copy-2"


# --- Review fixes (Phase 4 part 1 review) ----------------------------------------------------


def test_content_editor_cannot_hide_a_live_project_with_off_market(
    app: FastAPI, owner: SignedIn, db: Session, qr_present: None
) -> None:
    """SECURITY: off_market hides a project from the site (ARCHITECTURE §7), like archiving."""
    project = create_project(owner)
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    editor = signed(app, "content_editor")
    hide = patch_project(editor, project["id"], {"sales_status": "off_market"})
    assert hide.status_code == 403
    assert hide.json()["detail"] == service.NOT_ALLOWED_VISIBILITY
    assert get_project(owner, project["id"])["sales_status"] == "available"
    # Other sales changes stay with projects.write.
    sold = ok(patch_project(editor, project["id"], {"sales_status": "sold_out"}))
    assert sold["sales_status"] == "sold_out"
    assert "visibility_changed" not in events(db, "project.updated")[-1].payload
    # An admin may hide it; the event says the project's visibility changed.
    ok(patch_project(owner, project["id"], {"sales_status": "off_market"}))
    hidden = events(db, "project.updated")[-1]
    assert hidden.payload["visibility_changed"] is True
    assert hidden.payload["changed"] == ["sales_status"]
    # Bringing it back is the same permission.
    back = patch_project(editor, project["id"], {"sales_status": "available"})
    assert back.status_code == 403


def test_off_market_on_a_draft_needs_no_publish_permission(app: FastAPI) -> None:
    editor = signed(app, "content_editor")
    project = create_project(editor)
    hidden = ok(patch_project(editor, project["id"], {"sales_status": "off_market"}))
    assert hidden["sales_status"] == "off_market"


def test_slug_race_at_flush_is_409_not_500(
    app: FastAPI, owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two requests passed the slug pre-check at once: the database's unique index answers."""
    from fastapi.testclient import TestClient  # noqa: PLC0415

    from empire_api.projects import project_input  # noqa: PLC0415

    racer = TestClient(app, base_url="https://testserver", raise_server_exceptions=False)
    signed_in = sign_in(racer, make_user("admin", email="racer@example.com"))
    create_project(signed_in, "Aurum Heights")
    monkeypatch.setattr(project_input, "slug_must_be_free", lambda *args, **kwargs: None)
    created = racer.post(
        PROJECTS, json={"name": "Aurum Heights", "status": "ongoing"}, headers=signed_in.headers()
    )
    assert created.status_code == 409, created.text
    assert created.json()["errors"][0]["field"] == "slug"
    other = create_project(signed_in, "Other")
    moved = patch_project(signed_in, other["id"], {"slug": "aurum-heights"})
    assert moved.status_code == 409, moved.text
    assert moved.json()["errors"][0]["field"] == "slug"


def test_duplicate_never_copies_the_rera_registration(owner: SignedIn, qr_present: None) -> None:
    """COMPLIANCE: a copy must never carry another project's RERA registration (D-002)."""
    source = create_project(
        owner,
        rera_authority="UP-RERA",
        rera_number="UPRERAPRJ-TEST-77",
        rera_url="https://www.up-rera.in/projects/77",
        rera_account={"bank_name": "[Bank]", "account_name": "[Name]", "account_number": "[No.]"},
        seo={"title": "Kept", "canonical_path": "/projects/aurum-heights"},
    )
    add_child(
        owner,
        source["id"],
        "towers",
        {"name": "Phase 2", "kind": "phase", "rera_number": "UPRERAPRJ-TEST-78"},
    )
    url = f"{PROJECTS}/{source['id']}/duplicate"
    copy = ok(owner.client.post(url, headers=owner.headers()), 201)
    assert copy["rera"] == {"authority": "UP-RERA", "number": None, "url": None, "qr": None}
    assert copy["rera_account"] is None
    assert copy["seo"]["canonical_path"] is None
    assert copy["seo"]["title"] == "Kept"
    assert copy["towers"][0]["rera_number"] is None
    assert blockers.RERA_NUMBER_MISSING in copy["publish_blockers"]
    kept = get_project(owner, source["id"])
    assert kept["rera"]["number"] == "UPRERAPRJ-TEST-77"
    assert kept["towers"][0]["rera_number"] == "UPRERAPRJ-TEST-78"


@pytest.mark.parametrize(
    ("pasted", "stored"),
    [
        ("7JWV8XX8+XX Sector 150, Noida, Uttar Pradesh 201310", "7JWV8XX8+XX"),
        ("7jwv8xx8+xx", "7JWV8XX8+XX"),
        ("  7JWV8XX8+XX,  Noida ", "7JWV8XX8+XX"),
    ],
)
def test_project_plus_code_keeps_only_the_full_code(
    owner: SignedIn, pasted: str, stored: str
) -> None:
    project = create_project(owner)
    body = {"location": {"lat": 28.5, "lng": 77.4, "pin_source": "plus_code", "plus_code": pasted}}
    saved = ok(patch_project(owner, project["id"], body))
    assert saved["location"]["plus_code"] == stored


@pytest.mark.parametrize(
    "pasted", ["8XX8+XX Noida", "8FWC2300+G6", "not a code", "Noida 7JWV8XX8+XX"]
)
def test_project_plus_code_must_be_a_full_code(owner: SignedIn, pasted: str) -> None:
    project = create_project(owner)
    response = patch_project(owner, project["id"], {"location": {"plus_code": pasted}})
    assert response.status_code == 422
    assert response.json()["errors"][0]["field"] == "location.plus_code"
