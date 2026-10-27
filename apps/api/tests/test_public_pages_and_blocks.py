"""Tests for public pages and resolved block rendering (Task 5.1).

Covers:
- Page blocks arrive resolved with everything a block needs (media delivery URL, width, height,
  label, FAQs, offers, consent text).
- Dead references dropped: blocks whose references are gone/hidden/inactive are omitted.
- Empty picks stay empty: an empty pick list is never widened to all items (D-035).
- Landing pages return noindex: true.
- Legal pages return is_draft_text.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from empire_api.content.models import ConsentText, Faq, Offer, Page, PageBlock
from empire_api.media.models import Media


def test_page_blocks_resolved_and_dead_refs_dropped(db: Session, client: TestClient) -> None:
    # 1. Seed library media
    media_item = Media(
        kind="image",
        store="cloudinary",
        resource_type="image",
        public_id=f"page-img-{uuid.uuid4().hex[:6]}",
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
    db.add(media_item)
    db.flush()

    # 2. Seed FAQ
    faq = Faq(
        question="What is the possession timeline?",
        answer="Possession begins December 2027.",
        sort_order=1,
        is_visible=True,
    )
    db.add(faq)
    db.flush()

    # 3. Seed active offer
    offer = Offer(
        title="Festival Offer",
        placement="home",
        is_active=True,
    )
    db.add(offer)
    db.flush()

    # 4. Seed consent text
    consent = ConsentText(
        kind="lead_form",
        version=1,
        body="I agree to receive project updates.",
        checkbox_label="I consent",
        is_current=True,
        published_at=datetime.now(UTC),
    )
    db.add(consent)
    db.flush()

    # 5. Create Page with blocks:
    #   - b1: Valid image block
    #   - b2: Dead image block (non-existent UUID)
    #   - b3: FAQ list block with valid picked FAQ
    #   - b4: FAQ list block with empty faq_ids (empty pick list -> should be dropped per D-035)
    #   - b5: Offer banner with valid offer
    #   - b6: Lead form block
    page = Page(
        slug="test-about",
        title="About Us",
        kind="standard",
        publish_state="published",
    )
    db.add(page)
    db.flush()

    b1 = PageBlock(
        page_id=page.id,
        type="image",
        data={"image_id": str(media_item.id), "caption": "Our vision"},
        sort_order=1,
        is_visible=True,
    )
    b2 = PageBlock(
        page_id=page.id,
        type="image",
        data={"image_id": str(uuid.uuid4()), "caption": "Ghost image"},
        sort_order=2,
        is_visible=True,
    )
    b3 = PageBlock(
        page_id=page.id,
        type="faq_list",
        data={"faq_ids": [str(faq.id)]},
        sort_order=3,
        is_visible=True,
    )
    b4 = PageBlock(
        page_id=page.id,
        type="faq_list",
        data={"faq_ids": []},  # Explicit empty pick list
        sort_order=4,
        is_visible=True,
    )
    b5 = PageBlock(
        page_id=page.id,
        type="offer_banner",
        data={"offer_id": str(offer.id)},
        sort_order=5,
        is_visible=True,
    )
    b6 = PageBlock(
        page_id=page.id,
        type="lead_form",
        data={"source": "about_form"},
        sort_order=6,
        is_visible=True,
    )
    db.add_all([b1, b2, b3, b4, b5, b6])
    db.commit()

    # Fetch public page
    res = client.get("/api/v1/public/pages/test-about")
    assert res.status_code == 200
    data = res.json()

    assert data["slug"] == "test-about"
    assert data["title"] == "About Us"

    # Blocks assertions
    blocks = data["blocks"]
    assert [b["type"] for b in blocks] == ["image", "faq_list", "offer_banner", "lead_form"]

    # b2 (dead image) and b4 (empty faq_ids) must be dropped!
    assert len(blocks) == 4

    # b1: Image block is resolved
    img_b = blocks[0]
    assert img_b["type"] == "image"
    assert "image" in img_b["data"]
    assert img_b["data"]["image"]["id"] == str(media_item.id)
    assert img_b["data"]["image"]["width"] == 1920
    assert img_b["data"]["image"]["label"] == "artist_impression"
    assert "url" in img_b["data"]["image"]

    # b3: FAQ list resolved
    faq_b = blocks[1]
    assert faq_b["type"] == "faq_list"
    assert len(faq_b["data"]["faqs"]) == 1
    assert faq_b["data"]["faqs"][0]["question"] == "What is the possession timeline?"

    # b5: Offer banner resolved
    offer_b = blocks[2]
    assert offer_b["type"] == "offer_banner"
    assert offer_b["data"]["offer"]["title"] == "Festival Offer"

    # b6: Lead form resolved with consent text
    form_b = blocks[3]
    assert form_b["type"] == "lead_form"
    assert form_b["data"]["consent"]["body"] == "I agree to receive project updates."


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
