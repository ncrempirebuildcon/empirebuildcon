"""Tests for public search functionality with FTS and pg_trgm (Task 5.1).

Covers:
- Search by project name.
- Search by tagline.
- Search by locality name.
- Search by city name.
- Typo tolerance: 1 typo matches via pg_trgm trigram similarity.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.projects.models import City, Locality, Project


def test_public_project_search(db: Session, client: TestClient) -> None:
    # 1. Seed cities and localities
    city_lko = db.scalar(select(City).where(City.slug == "search-lucknow"))
    if not city_lko:
        city_lko = City(name="Lucknow", slug="search-lucknow", state="UP")
        db.add(city_lko)
        db.flush()

    city_vns = db.scalar(select(City).where(City.slug == "search-varanasi"))
    if not city_vns:
        city_vns = City(name="Varanasi", slug="search-varanasi", state="UP")
        db.add(city_vns)
        db.flush()

    loc_hazratganj = db.scalar(select(Locality).where(Locality.slug == "search-hazratganj"))
    if not loc_hazratganj:
        loc_hazratganj = Locality(name="Hazratganj", slug="search-hazratganj", city_id=city_lko.id)
        db.add(loc_hazratganj)
        db.flush()

    loc_assi = db.scalar(select(Locality).where(Locality.slug == "search-assi-ghat"))
    if not loc_assi:
        loc_assi = Locality(name="Assi Ghat", slug="search-assi-ghat", city_id=city_vns.id)
        db.add(loc_assi)
        db.flush()

    # 2. Seed projects
    p1 = Project(
        slug="search-emerald-heights",
        name="Emerald Heights",
        tagline="Panoramic riverside luxury",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city_lko.id,
        locality_id=loc_hazratganj.id,
        rera_number="UPRERASRC001",
        price_min_inr=8_000_000,
        price_max_inr=15_000_000,
    )
    p2 = Project(
        slug="search-kashi-villas",
        name="Kashi Riverside Villas",
        tagline="Serene spiritual retreats",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city_vns.id,
        locality_id=loc_assi.id,
        rera_number="UPRERASRC002",
        price_min_inr=12_000_000,
        price_max_inr=25_000_000,
    )
    db.add_all([p1, p2])
    db.commit()

    # Search 1: by exact project name
    res1 = client.get("/api/v1/public/projects?q=Emerald").json()
    slugs1 = [p["slug"] for p in res1["items"]]
    assert "search-emerald-heights" in slugs1
    assert "search-kashi-villas" not in slugs1

    # Search 2: by tagline keyword
    res2 = client.get("/api/v1/public/projects?q=spiritual").json()
    slugs2 = [p["slug"] for p in res2["items"]]
    assert "search-kashi-villas" in slugs2
    assert "search-emerald-heights" not in slugs2

    # Search 3: by locality name
    res3 = client.get("/api/v1/public/projects?q=Hazratganj").json()
    slugs3 = [p["slug"] for p in res3["items"]]
    assert "search-emerald-heights" in slugs3

    # Search 4: by city name
    res4 = client.get("/api/v1/public/projects?q=Varanasi").json()
    slugs4 = [p["slug"] for p in res4["items"]]
    assert "search-kashi-villas" in slugs4

    # Search 5: with 1 typo in project name ("Emerld" missing 'a' -> pg_trgm similarity)
    res5 = client.get("/api/v1/public/projects?q=Emerld").json()
    slugs5 = [p["slug"] for p in res5["items"]]
    assert "search-emerald-heights" in slugs5

    # Search 6: q + city filter together (M1 regression test)
    res6 = client.get("/api/v1/public/projects?city=search-lucknow&q=Emerald")
    assert res6.status_code == 200
    slugs6 = [p["slug"] for p in res6.json()["items"]]
    assert slugs6 == ["search-emerald-heights"]

    # Search 7: q + non-matching city filter
    res7 = client.get("/api/v1/public/projects?city=search-varanasi&q=Emerald")
    assert res7.status_code == 200
    assert len(res7.json()["items"]) == 0

    # Search 8: q + locality filter together (M1 regression test)
    res8 = client.get("/api/v1/public/projects?locality=search-hazratganj&q=Emerald")
    assert res8.status_code == 200
    slugs8 = [p["slug"] for p in res8.json()["items"]]
    assert slugs8 == ["search-emerald-heights"]

    # Search 9: Relevance ranking (S11)
    # Project with name match vs project with tagline match for query 'riverside'
    res9 = client.get("/api/v1/public/projects?q=riverside&sort=recommended")
    assert res9.status_code == 200
    items9 = res9.json()["items"]
    slugs9 = [p["slug"] for p in items9]
    assert "search-kashi-villas" in slugs9
    assert "search-emerald-heights" in slugs9
    # Kashi Riverside Villas has "Riverside" in name and should rank first or equal
    assert slugs9[0] == "search-kashi-villas"
