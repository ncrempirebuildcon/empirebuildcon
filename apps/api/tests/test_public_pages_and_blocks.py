"""Tests for public pages and resolved block rendering (Task 5.1).

Covers:
- Page blocks arrive resolved with everything a block needs (media delivery URL, width, height,
  label, FAQs, offers, consent text, map coordinates, video delivery URL).
- Stored block shapes (faq_ids: [], testimonial_ids: []) resolve auto items (M2).
- Dead references dropped: blocks whose references are gone/hidden/inactive are omitted.
- Block resolvers (M3):
  - offer_banner with placement.
  - map with project coordinates/address and visibility gating.
  - video with media_id library resolution.
  - lead_form with dual consent (lead_form + marketing) and visibility gating.
- Testimonial privacy: stripped consent_date, source_url, project_id (S12).
- Testimonials limit honored (default 3) (M2).
- Hindi translation for picked FAQs (S7).
- Landing pages return noindex: true.
- Legal pages return is_draft_text.
- Resolved OG image delivery URL in SEO (S13).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from empire_api.content.models import ConsentText, Faq, Offer, Page, PageBlock, Testimonial
from empire_api.media.models import Media
from empire_api.projects.models import City, Locality, Project
from empire_api.site_settings.models import FeatureFlag


def test_page_blocks_resolution_and_stored_shapes(db: Session, client: TestClient) -> None:
    # 1. Seed library media (image & video)
    hero_img = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"page-hero-{uuid.uuid4().hex[:6]}",
        title="Page Hero Image",
        alt_text="A grand facade",
        label="artist_impression",
        version=1,
        format="jpg",
        bytes=2048,
        width=1920,
        height=1080,
        created_by=uuid.uuid4(),
    )
    og_img = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"page-og-{uuid.uuid4().hex[:6]}",
        title="OG Image",
        alt_text="OG Social Share",
        label="artist_impression",
        version=1,
        format="jpg",
        bytes=1024,
        width=1200,
        height=630,
        created_by=uuid.uuid4(),
    )
    promo_vid = Media(
        kind="video",
        store="cloudinary",
        resource_type="video",
        public_id=f"promo-vid-{uuid.uuid4().hex[:6]}",
        title="Promo Video",
        alt_text="Video walkthrough",
        label=None,
        version=1,
        format="mp4",
        bytes=1048576,
        width=1280,
        height=720,
        duration_s=Decimal("45.00"),
        created_by=uuid.uuid4(),
    )
    db.add_all([hero_img, og_img, promo_vid])
    db.flush()

    # 2. Seed city, locality and project
    city = City(name="Noida", slug=f"noida-{uuid.uuid4().hex[:4]}", state="UP")
    db.add(city)
    db.flush()
    loc = Locality(name="Sector 150", slug=f"sec150-{uuid.uuid4().hex[:4]}", city_id=city.id)
    db.add(loc)
    db.flush()
    proj = Project(
        name="Empire Heights",
        slug=f"heights-{uuid.uuid4().hex[:4]}",
        tagline="Luxury green living",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=loc.id,
        rera_number="UPRERA12345",
        lat=Decimal("28.4595"),
        lng=Decimal("77.5020"),
        address_line="Sector 150 Expressway",
        price_min_inr=10_000_000,
    )

    db.add(proj)
    db.flush()

    # 3. Seed FAQs: one picked with Hindi translation, one site-wide
    faq_picked = Faq(
        question="What is the possession timeline?",
        answer="Possession begins December 2027.",
        translations={"hi": {"question": "कब्ज़ा कब मिलेगा?", "answer": "दिसंबर 2027 में।"}},
        sort_order=1,
        is_visible=True,
    )
    faq_general = Faq(
        question="Are home loans available?",
        answer="Yes, all major banks approve loans.",
        sort_order=2,
        is_visible=True,
    )
    db.add_all([faq_picked, faq_general])
    db.flush()

    # 4. Seed Testimonials: 4 testimonials to test limit (default 3)
    t_items = []
    for i in range(4):
        t = Testimonial(
            person_name=f"Customer {i + 1}",
            person_detail="Homeowner",
            quote=f"Great experience purchasing my home {i + 1}.",
            source="google",
            source_url="https://google.com/review/123",
            consent_date=datetime.now(UTC).date(),
            is_visible=True,
            project_id=proj.id,
        )
        t_items.append(t)
    db.add_all(t_items)
    db.flush()

    # 5. Seed active offer with placement
    offer_p = Offer(
        title="Festive Cashback",
        placement="home",
        is_active=True,
    )
    db.add(offer_p)
    db.flush()

    # 6. Seed dual consent texts
    c_lead = ConsentText(
        kind="lead_form",
        version=1,
        body="I agree to receive project updates.",
        checkbox_label="I consent",
        is_current=True,
        published_at=datetime.now(UTC),
    )
    c_mkt = ConsentText(
        kind="marketing",
        version=1,
        body="I agree to receive marketing brochures via WhatsApp.",
        checkbox_label="Optional WhatsApp updates",
        is_current=True,
        published_at=datetime.now(UTC),
    )
    db.add_all([c_lead, c_mkt])
    db.flush()

    # 7. Create Page with blocks
    page = Page(
        slug="test-full-blocks",
        title="Full Blocks Test Page",
        kind="standard",
        publish_state="published",
        seo={"title": "Page SEO", "og_image_id": str(og_img.id)},
    )
    db.add(page)
    db.flush()

    # Blocks:
    # 1. Valid image block
    b1 = PageBlock(
        page_id=page.id,
        type="image",
        data={"image_id": str(hero_img.id), "caption": "Our vision"},
        sort_order=1,
    )
    # 2. Dead image block (must be dropped)
    b2 = PageBlock(
        page_id=page.id,
        type="image",
        data={"image_id": str(uuid.uuid4())},
        sort_order=2,
    )
    # 3. Picked FAQ list with faq_ids non-empty
    b3 = PageBlock(
        page_id=page.id,
        type="faq_list",
        data={"faq_ids": [str(faq_picked.id)]},
        sort_order=3,
    )
    # 4. Auto FAQ list with stored shape faq_ids: [] (resolves site-wide FAQs, M2)
    b4 = PageBlock(
        page_id=page.id,
        type="faq_list",
        data={"faq_ids": [], "project_id": None},
        sort_order=4,
    )
    # 5. Testimonials block with stored shape testimonial_ids: [] (resolves latest, max 3, M2)
    b5 = PageBlock(
        page_id=page.id,
        type="testimonials",
        data={"testimonial_ids": []},
        sort_order=5,
    )
    # 6. Offer banner with placement="home" (M3)
    b6 = PageBlock(
        page_id=page.id,
        type="offer_banner",
        data={"placement": "home"},
        sort_order=6,
    )
    # 7. Map block with published project (M3)
    b7 = PageBlock(
        page_id=page.id,
        type="map",
        data={"project_id": str(proj.id)},
        sort_order=7,
    )
    # 8. Video block with library media_id (M3)
    b8 = PageBlock(
        page_id=page.id,
        type="video",
        data={"media_id": str(promo_vid.id)},
        sort_order=8,
    )
    # 9. Lead form block with published project (M3)
    b9 = PageBlock(
        page_id=page.id,
        type="lead_form",
        data={"project_id": str(proj.id), "source": "project_form"},
        sort_order=9,
    )
    db.add_all([b1, b2, b3, b4, b5, b6, b7, b8, b9])
    db.commit()

    # Query public page (English)
    res = client.get("/api/v1/public/pages/test-full-blocks")
    assert res.status_code == 200
    data = res.json()

    # Verify SEO OG image resolution (S13)
    assert data["seo"] is not None
    assert data["seo"]["og_image"] is not None
    assert data["seo"]["og_image"]["id"] == str(og_img.id)
    assert data["seo"]["og_image"]["width"] == 1200
    assert "url" in data["seo"]["og_image"]

    blocks = data["blocks"]
    # b2 (dead image) is dropped. b1, b3, b4, b5, b6, b7, b8, b9 should all be resolved (8 blocks)
    assert len(blocks) == 8
    block_types = [b["type"] for b in blocks]
    assert block_types == [
        "image",
        "faq_list",
        "faq_list",
        "testimonials",
        "offer_banner",
        "map",
        "video",
        "lead_form",
    ]

    # Verify b3 (picked FAQ)
    assert blocks[1]["data"]["faqs"][0]["question"] == "What is the possession timeline?"

    # Verify b4 (auto FAQ list) resolved site-wide FAQs
    assert len(blocks[2]["data"]["faqs"]) >= 2

    # Verify b5 (testimonials) honours limit 3 (M2) and strips consent/source/project_id (S12)
    t_res = blocks[3]["data"]["testimonials"]
    assert len(t_res) == 3  # Honoured limit 3!
    for t_item in t_res:
        assert "person_name" in t_item
        assert "quote" in t_item
        # S12: dropped sensitive internal fields
        assert "consent_date" not in t_item
        assert "source_url" not in t_item
        assert "project_id" not in t_item

    # Verify b6 (offer banner with placement)
    assert blocks[4]["data"]["offer"]["title"] == "Festive Cashback"

    # Verify b7 (map) resolved coordinates and address
    map_data = blocks[5]["data"]["project"]
    assert map_data["lat"] == 28.4595
    assert map_data["lng"] == 77.5020
    assert "Sector 150 Expressway" in map_data["address"]
    assert "directions_url" in map_data

    # Verify b8 (video) resolved delivery URL
    vid_data = blocks[6]["data"]["media"]
    assert vid_data["id"] == str(promo_vid.id)
    assert "url" in vid_data
    assert vid_data["width"] == 1280

    # Verify b9 (lead form) attached dual consent (lead_form + marketing)
    form_data = blocks[7]["data"]
    assert form_data["consent"]["body"] == "I agree to receive project updates."
    assert form_data["marketing_consent"] is not None
    assert "WhatsApp" in form_data["marketing_consent"]["checkbox_label"]

    # Query in Hindi: verify picked FAQ translation (S7)
    # Enable locale_hi feature flag first (D-014 gating)
    flag = db.get(FeatureFlag, "locale_hi")
    if not flag:
        flag = FeatureFlag(key="locale_hi", enabled=True, description="Hindi pages")
        db.add(flag)
    else:
        flag.enabled = True
    db.commit()

    res_hi = client.get("/api/v1/public/pages/test-full-blocks?locale=hi")
    assert res_hi.status_code == 200
    data_hi = res_hi.json()
    b3_hi = data_hi["blocks"][1]
    assert b3_hi["data"]["faqs"][0]["question"] == "कब्ज़ा कब मिलेगा?"
    assert b3_hi["data"]["faqs"][0]["answer"] == "दिसंबर 2027 में।"


def test_blocks_with_draft_project_are_dropped(db: Session, client: TestClient) -> None:
    # Test that map and lead_form blocks referencing draft/unpublished projects are dropped (M3)
    city = City(name="Kanpur", slug=f"kanpur-{uuid.uuid4().hex[:4]}", state="UP")
    db.add(city)
    db.flush()
    draft_proj = Project(
        name="Secret Draft Project",
        slug=f"draft-{uuid.uuid4().hex[:4]}",
        tagline="Coming soon",
        project_type="residential",
        status="upcoming",
        publish_state="draft",  # DRAFT!
        city_id=city.id,
        lat=Decimal("26.4499"),
        lng=Decimal("80.3319"),
    )
    db.add(draft_proj)
    db.flush()

    page = Page(
        slug=f"draft-ref-page-{uuid.uuid4().hex[:4]}",
        title="Draft Reference Test",
        kind="standard",
        publish_state="published",
    )
    db.add(page)
    db.flush()

    b_map = PageBlock(
        page_id=page.id,
        type="map",
        data={"project_id": str(draft_proj.id)},
        sort_order=1,
    )
    b_form = PageBlock(
        page_id=page.id,
        type="lead_form",
        data={"project_id": str(draft_proj.id)},
        sort_order=2,
    )
    db.add_all([b_map, b_form])
    db.commit()

    res = client.get(f"/api/v1/public/pages/{page.slug}")
    assert res.status_code == 200
    # Both blocks should be dropped because project is draft!
    assert len(res.json()["blocks"]) == 0


def test_landing_page_noindex(db: Session, client: TestClient) -> None:
    landing = Page(
        slug="autumn-campaign",
        title="Autumn Campaign Landing",
        kind="landing",
        publish_state="published",
        seo={"title": "Special Campaign"},
    )
    db.add(landing)
    db.commit()

    res = client.get("/api/v1/public/pages/autumn-campaign")
    assert res.status_code == 200
    data = res.json()
    assert data["seo"]["noindex"] is True


def test_legal_page_draft_marker(db: Session, client: TestClient) -> None:
    # 1. Legal page with draft text
    legal_draft = Page(
        slug="privacy-draft",
        title="Privacy Policy",
        kind="legal",
        legal_version="v0.1-draft",
        publish_state="published",
    )
    b_draft = PageBlock(
        page_id=legal_draft.id,
        type="rich_text",
        data={"body": "[DRAFT: This is a placeholder legal draft subject to review]"},
        sort_order=1,
    )
    legal_draft.blocks.append(b_draft)

    # 2. Legal page with final text
    legal_final = Page(
        slug="terms-final",
        title="Terms of Service",
        kind="legal",
        legal_version="v1.0",
        publish_state="published",
    )
    b_final = PageBlock(
        page_id=legal_final.id,
        type="rich_text",
        data={"body": "Final binding terms of service."},
        sort_order=1,
    )
    legal_final.blocks.append(b_final)

    db.add_all([legal_draft, legal_final])
    db.commit()

    res_draft = client.get("/api/v1/public/pages/privacy-draft").json()
    assert res_draft["is_draft_text"] is True

    res_final = client.get("/api/v1/public/pages/terms-final").json()
    assert res_final["is_draft_text"] is False
