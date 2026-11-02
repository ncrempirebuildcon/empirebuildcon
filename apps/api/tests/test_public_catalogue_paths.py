"""Public paths for configurations and cities, and their sitemap entries (task 5.3, D-041).

The web app serves a configuration at /projects/<project>/<config> and a city at
/cities/<city>; the sitemap feed lists both, using the same visibility rules as the
public endpoints (published project, not off-market, no sample rows in production, a noindex
project leaves out its configurations).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.projects.models import City, Configuration, Project
from empire_api.seo.paths import RESERVED_PAGE_SLUGS, city_path, property_path


def _tag() -> str:
    return uuid.uuid4().hex[:6]


def _project(db: Session, city: City, **values: object) -> Project:
    t = _tag()
    fields: dict[str, object] = {
        "slug": f"paths-proj-{t}",
        "name": f"Paths Project {t}",
        "project_type": "residential",
        "status": "ongoing",
        "sales_status": "available",
        "publish_state": "published",
        "city_id": city.id,
        "rera_number": f"UPRERAPATHS{t}",
    }
    project = Project(**{**fields, **values})
    db.add(project)
    db.flush()
    return project


def _configuration(db: Session, project: Project, slug: str, **values: object) -> Configuration:
    cfg = Configuration(
        project_id=project.id,
        slug=slug,
        name=slug.upper(),
        property_type="apartment",
        bhk=Decimal("2.0"),
        area_min_sqm=Decimal("80"),
        area_max_sqm=Decimal("80"),
        **values,
    )
    db.add(cfg)
    db.flush()
    return cfg


def test_path_helpers_match_the_web_app() -> None:
    # The web twin is apps/web/src/lib/public/catalogue.ts (projectPath/propertyPath/cityPath).
    assert property_path("aurum-heights", "3-bhk") == "/projects/aurum-heights/3-bhk"
    assert city_path("noida") == "/cities/noida"


def test_cities_is_a_reserved_page_slug() -> None:
    # A CMS page called "cities" would hide every city page behind it.
    assert "cities" in RESERVED_PAGE_SLUGS


def test_sitemap_lists_configurations_and_cities(db: Session, client: TestClient) -> None:
    t = _tag()
    city = City(name=f"Paths City {t}", slug=f"paths-city-{t}", state="Uttar Pradesh")
    empty_city = City(name=f"Empty City {t}", slug=f"empty-city-{t}", state="Uttar Pradesh")
    db.add_all([city, empty_city])
    db.flush()

    listed = _project(db, city)
    _configuration(db, listed, "two-bhk")
    _configuration(db, listed, "gone", sales_status="off_market")
    hidden = _project(db, city, seo={"noindex": True})
    _configuration(db, hidden, "hidden-home")
    draft = _project(db, empty_city, publish_state="draft")
    _configuration(db, draft, "draft-home")
    db.commit()

    paths = {e["path"] for e in client.get("/api/v1/public/sitemap").json()}

    assert property_path(listed.slug, "two-bhk") in paths
    assert property_path(listed.slug, "gone") not in paths  # off-market configuration
    assert property_path(hidden.slug, "hidden-home") not in paths  # noindex project
    assert property_path(draft.slug, "draft-home") not in paths  # draft project
    assert city_path(city.slug) in paths
    assert city_path(empty_city.slug) not in paths  # no listed project


def test_sitemap_leaves_out_sample_configurations_in_production(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = _tag()
    city = City(name=f"Sample City {t}", slug=f"sample-city-{t}", state="Uttar Pradesh")
    db.add(city)
    db.flush()
    project = _project(db, city)
    _configuration(db, project, "real-home")
    _configuration(db, project, "sample-home", is_sample=True)
    db.commit()

    dev_paths = {e["path"] for e in client.get("/api/v1/public/sitemap").json()}
    assert property_path(project.slug, "sample-home") in dev_paths

    monkeypatch.setattr(get_settings(), "app_env", "production")
    prod_paths = {e["path"] for e in client.get("/api/v1/public/sitemap").json()}
    assert property_path(project.slug, "real-home") in prod_paths
    assert property_path(project.slug, "sample-home") not in prod_paths


def test_budget_filter_matches_a_price_with_one_end(db: Session, client: TestClient) -> None:
    """ "From ₹ 78 L" (no upper end) is inside the ₹ 75 L – ₹ 1.5 Cr band (task 5.3 fix)."""
    t = _tag()
    city = City(name=f"Budget City {t}", slug=f"budget-city-{t}", state="Uttar Pradesh")
    db.add(city)
    db.flush()
    from_only = _project(db, city, price_min_inr=7_800_000)
    up_to_only = _project(db, city, price_max_inr=7_000_000)
    _configuration(db, from_only, "from-home", price_min_inr=7_800_000)
    db.commit()

    def slugs(path: str) -> set[str]:
        body = client.get(path).json()
        return {item.get("slug") for item in body["items"]} | {
            item["project"]["slug"] for item in body["items"] if "project" in item
        }

    band = f"city={city.slug}&budget_min=7500000&budget_max=15000000"
    assert from_only.slug in slugs(f"/api/v1/public/projects?{band}")
    assert up_to_only.slug not in slugs(f"/api/v1/public/projects?{band}")
    assert from_only.slug in slugs(f"/api/v1/public/properties?{band}")
    # Above ₹ 1.5 Cr leaves both out; up to ₹ 75 L finds only the "up to ₹ 70 L" one.
    assert slugs(f"/api/v1/public/projects?city={city.slug}&budget_min=15000000") == set()
    assert slugs(f"/api/v1/public/projects?city={city.slug}&budget_max=7500000") == {
        up_to_only.slug
    }


def test_project_price_on_request_hides_every_home_price(db: Session, client: TestClient) -> None:
    """COMPLIANCE (D-041): "price on request" on the project hides its homes' figures too, even
    when staff left prices on them, on every public answer and in the budget filter."""
    t = _tag()
    city = City(name=f"POR City {t}", slug=f"por-city-{t}", state="Uttar Pradesh")
    db.add(city)
    db.flush()
    project = _project(db, city, price_on_request=True, price_min_inr=7_800_000)
    _configuration(db, project, "priced-home", price_min_inr=7_800_000, price_max_inr=8_000_000)
    db.commit()

    def assert_hidden(price: dict[str, object]) -> None:
        assert price["on_request"] is True
        assert price["display"] == "Price on request"
        assert price["min_inr"] is None and price["max_inr"] is None

    detail = client.get(f"/api/v1/public/projects/{project.slug}").json()
    assert_hidden(detail["price"])
    assert_hidden(detail["configurations"][0]["price"])

    prop = client.get(f"/api/v1/public/projects/{project.slug}/configurations/priced-home").json()
    assert_hidden(prop["price"])

    listed = client.get(f"/api/v1/public/properties?city={city.slug}").json()["items"]
    assert len(listed) == 1
    assert_hidden(listed[0]["price"])

    in_band = client.get(
        f"/api/v1/public/properties?city={city.slug}&budget_min=7500000&budget_max=15000000"
    ).json()["items"]
    assert in_band == []
