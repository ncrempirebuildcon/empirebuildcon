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

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content.models import Faq, Offer, Page, PageBlock, Post
from empire_api.content.models import Testimonial as DbTestimonial
from empire_api.media.models import Media, MediaLink
from empire_api.projects.models import City, Configuration, ConstructionUpdate, Locality, Project
from empire_api.public.visibility import resolve_cover_image, sanitize_placeholders
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

    # 2. Testimonials: S16 (2) proves consent is required
    # A) Attempting to set is_visible=True without consent_date is blocked by DB check constraint
    with pytest.raises(IntegrityError):
        invalid_t = DbTestimonial(
            person_name="Invalid User",
            quote="No consent but visible",
            source="google",
            consent_date=None,
            is_visible=True,
        )
        db.add(invalid_t)
        db.flush()
    db.rollback()

    # Re-seed FAQs because rollback rolled back uncommitted flush
    faq_vis = Faq(question="Visible FAQ", answer="Answer", is_visible=True, is_sample=False)
    faq_hid = Faq(question="Hidden FAQ", answer="Answer", is_visible=False, is_sample=False)
    faq_smp = Faq(question="Sample FAQ", answer="Answer", is_visible=True, is_sample=True)
    db.add_all([faq_vis, faq_hid, faq_smp])

    t_consented = DbTestimonial(
        person_name="Consented User",
        quote="Loved the home",
        source="google",
        consent_date=datetime.now(UTC).date(),
        is_visible=True,
    )
    t_unconsented = DbTestimonial(
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


def test_resolve_cover_image_skips_sample_media_in_production(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # R2-N1 / S14: when primary cover is sample media,
    # production skips it and falls back to non-sample
    proj = _seed_project(db, f"cover-sample-fallback-{uuid.uuid4().hex[:4]}")

    m_sample = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"sample-cover-{uuid.uuid4().hex[:6]}",
        title="Sample Cover",
        alt_text="Sample Cover Alt",
        label="artist_impression",
        version=1,
        format="jpg",
        bytes=1024,
        width=1200,
        height=800,
        is_sample=True,
    )
    m_real = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"real-gallery-{uuid.uuid4().hex[:6]}",
        title="Real Photo",
        alt_text="Real Photo Alt",
        label="artist_impression",
        version=1,
        format="jpg",
        bytes=2048,
        width=1200,
        height=800,
        is_sample=False,
    )
    db.add_all([m_sample, m_real])
    db.flush()

    link_sample_cover = MediaLink(
        media_id=m_sample.id,
        project_id=proj.id,
        role="gallery",
        is_cover=True,
        is_visible=True,
        sort_order=1,
    )
    link_real_gallery = MediaLink(
        media_id=m_real.id,
        project_id=proj.id,
        role="gallery",
        is_cover=False,
        is_visible=True,
        sort_order=2,
    )
    db.add_all([link_sample_cover, link_real_gallery])
    db.commit()

    # Unit check of helper
    chosen_dev = resolve_cover_image([link_sample_cover, link_real_gallery], prod=False)
    assert chosen_dev is not None and chosen_dev.id == m_sample.id

    chosen_prod = resolve_cover_image([link_sample_cover, link_real_gallery], prod=True)
    assert chosen_prod is not None and chosen_prod.id == m_real.id

    # Endpoint check: in dev / test, cover image is the sample media
    res_dev = client.get(f"/api/v1/public/projects/{proj.slug}").json()
    assert res_dev["cover"]["id"] == str(m_sample.id)

    # In production, cover image skips the sample media and falls back to real gallery media
    monkeypatch.setattr(get_settings(), "app_env", "production")
    res_prod = client.get(f"/api/v1/public/projects/{proj.slug}").json()
    assert res_prod["cover"]["id"] == str(m_real.id)


