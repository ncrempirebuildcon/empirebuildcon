"""Tests for public projects and properties (configurations) endpoints (Task 5.1).

Covers:
- UP-RERA compliance: RERA authority, registration number, QR code and portal always present.
- Price honesty: price note excludes GST/stamp duty/registration; price_on_request hides numbers.
- Area honesty: carpet area first, in both sq ft and sq m.
- D-038 hero/cover image selection rule.
- Configuration detail and property list with filters and sorting.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.media.models import Media, MediaLink
from empire_api.projects.models import City, Configuration, Locality, Project


def _seed_city_and_locality(db: Session) -> tuple[City, Locality]:
    city = db.scalar(select(City).where(City.slug == "lucknow"))
    if not city:
        city = City(name="Lucknow", slug="lucknow", state="UP")
        db.add(city)
        db.flush()

    locality = db.scalar(select(Locality).where(Locality.slug == "gomti-nagar"))
    if not locality:
        locality = Locality(name="Gomti Nagar", slug="gomti-nagar", city_id=city.id)
        db.add(locality)
        db.flush()

    return city, locality


def test_project_rera_and_price_honesty(db: Session, client: TestClient) -> None:
    city, locality = _seed_city_and_locality(db)

    # 1. Project with normal prices
    p1 = Project(
        slug="rera-normal-proj",
        name="RERA Normal Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAAGT12345",
        price_min_inr=6_000_000,
        price_max_inr=12_000_000,
        price_on_request=False,
    )
    # 2. Project with price_on_request
    p2 = Project(
        slug="rera-por-proj",
        name="RERA POR Project",
        project_type="commercial",
        status="completed",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAAGT67890",
        price_min_inr=15_000_000,
        price_max_inr=30_000_000,
        price_on_request=True,
    )
    db.add_all([p1, p2])
    db.commit()

    # Verify Project 1 detail
    res1 = client.get(f"/api/v1/public/projects/{p1.slug}")
    assert res1.status_code == 200
    data1 = res1.json()

    # RERA checks
    assert data1["rera"]["authority"] == "UP-RERA"
    assert data1["rera"]["number"] == "UPRERAAGT12345"
    assert "up-rera.in" in data1["rera"]["url"]

    # Price note and numeric values visible
    assert "excludes GST, stamp duty and registration" in data1["price"]["note"]
    assert data1["price"]["on_request"] is False
    assert data1["price"]["min_inr"] == 6_000_000
    assert data1["price"]["max_inr"] == 12_000_000

    # Verify Project 2 detail (price on request)
    res2 = client.get(f"/api/v1/public/projects/{p2.slug}")
    assert res2.status_code == 200
    data2 = res2.json()

    # Price on request hides numbers
    assert data2["price"]["on_request"] is True
    assert data2["price"]["min_inr"] is None
    assert data2["price"]["max_inr"] is None
    assert data2["price"]["display"] == "Price on request"


def test_property_carpet_area_and_config_detail(db: Session, client: TestClient) -> None:
    city, locality = _seed_city_and_locality(db)

    project = Project(
        slug="proj-carpet-test",
        name="Carpet Test Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERACARPET1",
        price_min_inr=7_500_000,
        price_max_inr=7_500_000,
    )
    db.add(project)
    db.flush()

    # Configuration: stored in square metres = 120.5 sqm
    config = Configuration(
        project_id=project.id,
        slug="3bhk-luxury",
        name="3 BHK Luxury Apartment",
        property_type="apartment",
        bhk=Decimal("3.0"),
        bathrooms=3,
        area_min_sqm=Decimal("120.50"),
        area_max_sqm=Decimal("120.50"),
        area_basis="carpet",
        area_display_unit="sqft",
        sales_status="available",
        price_min_inr=7_500_000,
        price_max_inr=7_500_000,
        price_on_request=False,
    )
    db.add(config)
    db.commit()

    # Check config detail endpoint
    res = client.get(f"/api/v1/public/projects/{project.slug}/configurations/{config.slug}")
    assert res.status_code == 200
    data = res.json()

    assert data["name"] == "3 BHK Luxury Apartment"
    assert data["bhk"] == 3.0
    assert data["bathrooms"] == 3
    # Carpet area first: sq ft and sq m both present in display string
    assert data["area"]["min_sqm"] == 120.5
    assert data["area"]["basis"] == "carpet"
    assert "sq ft" in data["area"]["display"]
    assert "sq m" in data["area"]["display"]
    assert "(carpet)" in data["area"]["display"]
    # Project RERA carried over
    assert data["project"]["rera"]["number"] == "UPRERACARPET1"
    assert data["price"]["min_inr"] == 7_500_000

    # Also check /api/v1/public/properties listing
    res_list = client.get("/api/v1/public/properties?project_status=ongoing&bhk=3")
    assert res_list.status_code == 200
    items = res_list.json()["items"]
    slugs = [c["slug"] for c in items]
    assert "3bhk-luxury" in slugs
    target = next(c for c in items if c["slug"] == "3bhk-luxury")
    assert target["area"]["min_sqm"] == 120.5
    assert target["area"]["basis"] == "carpet"


def test_d038_hero_cover_selection_rule(db: Session, client: TestClient) -> None:
    city, locality = _seed_city_and_locality(db)

    project = Project(
        slug="proj-hero-rule",
        name="Hero Rule Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAHERO1",
    )
    db.add(project)
    db.flush()

    # Create 3 media items:
    # 1. Unlabelled photo (should not be chosen)
    # 2. Labelled gallery photo (sort_order=1)
    # 3. Labelled gallery photo pinned as cover (sort_order=2, is_cover=True)
    m1 = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"media-unlabelled-{uuid.uuid4().hex[:6]}",
        title="Unlabelled Photo",
        label=None,  # Not labelled
        version=1,
        format="jpg",
        bytes=1000,
        width=800,
        height=600,
        created_by=uuid.uuid4(),
    )
    m2 = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"media-first-photo-{uuid.uuid4().hex[:6]}",
        title="First Photo",
        label="actual_photo",
        version=1,
        format="jpg",
        bytes=1000,
        width=800,
        height=600,
        created_by=uuid.uuid4(),
    )
    m3 = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"media-pinned-cover-{uuid.uuid4().hex[:6]}",
        title="Pinned Cover",
        label="artist_impression",
        version=1,
        format="jpg",
        bytes=1000,
        width=1200,
        height=800,
        created_by=uuid.uuid4(),
    )
    db.add_all([m1, m2, m3])
    db.flush()

    lnk1 = MediaLink(
        media_id=m1.id,
        project_id=project.id,
        role="gallery",
        sort_order=0,
        is_visible=True,
        is_cover=False,
    )
    lnk2 = MediaLink(
        media_id=m2.id,
        project_id=project.id,
        role="gallery",
        sort_order=1,
        is_visible=True,
        is_cover=False,
    )
    lnk3 = MediaLink(
        media_id=m3.id,
        project_id=project.id,
        role="gallery",
        sort_order=2,
        is_visible=True,
        is_cover=True,  # Pinned cover
    )
    db.add_all([lnk1, lnk2, lnk3])
    db.commit()

    # Rule 1: Pinned cover (m3) should be selected as cover
    res = client.get(f"/api/v1/public/projects/{project.slug}").json()
    assert res["cover"] is not None
    assert res["cover"]["id"] == str(m3.id)
    assert res["cover"]["label"] == "artist_impression"

    # Rule 2: If pinned cover is unpinned, first visible labelled photo is selected
    lnk3.is_cover = False
    db.commit()

    res_no_cover = client.get(f"/api/v1/public/projects/{project.slug}").json()
    assert res_no_cover["cover"] is not None
    assert res_no_cover["cover"]["id"] == str(m2.id)
    assert res_no_cover["cover"]["label"] == "actual_photo"

    # Rule 3: If both m2 and m3 are hidden and m1 has no label, cover should be None
    lnk2.is_visible = False
    lnk3.is_visible = False
    db.commit()

    res_no_hero = client.get(f"/api/v1/public/projects/{project.slug}").json()
    assert res_no_hero["cover"] is None


def test_gated_brochure_hidden_from_public_detail(db: Session, client: TestClient) -> None:
    # M4: A gated brochure must not expose delivery URL openly
    city, locality = _seed_city_and_locality(db)

    brochure_media = Media(
        kind="document",
        store="cloudinary",
        resource_type="raw",
        public_id=f"brochure-{uuid.uuid4().hex[:6]}",
        title="Project Brochure",
        version=1,
        format="pdf",
        bytes=50000,
        created_by=uuid.uuid4(),
    )
    db.add(brochure_media)
    db.flush()

    p_gated = Project(
        slug=f"gated-proj-{uuid.uuid4().hex[:4]}",
        name="Gated Brochure Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAGATED1",
        brochure_gated=True,  # GATED!
    )
    db.add(p_gated)
    db.flush()

    link_gated = MediaLink(
        media_id=brochure_media.id,
        project_id=p_gated.id,
        role="brochure",
        is_visible=True,
    )
    db.add(link_gated)

    p_open = Project(
        slug=f"open-proj-{uuid.uuid4().hex[:4]}",
        name="Open Brochure Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAOPEN1",
        brochure_gated=False,  # OPEN!
    )
    db.add(p_open)
    db.flush()

    link_open = MediaLink(
        media_id=brochure_media.id,
        project_id=p_open.id,
        role="brochure",
        is_visible=True,
    )
    db.add(link_open)
    db.commit()

    # Gated project detail must return brochure: None
    res_gated = client.get(f"/api/v1/public/projects/{p_gated.slug}").json()
    assert res_gated["brochure_gated"] is True
    assert res_gated["brochure"] is None

    # Open project detail returns brochure delivery URL
    res_open = client.get(f"/api/v1/public/projects/{p_open.slug}").json()
    assert res_open["brochure_gated"] is False
    assert res_open["brochure"] is not None
    assert res_open["brochure"]["id"] == str(brochure_media.id)
    assert "url" in res_open["brochure"]


def test_off_market_and_sample_configurations_excluded_from_labels(
    db: Session, client: TestClient
) -> None:
    # M5: Off-market configurations must not leak into configuration_labels or property_types
    city, locality = _seed_city_and_locality(db)

    p = Project(
        slug=f"config-filter-proj-{uuid.uuid4().hex[:4]}",
        name="Config Filter Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERACFG1",
    )
    db.add(p)
    db.flush()

    c_avail = Configuration(
        project_id=p.id,
        slug=f"2bhk-{uuid.uuid4().hex[:4]}",
        name="2 BHK Premium",
        property_type="apartment",
        bhk=Decimal("2.0"),
        bathrooms=2,
        area_min_sqm=Decimal("90.0"),
        area_max_sqm=Decimal("90.0"),
        sales_status="available",  # Available
        price_min_inr=5_000_000,
        price_max_inr=5_000_000,
    )
    c_off_market = Configuration(
        project_id=p.id,
        slug=f"4bhk-penthouse-{uuid.uuid4().hex[:4]}",
        name="4 BHK Penthouse",
        property_type="penthouse",
        bhk=Decimal("4.0"),
        bathrooms=4,
        area_min_sqm=Decimal("250.0"),
        area_max_sqm=Decimal("250.0"),
        sales_status="off_market",  # Off-market!
        price_min_inr=25_000_000,
        price_max_inr=25_000_000,
    )
    db.add_all([c_avail, c_off_market])
    db.commit()

    res = client.get(f"/api/v1/public/projects/{p.slug}").json()
    # 4 BHK and penthouse must NOT be in configuration_labels or property_types!
    assert res["configuration_labels"] == ["2 BHK"]
    assert res["property_types"] == ["apartment"]

    # Also on project summary card
    res_list = client.get(f"/api/v1/public/projects?city={city.slug}").json()
    p_summary = next(item for item in res_list["items"] if item["slug"] == p.slug)
    assert p_summary["configuration_labels"] == ["2 BHK"]
    assert p_summary["property_types"] == ["apartment"]


def test_price_on_request_bisection_protection(db: Session, client: TestClient) -> None:
    # S5: budget filters treat price_on_request as NULL
    city, locality = _seed_city_and_locality(db)

    p_por = Project(
        slug=f"bisect-por-{uuid.uuid4().hex[:4]}",
        name="Bisect POR Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAPORBIS",
        price_min_inr=20_000_000,
        price_max_inr=20_000_000,
        price_on_request=True,  # Hidden!
    )
    db.add(p_por)
    db.commit()

    # Filtering with budget_max=25M should NOT match p_por because price is on request!
    res = client.get(f"/api/v1/public/projects?budget_max=25000000&city={city.slug}").json()
    slugs = [item["slug"] for item in res["items"]]
    assert p_por.slug not in slugs


def test_directions_url_on_project_detail(db: Session, client: TestClient) -> None:
    # S9: directions_url is generated from present.directions_url
    city, locality = _seed_city_and_locality(db)

    p = Project(
        slug=f"map-dir-proj-{uuid.uuid4().hex[:4]}",
        name="Directions Test Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAMAP1",
        lat=Decimal("26.8467"),
        lng=Decimal("80.9462"),
    )
    db.add(p)
    db.commit()

    res = client.get(f"/api/v1/public/projects/{p.slug}").json()
    assert res["location"] is not None
    assert res["location"]["directions_url"] is not None
    assert "google.com/maps/dir" in res["location"]["directions_url"]
    assert "26.8467" in res["location"]["directions_url"]
    assert "80.9462" in res["location"]["directions_url"]
