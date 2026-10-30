"""Visibility and sample data isolation tests for public endpoints (Task 5.1).

Covers:
- Published only (draft and archived items never returned).
- Off-market items hidden (sales_status == "off_market" never returned; sold_out after available).
- Hidden items (is_visible=False) never returned.
- D-015 Sample data isolation: in production (APP_ENV=production), is_sample=True items are never
  returned anywhere (lists, detail, blocks, sitemap, counts). In dev/test they are returned with
  is_sample: true.
- Bracketed [placeholder] values: sanitized to null in production; returned as-is in dev/test.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content.models import Faq, Offer, Page, Post, Testimonial
from empire_api.projects.models import City, Configuration, Locality, Project
from empire_api.public.visibility import sanitize_placeholders
from empire_api.seo.models import Redirect


def _seed_project(
    db: Session,
    slug: str,
    *,
    publish_state: str = "published",
    sales_status: str = "available",
    is_sample: bool = False,
    is_featured: bool = False,
) -> Project:
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

    project = Project(
        slug=slug,
        name=f"Project {slug}",
        project_type="residential",
        status="ongoing",
        sales_status=sales_status,
        publish_state=publish_state,
        city_id=city.id,
        locality_id=locality.id,
        rera_number=f"UPRERA{slug.upper()[:8]}",
        price_min_inr=5_000_000,
        price_max_inr=10_000_000,
        is_sample=is_sample,
        is_featured=is_featured,
    )
    db.add(project)
    db.flush()
    return project


def test_sanitize_placeholders_rule() -> None:
    # In non-production (dev/test): returned as is
    assert (
        sanitize_placeholders("[Company legal name]", in_production=False) == "[Company legal name]"
    )
    assert sanitize_placeholders("Real Value", in_production=False) == "Real Value"

    # In production: bracketed placeholders become None
    assert sanitize_placeholders("[Company legal name]", in_production=True) is None
    assert sanitize_placeholders("Leading [placeholder] trailing", in_production=True) is None
    assert sanitize_placeholders("Real Value", in_production=True) == "Real Value"
    assert sanitize_placeholders(None, in_production=True) is None

    # Nested structures
    d = {"name": "Real", "legal": "[Legal Name]", "nested": ["Valid", "[Bad]"]}
    sanitized = sanitize_placeholders(d, in_production=True)
    assert sanitized == {"name": "Real", "legal": None, "nested": ["Valid", None]}


def test_published_only_projects(db: Session, client: TestClient) -> None:
    _seed_project(db, "pub-proj", publish_state="published")
    _seed_project(db, "draft-proj", publish_state="draft")
    _seed_project(db, "arch-proj", publish_state="archived")
    db.commit()

    res = client.get("/api/v1/public/projects")
    assert res.status_code == 200
    slugs = [p["slug"] for p in res.json()["items"]]
    assert "pub-proj" in slugs
    assert "draft-proj" not in slugs
    assert "arch-proj" not in slugs

    # Detail check
    assert client.get("/api/v1/public/projects/pub-proj").status_code == 200
    assert client.get("/api/v1/public/projects/draft-proj").status_code == 404
    assert client.get("/api/v1/public/projects/arch-proj").status_code == 404


def test_off_market_projects_and_properties_hidden(db: Session, client: TestClient) -> None:
    p_avail = _seed_project(db, "proj-avail", sales_status="available")
    _seed_project(db, "proj-sold", sales_status="sold_out")
    _seed_project(db, "proj-off", sales_status="off_market")

    # Add configurations
    c_avail = Configuration(
        project_id=p_avail.id,
        slug="cfg-avail",
        name="2 BHK Avail",
        property_type="apartment",
        sales_status="available",
        price_min_inr=5_000_000,
        price_max_inr=5_000_000,
    )
    c_sold = Configuration(
        project_id=p_avail.id,
        slug="cfg-sold",
        name="3 BHK Sold",
        property_type="apartment",
        sales_status="sold_out",
        price_min_inr=8_000_000,
        price_max_inr=8_000_000,
    )
    c_off = Configuration(
        project_id=p_avail.id,
        slug="cfg-off",
        name="4 BHK Off",
        property_type="apartment",
        sales_status="off_market",
        price_min_inr=12_000_000,
        price_max_inr=12_000_000,
    )
    db.add_all([c_avail, c_sold, c_off])
    db.commit()

    # Projects list
    res_p = client.get("/api/v1/public/projects").json()
    p_slugs = [p["slug"] for p in res_p["items"]]
    assert "proj-avail" in p_slugs
    assert "proj-sold" in p_slugs
    assert "proj-off" not in p_slugs
    # sold_out after available
    assert p_slugs.index("proj-avail") < p_slugs.index("proj-sold")

    # Properties list
    res_c = client.get("/api/v1/public/properties").json()
    c_slugs = [c["slug"] for c in res_c["items"]]
    assert "cfg-avail" in c_slugs
    assert "cfg-sold" in c_slugs
    assert "cfg-off" not in c_slugs
    # sold_out after available
    assert c_slugs.index("cfg-avail") < c_slugs.index("cfg-sold")

    # Single configuration detail
    assert (
        client.get("/api/v1/public/projects/proj-avail/configurations/cfg-avail").status_code == 200
    )
    assert (
        client.get("/api/v1/public/projects/proj-avail/configurations/cfg-off").status_code == 404
    )


def test_production_sample_isolation(
    db: Session,
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Seed sample and non-sample projects
    _seed_project(db, "real-project", is_sample=False)
    _seed_project(db, "sample-project", is_sample=True)

    # Seed sample and non-sample posts
    post_real = Post(
        slug="real-post",
        title="Real Post",
        body="Real Body",
        publish_state="published",
        is_sample=False,
    )
    post_sample = Post(
        slug="sample-post",
        title="Sample Post",
        body="Sample Body",
        publish_state="published",
        is_sample=True,
    )
    db.add_all([post_real, post_sample])
    db.commit()

    # In test/development environment: sample items are visible and flagged is_sample=True
    res_p_dev = client.get("/api/v1/public/projects").json()
    slugs_dev = [p["slug"] for p in res_p_dev["items"]]
    assert "sample-project" in slugs_dev
    assert "real-project" in slugs_dev
    sample_proj = next(p for p in res_p_dev["items"] if p["slug"] == "sample-project")
    assert sample_proj["is_sample"] is True

    # Now simulate production environment
    monkeypatch.setattr(get_settings(), "app_env", "production")

    res_p_prod = client.get("/api/v1/public/projects").json()
    slugs_prod = [p["slug"] for p in res_p_prod["items"]]
    assert "real-project" in slugs_prod
    assert "sample-project" not in slugs_prod

    # Detail in production
    assert client.get("/api/v1/public/projects/real-project").status_code == 200
    assert client.get("/api/v1/public/projects/sample-project").status_code == 404

    # Posts in production
    res_posts_prod = client.get("/api/v1/public/posts").json()
    post_slugs_prod = [p["slug"] for p in res_posts_prod["items"]]
    assert "real-post" in post_slugs_prod
    assert "sample-post" not in post_slugs_prod
    assert client.get("/api/v1/public/posts/sample-post").status_code == 404

    # Sitemap in production
    res_sitemap = client.get("/api/v1/public/sitemap").json()
    sitemap_paths = [e["path"] for e in res_sitemap]
    assert "/projects/real-project" in sitemap_paths
    assert "/projects/sample-project" not in sitemap_paths
    assert "/blog/real-post" in sitemap_paths
    assert "/blog/sample-post" not in sitemap_paths


def test_public_site_sanitization_in_production(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # S1: Endpoint-level test for /public/site in production
    # Verify that company, contacts, social, regulator, and seo_defaults placeholders are sanitized
    monkeypatch.setattr(get_settings(), "app_env", "production")

    res = client.get("/api/v1/public/site")
    assert res.status_code == 200
    data = res.json()

    # In production, any placeholder starting with "[" must be sanitized to None / empty
    def _assert_no_placeholders(val: object) -> None:
        if isinstance(val, str):
            assert not (val.startswith("[") and val.endswith("]")), (
                f"Leaked placeholder in production: {val}"
            )
        elif isinstance(val, dict):
            for v in val.values():
                _assert_no_placeholders(v)
        elif isinstance(val, list):
            for item in val:
                _assert_no_placeholders(item)

    _assert_no_placeholders(data)


def test_visibility_across_all_content_types(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # S16: Visibility of FAQs, testimonials, redirects, pages, and offers
    # 1. FAQs: visible vs hidden vs sample
    faq_vis = Faq(question="Visible FAQ", answer="Answer", is_visible=True, is_sample=False)
    faq_hid = Faq(question="Hidden FAQ", answer="Answer", is_visible=False, is_sample=False)
    faq_smp = Faq(question="Sample FAQ", answer="Answer", is_visible=True, is_sample=True)
    db.add_all([faq_vis, faq_hid, faq_smp])

    # 2. Testimonials: consented & visible vs unconsented / hidden
    t_consented = Testimonial(
        person_name="Consented User",
        quote="Loved the home",
        source="google",
        consent_date=datetime.now(UTC).date(),
        is_visible=True,
    )
    t_unconsented = Testimonial(
        person_name="Unconsented User",
        quote="Do not show this",
        source="google",
        consent_date=None,
        is_visible=False,
    )
    db.add_all([t_consented, t_unconsented])

    # 3. Redirects: active vs inactive
    r_act = Redirect(from_path="/old-link", to_path="/new-link", is_active=True)
    r_inact = Redirect(from_path="/dead-link", to_path="/nowhere", is_active=False)
    db.add_all([r_act, r_inact])

    # 4. Pages: published vs draft vs sample
    p_pub = Page(slug="pub-page", title="Published", kind="standard", publish_state="published")
    p_draft = Page(slug="draft-page", title="Draft", kind="standard", publish_state="draft")
    p_smp = Page(
        slug="smp-page",
        title="Sample",
        kind="standard",
        publish_state="published",
        is_sample=True,
    )
    db.add_all([p_pub, p_draft, p_smp])

    # 5. Offers: active vs inactive vs draft project
    draft_proj = _seed_project(db, "offer-draft-proj", publish_state="draft")
    pub_proj = _seed_project(db, "offer-pub-proj", publish_state="published")
    off_act = Offer(
        title="Valid Site Offer",
        placement="home",
        is_active=True,
        project_id=pub_proj.id,
    )
    off_inact = Offer(
        title="Inactive Offer",
        placement="home",
        is_active=False,
        project_id=pub_proj.id,
    )
    off_draft_p = Offer(
        title="Draft Proj Offer",
        placement="home",
        is_active=True,
        project_id=draft_proj.id,
    )
    db.add_all([off_act, off_inact, off_draft_p])
    db.commit()

    # Check in Dev:
    # FAQs
    faqs = client.get("/api/v1/public/faqs").json()
    f_qs = [f["question"] for f in faqs]
    assert "Visible FAQ" in f_qs
    assert "Hidden FAQ" not in f_qs
    assert "Sample FAQ" in f_qs

    # Testimonials: unconsented must NEVER appear
    testimonials = client.get("/api/v1/public/testimonials").json()
    t_names = [t["person_name"] for t in testimonials]
    assert "Consented User" in t_names
    assert "Unconsented User" not in t_names

    # Redirects: inactive must NEVER appear
    redirects = client.get("/api/v1/public/redirects").json()
    r_sources = [r["from_path"] for r in redirects]
    assert "/old-link" in r_sources
    assert "/dead-link" not in r_sources

    # Check in Production: sample items filtered out
    monkeypatch.setattr(get_settings(), "app_env", "production")

    # FAQs in prod
    faqs_prod = client.get("/api/v1/public/faqs").json()
    f_qs_prod = [f["question"] for f in faqs_prod]
    assert "Visible FAQ" in f_qs_prod
    assert "Sample FAQ" not in f_qs_prod

    # Pages in prod
    assert client.get("/api/v1/public/pages/pub-page").status_code == 200
    assert client.get("/api/v1/public/pages/draft-page").status_code == 404
    assert client.get("/api/v1/public/pages/smp-page").status_code == 404

    # Offers on public site: inactive, draft project, and sample excluded
    site_data = client.get("/api/v1/public/site").json()
    offer_titles = [o["title"] for o in site_data.get("offers", [])]
    assert "Valid Site Offer" in offer_titles
    assert "Inactive Offer" not in offer_titles
    assert "Draft Proj Offer" not in offer_titles