def test_site_navigation_and_offers_filtering(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # S16 (4): Nav and offers filtering (inactive, ended, sample, draft project)
    p_nav_pub = Page(
        slug=f"nav-pub-{uuid.uuid4().hex[:4]}",
        title="Nav Pub",
        kind="standard",
        publish_state="published",
        show_in_nav=True,
        nav_order=1,
        is_sample=False,
    )
    p_nav_draft = Page(
        slug=f"nav-draft-{uuid.uuid4().hex[:4]}",
        title="Nav Draft",
        kind="standard",
        publish_state="draft",
        show_in_nav=True,
        nav_order=2,
        is_sample=False,
    )
    p_nav_sample = Page(
        slug=f"nav-smp-{uuid.uuid4().hex[:4]}",
        title="Nav Sample",
        kind="standard",
        publish_state="published",
        show_in_nav=True,
        nav_order=3,
        is_sample=True,
    )
    db.add_all([p_nav_pub, p_nav_draft, p_nav_sample])

    now = datetime.now(UTC)
    off_active = Offer(
        title="Off Active",
        placement="home",
        is_active=True,
        starts_at=now - timedelta(days=2),
        ends_at=now + timedelta(days=2),
        is_sample=False,
    )
    off_ended = Offer(
        title="Off Ended",
        placement="home",
        is_active=True,
        starts_at=now - timedelta(days=10),
        ends_at=now - timedelta(days=1),
        is_sample=False,
    )
    off_sample = Offer(
        title="Off Sample",
        placement="home",
        is_active=True,
        starts_at=now - timedelta(days=1),
        ends_at=now + timedelta(days=5),
        is_sample=True,
    )
    db.add_all([off_active, off_ended, off_sample])
    db.commit()

    # In dev:
    site_dev = client.get("/api/v1/public/site").json()
    nav_labels_dev = [n["label"] for n in site_dev["nav"]]
    assert "Nav Pub" in nav_labels_dev
    assert "Nav Sample" in nav_labels_dev
    assert "Nav Draft" not in nav_labels_dev

    off_titles_dev = [o["title"] for o in site_dev["offers"]]
    assert "Off Active" in off_titles_dev
    assert "Off Sample" in off_titles_dev
    assert "Off Ended" not in off_titles_dev

    # In production:
    monkeypatch.setattr(get_settings(), "app_env", "production")
    site_prod = client.get("/api/v1/public/site").json()
    nav_labels_prod = [n["label"] for n in site_prod["nav"]]
    assert "Nav Pub" in nav_labels_prod
    assert "Nav Sample" not in nav_labels_prod
    assert "Nav Draft" not in nav_labels_prod

    off_titles_prod = [o["title"] for o in site_prod["offers"]]
    assert "Off Active" in off_titles_prod
    assert "Off Sample" not in off_titles_prod
    assert "Off Ended" not in off_titles_prod


def test_hidden_media_links_omitted_from_project_detail(db: Session, client: TestClient) -> None:
    # S16 (5): Media links with is_visible=False are omitted from public detail responses
    proj = _seed_project(db, f"hidden-media-{uuid.uuid4().hex[:4]}")

    m1 = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"g-vis-{uuid.uuid4().hex[:6]}",
        title="Vis Gallery",
        alt_text="Alt",
        label="artist_impression",
        version=1,
        format="jpg",
        bytes=1024,
        width=800,
        height=600,
    )
    m2 = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"g-hid-{uuid.uuid4().hex[:6]}",
        title="Hid Gallery",
        alt_text="Alt",
        label="artist_impression",
        version=1,
        format="jpg",
        bytes=1024,
        width=800,
        height=600,
    )
    m3 = Media(
        kind="video",
        store="cloudinary",
        resource_type="video",
        public_id=f"v-vis-{uuid.uuid4().hex[:6]}",
        title="Vis Video",
        alt_text="Alt",
        label=None,
        version=1,
        format="mp4",
        bytes=1024,
        width=1280,
        height=720,
    )
    m4 = Media(
        kind="video",
        store="cloudinary",
        resource_type="video",
        public_id=f"v-hid-{uuid.uuid4().hex[:6]}",
        title="Hid Video",
        alt_text="Alt",
        label=None,
        version=1,
        format="mp4",
        bytes=1024,
        width=1280,
        height=720,
    )
    db.add_all([m1, m2, m3, m4])
    db.flush()

    lnk1 = MediaLink(
        media_id=m1.id, project_id=proj.id, role="gallery", is_visible=True, sort_order=1
    )
    lnk2 = MediaLink(
        media_id=m2.id, project_id=proj.id, role="gallery", is_visible=False, sort_order=2
    )
    lnk3 = MediaLink(
        media_id=m3.id, project_id=proj.id, role="video", is_visible=True, sort_order=1
    )
    lnk4 = MediaLink(
        media_id=m4.id, project_id=proj.id, role="video", is_visible=False, sort_order=2
    )
    db.add_all([lnk1, lnk2, lnk3, lnk4])
    db.commit()

    detail = client.get(f"/api/v1/public/projects/{proj.slug}").json()
    gallery_ids = [img["id"] for img in detail["gallery"]]
    video_ids = [vid["id"] for vid in detail["videos"]]

    assert str(m1.id) in gallery_ids
    assert str(m2.id) not in gallery_ids
    assert str(m3.id) in video_ids
    assert str(m4.id) not in video_ids


def test_sample_items_inside_grids_omitted_in_production(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # S16 (6): Sample items inside project_grid and property_grid omitted in production
    p_real = _seed_project(db, f"grid-p-real-{uuid.uuid4().hex[:4]}", is_sample=False)
    p_sample = _seed_project(db, f"grid-p-sample-{uuid.uuid4().hex[:4]}", is_sample=True)

    c_real = Configuration(
        project_id=p_real.id,
        slug=f"grid-c-real-{uuid.uuid4().hex[:4]}",
        name="Real Config",
        property_type="apartment",
        sales_status="available",
        price_min_inr=5_000_000,
        price_max_inr=5_000_000,
    )
    c_sample = Configuration(
        project_id=p_sample.id,
        slug=f"grid-c-sample-{uuid.uuid4().hex[:4]}",
        name="Sample Config",
        property_type="apartment",
        sales_status="available",
        price_min_inr=6_000_000,
        price_max_inr=6_000_000,
    )
    db.add_all([c_real, c_sample])
    db.flush()

    page = Page(
        slug=f"grid-page-{uuid.uuid4().hex[:4]}",
        title="Grid Page",
        kind="standard",
        publish_state="published",
    )
    db.add(page)
    db.flush()

    b_pgrid = PageBlock(
        page_id=page.id,
        type="project_grid",
        data={"mode": "curated", "project_ids": [str(p_real.id), str(p_sample.id)]},
        sort_order=1,
    )
    b_cgrid = PageBlock(
        page_id=page.id,
        type="property_grid",
        data={"mode": "curated", "property_ids": [str(c_real.id), str(c_sample.id)]},
        sort_order=2,
    )
    db.add_all([b_pgrid, b_cgrid])
    db.commit()

    # In dev: both real and sample appear
    res_dev = client.get(f"/api/v1/public/pages/{page.slug}").json()
    p_slugs_dev = [p["slug"] for p in res_dev["blocks"][0]["data"]["projects"]]
    c_slugs_dev = [c["slug"] for c in res_dev["blocks"][1]["data"]["properties"]]
    assert p_real.slug in p_slugs_dev
    assert p_sample.slug in p_slugs_dev
    assert c_real.slug in c_slugs_dev
    assert c_sample.slug in c_slugs_dev

    # In production: sample items are omitted from grids
    monkeypatch.setattr(get_settings(), "app_env", "production")
    res_prod = client.get(f"/api/v1/public/pages/{page.slug}").json()
    p_slugs_prod = [p["slug"] for p in res_prod["blocks"][0]["data"]["projects"]]
    c_slugs_prod = [c["slug"] for c in res_prod["blocks"][1]["data"]["properties"]]
    assert p_real.slug in p_slugs_prod
    assert p_sample.slug not in p_slugs_prod
    assert c_real.slug in c_slugs_prod
    assert c_sample.slug not in c_slugs_prod


def test_sample_media_filtering_across_remaining_slots(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Part B Item 2: Verify sample media is excluded in production across all media slots:
    - project gallery
    - video
    - document
    - QR
    - brochure
    - floor plans
    - update photos
    - testimonial photos
    - offer images
    """
    proj = _seed_project(db, f"slots-proj-{uuid.uuid4().hex[:4]}")
    proj.brochure_gated = False

    def _make_media(
        title: str,
        is_sample: bool,
        kind: str = "image",
        label: str | None = "artist_impression",
    ) -> Media:
        res_type = "raw" if kind == "document" else kind
        eff_label = None if kind == "document" else label
        month = date(2026, 10, 1) if eff_label in ("progress_photo", "actual_photo") else None
        return Media(
            kind=kind,
            store="cloudinary",
            resource_type=res_type,
            public_id=f"media-{uuid.uuid4().hex[:6]}",
            title=title,
            alt_text=f"{title} Alt",
            label=eff_label,
            label_month=month,
            version=1,
            format="jpg" if kind == "image" else "mp4" if kind == "video" else "pdf",
            bytes=1024,
            width=1200 if kind == "image" else None,
            height=800 if kind == "image" else None,
            is_sample=is_sample,
        )

    # 1. Media items (sample + real controls where applicable)
    m_real_gallery = _make_media("Real Gallery", is_sample=False)
    m_sample_gallery = _make_media("Sample Gallery", is_sample=True)
    m_sample_video = _make_media("Sample Video", is_sample=True, kind="video")
    m_sample_doc = _make_media("Sample Document", is_sample=True, kind="document")
    m_sample_qr = _make_media("Sample QR", is_sample=True, label="actual_photo")
    m_sample_brochure = _make_media("Sample Brochure", is_sample=True, kind="document")
    m_sample_floor_plan = _make_media("Sample Floor Plan", is_sample=True)
    m_sample_update_photo = _make_media(
        "Sample Update Photo", is_sample=True, label="progress_photo"
    )
    m_sample_testimonial_photo = _make_media(
        "Sample Testimonial Photo", is_sample=True, label="actual_photo"
    )
    m_sample_offer_img = _make_media("Sample Offer Image", is_sample=True)

    db.add_all(
        [
            m_real_gallery,
            m_sample_gallery,
            m_sample_video,
            m_sample_doc,
            m_sample_qr,
            m_sample_brochure,
            m_sample_floor_plan,
            m_sample_update_photo,
            m_sample_testimonial_photo,
            m_sample_offer_img,
        ]
    )
    db.flush()

    # 2. Links to Project
    link_real_gal = MediaLink(
        media_id=m_real_gallery.id,
        project_id=proj.id,
        role="gallery",
        is_cover=True,
        is_visible=True,
        sort_order=1,
    )
    link_sample_gal = MediaLink(
        media_id=m_sample_gallery.id,
        project_id=proj.id,
        role="gallery",
        is_cover=False,
        is_visible=True,
        sort_order=2,
    )
    link_sample_vid = MediaLink(
        media_id=m_sample_video.id,
        project_id=proj.id,
        role="video",
        is_visible=True,
        sort_order=3,
    )
    link_sample_doc = MediaLink(
        media_id=m_sample_doc.id,
        project_id=proj.id,
        role="document",
        is_visible=True,
        sort_order=4,
    )
    link_sample_qr = MediaLink(
        media_id=m_sample_qr.id,
        project_id=proj.id,
        role="rera_qr",
        is_visible=True,
        sort_order=5,
    )
    link_sample_broch = MediaLink(
        media_id=m_sample_brochure.id,
        project_id=proj.id,
        role="brochure",
        is_visible=True,
        sort_order=6,
    )
    db.add_all(
        [
            link_real_gal,
            link_sample_gal,
            link_sample_vid,
            link_sample_doc,
            link_sample_qr,
            link_sample_broch,
        ]
    )

    # 3. Configuration with Floor Plan
    cfg = Configuration(
        project_id=proj.id,
        slug=f"slots-cfg-{uuid.uuid4().hex[:4]}",
        name="Slots 3BHK",
        property_type="apartment",
        sales_status="available",
        price_min_inr=5_000_000,
        price_max_inr=5_000_000,
        is_sample=False,
    )
    db.add(cfg)
    db.flush()
    link_fp = MediaLink(
        media_id=m_sample_floor_plan.id,
        configuration_id=cfg.id,
        role="floor_plan",
        is_visible=True,
    )
    db.add(link_fp)

    # 4. Construction Update with Photo
    update = ConstructionUpdate(
        project_id=proj.id,
        title="Foundation Complete",
        update_date=datetime.now(UTC).date(),
        publish_state="published",
        sort_order=1,
    )
    db.add(update)
    db.flush()
    link_up = MediaLink(
        media_id=m_sample_update_photo.id,
        construction_update_id=update.id,
        role="gallery",
        is_visible=True,
    )
    db.add(link_up)

    # 5. Testimonial with Photo
    t = DbTestimonial(
        person_name="Sample User",
        person_detail="Owner",
        quote="Great home and honest dealings.",
        source="Google Reviews",
        rating=5,
        is_visible=True,
        consent_date=datetime.now(UTC).date(),
        photo_media_id=m_sample_testimonial_photo.id,
    )
    db.add(t)

    # 6. Offer with Image
    offer = Offer(
        title="Sample Media Offer",
        placement="home",
        is_active=True,
        image_media_id=m_sample_offer_img.id,
        is_sample=False,
    )
    db.add(offer)
    db.commit()

    # --- IN DEV: All sample media slots appear ---
    res_proj_dev = client.get(f"/api/v1/public/projects/{proj.slug}").json()
    gal_ids_dev = [m["id"] for m in res_proj_dev["gallery"]]
    vid_ids_dev = [m["id"] for m in res_proj_dev["videos"]]
    doc_ids_dev = [m["id"] for m in res_proj_dev["documents"]]
    assert str(m_sample_gallery.id) in gal_ids_dev
    assert str(m_sample_video.id) in vid_ids_dev
    assert str(m_sample_doc.id) in doc_ids_dev
    assert res_proj_dev["rera"]["qr"] is not None
    assert res_proj_dev["rera"]["qr"]["id"] == str(m_sample_qr.id)
    assert res_proj_dev["brochure"] is not None
    assert res_proj_dev["brochure"]["id"] == str(m_sample_brochure.id)
    assert len(res_proj_dev["construction_updates"][0]["photos"]) > 0
    assert res_proj_dev["construction_updates"][0]["photos"][0]["id"] == str(
        m_sample_update_photo.id
    )

    res_cfg_dev = client.get(
        f"/api/v1/public/projects/{proj.slug}/configurations/{cfg.slug}"
    ).json()
    assert len(res_cfg_dev["floor_plans"]) > 0
    assert res_cfg_dev["floor_plans"][0]["id"] == str(m_sample_floor_plan.id)

    res_site_dev = client.get("/api/v1/public/site").json()
    o_match_dev = next(item for item in res_site_dev["offers"] if item["id"] == str(offer.id))
    assert o_match_dev["image"] is not None
    assert o_match_dev["image"]["id"] == str(m_sample_offer_img.id)

    res_test_dev = client.get("/api/v1/public/testimonials").json()
    t_match_dev = next(item for item in res_test_dev if item["id"] == str(t.id))
    assert t_match_dev["photo"] is not None
    assert t_match_dev["photo"]["id"] == str(m_sample_testimonial_photo.id)

    # --- IN PROD: Every sample media slot is sanitized to None / empty list ---
    monkeypatch.setattr(get_settings(), "app_env", "production")

    res_proj_prod = client.get(f"/api/v1/public/projects/{proj.slug}").json()
    gal_ids_prod = [m["id"] for m in res_proj_prod["gallery"]]
    vid_ids_prod = [m["id"] for m in res_proj_prod["videos"]]
    doc_ids_prod = [m["id"] for m in res_proj_prod["documents"]]
    assert str(m_real_gallery.id) in gal_ids_prod
    assert str(m_sample_gallery.id) not in gal_ids_prod
    assert str(m_sample_video.id) not in vid_ids_prod
    assert str(m_sample_doc.id) not in doc_ids_prod
    assert res_proj_prod["rera"]["qr"] is None
    assert res_proj_prod["brochure"] is None
    assert len(res_proj_prod["construction_updates"][0]["photos"]) == 0

    res_cfg_prod = client.get(
        f"/api/v1/public/projects/{proj.slug}/configurations/{cfg.slug}"
    ).json()
    assert len(res_cfg_prod["floor_plans"]) == 0

    res_site_prod = client.get("/api/v1/public/site").json()
    o_match_prod = next(item for item in res_site_prod["offers"] if item["id"] == str(offer.id))
    assert o_match_prod["image"] is None

    res_test_prod = client.get("/api/v1/public/testimonials").json()
    t_match_prod = next(item for item in res_test_prod if item["id"] == str(t.id))
    assert t_match_prod["photo"] is None


def test_public_site_has_sample_and_offer_dates(
    db: Session, client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """S-N4 / Item 6: PublicSite exposes has_sample and PublicOffer exposes starts_at/ends_at."""
    monkeypatch.setattr(get_settings(), "app_env", "development")
    now = datetime.now(UTC)

    real_proj = _seed_project(db, f"real-site-proj-{uuid.uuid4().hex[:4]}", is_sample=False)
    starts = now - timedelta(days=1)
    ends = now + timedelta(days=10)
    offer = Offer(
        title="Festive Offer",
        placement="banner",
        is_active=True,
        project_id=real_proj.id,
        starts_at=starts,
        ends_at=ends,
        is_sample=False,
    )
    db.add(offer)
    db.commit()

    res_dev = client.get("/api/v1/public/site").json()
    matched = next(o for o in res_dev["offers"] if o["id"] == str(offer.id))
    assert matched["starts_at"] is not None
    assert matched["ends_at"] is not None
    assert datetime.fromisoformat(matched["starts_at"]) == starts
    assert datetime.fromisoformat(matched["ends_at"]) == ends

    # Add published sample project -> has_sample is True in dev
    _seed_project(
        db,
        f"sample-site-proj-{uuid.uuid4().hex[:4]}",
        is_sample=True,
        publish_state="published",
    )
    db.commit()
    res_dev_sample = client.get("/api/v1/public/site").json()
    assert res_dev_sample["has_sample"] is True

    # In production -> has_sample is ALWAYS False
    monkeypatch.setattr(get_settings(), "app_env", "production")
    res_prod = client.get("/api/v1/public/site").json()
    assert res_prod["has_sample"] is False
