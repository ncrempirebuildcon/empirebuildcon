"""Performance tests for public endpoints ensuring bounded query counts (Task 5.1).

Covers:
- Project detail does NOT run a query per item (children, media, configs, towers, amenities).
- Multi-block page does NOT run a query per block or media item (batch-loaded entities).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from empire_api.content.models import Faq, Offer, Page, PageBlock, Post
from empire_api.db import get_engine
from empire_api.media.models import Media, MediaLink
from empire_api.projects.models import City, Configuration, Locality, Project, Tower


@contextmanager
def count_queries() -> Iterator[list[str]]:
    engine = get_engine()
    queries: list[str] = []

    def callback(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        queries.append(statement)

    event.listen(engine, "before_cursor_execute", callback)
    try:
        yield queries
    finally:
        event.remove(engine, "before_cursor_execute", callback)


def test_project_detail_query_count_bounded(db: Session, client: TestClient) -> None:
    # 1. Seed project with multiple towers, configurations, and media
    city = db.scalar(select(City).where(City.slug == "perf-lucknow"))
    if not city:
        city = City(name="Lucknow", slug="perf-lucknow", state="UP")
        db.add(city)
        db.flush()

    locality = db.scalar(select(Locality).where(Locality.slug == "perf-gomti"))
    if not locality:
        locality = Locality(name="Gomti Nagar", slug="perf-gomti", city_id=city.id)
        db.add(locality)
        db.flush()

    p = Project(
        slug="perf-huge-project",
        name="Huge Project",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERAPERF01",
    )
    db.add(p)
    db.flush()

    # Add 5 towers
    towers = [
        Tower(project_id=p.id, name=f"Tower {i}", kind="tower", sort_order=i) for i in range(1, 6)
    ]
    db.add_all(towers)

    # Add 10 configurations
    configs = [
        Configuration(
            project_id=p.id,
            slug=f"config-{i}",
            name=f"{i} BHK Premium",
            property_type="apartment",
            bhk=Decimal(str(i)),
            area_min_sqm=Decimal("100"),
            area_max_sqm=Decimal("150"),
            sort_order=i,
        )
        for i in range(1, 11)
    ]
    db.add_all(configs)

    # Add 10 gallery photos
    media_items = [
        Media(
            kind="image",
            store="cloudinary",
            resource_type="image",
            public_id=f"perf-img-{i}-{uuid.uuid4().hex[:6]}",
            title=f"Photo {i}",
            label="artist_impression",
            version=1,
            format="jpg",
            bytes=1000,
            width=800,
            height=600,
            created_by=uuid.uuid4(),
        )
        for i in range(1, 11)
    ]
    db.add_all(media_items)
    db.flush()

    links = [
        MediaLink(
            media_id=m.id,
            project_id=p.id,
            role="gallery",
            sort_order=i,
            is_visible=True,
            is_cover=(i == 0),
        )
        for i, m in enumerate(media_items)
    ]
    db.add_all(links)
    db.commit()

    # Measure queries on GET /public/projects/{slug}
    with count_queries() as queries:
        res = client.get(f"/api/v1/public/projects/{p.slug}")
        assert res.status_code == 200

    # Ensure query count is strictly bounded (less than 15 queries despite 25+ child objects)
    assert len(queries) <= 15, f"Expected <= 15 queries for project detail, got {len(queries)}"


def test_multi_block_page_query_count_bounded(db: Session, client: TestClient) -> None:
    # 1. Seed city, locality, media
    city = db.scalar(select(City).where(City.slug == "perf-lucknow-grid"))
    if not city:
        city = City(name="Lucknow Grid", slug="perf-lucknow-grid", state="UP")
        db.add(city)
        db.flush()

    locality = db.scalar(select(Locality).where(Locality.slug == "perf-gomti-grid"))
    if not locality:
        locality = Locality(name="Gomti Grid", slug="perf-gomti-grid", city_id=city.id)
        db.add(locality)
        db.flush()

    # Seed 5 Media items for gallery and blocks
    media_items = [
        Media(
            kind="image",
            store="cloudinary",
            resource_type="image",
            public_id=f"perf-page-img-{i}-{uuid.uuid4().hex[:6]}",
            title=f"Page Photo {i}",
            label="artist_impression",
            version=1,
            format="jpg",
            bytes=1000,
            width=800,
            height=600,
            created_by=uuid.uuid4(),
        )
        for i in range(1, 10)
    ]
    db.add_all(media_items)
    db.flush()

    # Seed 4 published Projects with Configurations and MediaLinks
    projects = []
    configs = []
    links = []
    for i in range(1, 5):
        p = Project(
            slug=f"perf-grid-proj-{i}-{uuid.uuid4().hex[:4]}",
            name=f"Perf Grid Project {i}",
            project_type="residential",
            status="ongoing",
            sales_status="available",
            publish_state="published",
            city_id=city.id,
            locality_id=locality.id,
            rera_number=f"UPRERAGRID00{i}",
            price_min_inr=5_000_000 * i,
            price_max_inr=10_000_000 * i,
        )
        projects.append(p)
        db.add(p)
        db.flush()

        cfg = Configuration(
            project_id=p.id,
            name=f"{i} BHK Premium Suite",
            slug=f"perf-grid-cfg-{i}-{uuid.uuid4().hex[:4]}",
            property_type="apartment",
            bhk=float(i),
            sales_status="available",
            price_min_inr=5_000_000 * i,
            price_max_inr=6_000_000 * i,
            area_min_sqm=Decimal(f"{50 * i}.0"),
            area_max_sqm=Decimal(f"{60 * i}.0"),
        )
        configs.append(cfg)
        db.add(cfg)
        db.flush()

        ml = MediaLink(
            media_id=media_items[i - 1].id,
            project_id=p.id,
            role="gallery",
            sort_order=1,
            is_visible=True,
            is_cover=True,
        )
        links.append(ml)

    db.add_all(links)
    db.flush()

    # Seed 5 site-wide FAQs and 1 project-linked FAQ
    faqs = [
        Faq(question=f"Q{i}?", answer=f"A{i}.", sort_order=i, is_visible=True) for i in range(1, 6)
    ]
    project_faq = Faq(
        question="Project FAQ?",
        answer="Project Answer.",
        sort_order=10,
        is_visible=True,
        project_id=projects[0].id,
    )
    faqs.append(project_faq)
    db.add_all(faqs)
    db.flush()

    # Seed an active placement Offer for home
    offer = Offer(
        title="Exclusive Festive Offer",
        placement="home",
        is_active=True,
        priority=1,
        project_id=projects[0].id,
    )
    db.add(offer)
    db.flush()

    # Seed page with 15 blocks
    page = Page(
        slug=f"perf-multi-block-page-{uuid.uuid4().hex[:4]}",
        title="Multi Block Page",
        kind="standard",
        publish_state="published",
    )
    db.add(page)
    db.flush()

    blocks = []
    # 5 image blocks
    for i in range(5):
        blocks.append(
            PageBlock(
                page_id=page.id,
                type="image",
                data={"image_id": str(media_items[i].id)},
                sort_order=i,
            )
        )
    # 1 FAQ list block referencing all FAQs (including project-linked)
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="faq_list",
            data={"faq_ids": [str(f.id) for f in faqs]},
            sort_order=10,
        )
    )
    # 1 auto FAQ list block
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="faq_list",
            data={"faq_ids": []},
            sort_order=11,
        )
    )
    # 2 distinct project grid blocks (S9: distinct limits batched into single query)
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="project_grid",
            data={"limit": 2},
            sort_order=12,
        )
    )
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="project_grid",
            data={"limit": 4},
            sort_order=13,
        )
    )
    # 2 distinct property grid blocks (S9: distinct limits batched into single query)
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="property_grid",
            data={"limit": 2},
            sort_order=14,
        )
    )
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="property_grid",
            data={"limit": 4},
            sort_order=15,
        )
    )
    # 1 placement offer_banner block
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="offer_banner",
            data={"placement": "home"},
            sort_order=16,
        )
    )
    db.add_all(blocks)
    db.commit()

    # Measure queries on GET /public/pages/{slug}
    with count_queries() as queries:
        res = client.get(f"/api/v1/public/pages/{page.slug}")
        assert res.status_code == 200

    # Ensure grids return actual items (N7) and query count is strictly bounded
    body = res.json()
    proj_blocks = [b for b in body["blocks"] if b["type"] == "project_grid"]
    prop_blocks = [b for b in body["blocks"] if b["type"] == "property_grid"]
    assert len(proj_blocks) == 2
    assert len(proj_blocks[0]["data"]["projects"]) > 0
    assert len(proj_blocks[1]["data"]["projects"]) > 0
    assert len(prop_blocks) == 2
    assert len(prop_blocks[0]["data"]["properties"]) > 0
    assert len(prop_blocks[1]["data"]["properties"]) > 0

    msg = f"Expected <= 15 queries for multi-block page, got {len(queries)}"
    assert len(queries) <= 15, msg


def test_post_list_og_images_query_count_bounded(db: Session, client: TestClient) -> None:
    """R2-S4: Listing posts with share images must batch-load og_images without N+1 queries."""
    # Seed 10 media items for share images
    media_items = [
        Media(
            kind="image",
            store="cloudinary",
            resource_type="image",
            public_id=f"perf-og-img-{i}-{uuid.uuid4().hex[:6]}",
            title=f"OG Photo {i}",
            label="artist_impression",
            version=1,
            format="jpg",
            bytes=1000,
            width=1200,
            height=630,
            created_by=uuid.uuid4(),
        )
        for i in range(1, 11)
    ]
    db.add_all(media_items)
    db.flush()

    posts = [
        Post(
            slug=f"perf-post-seo-{i}-{uuid.uuid4().hex[:4]}",
            title=f"Post Title {i}",
            body=f"Post Body {i}",
            publish_state="published",
            seo={"title": f"SEO Title {i}", "og_image_id": str(media_items[i - 1].id)},
        )
        for i in range(1, 11)
    ]
    db.add_all(posts)
    db.commit()

    with count_queries() as queries:
        res = client.get("/api/v1/public/posts?per_page=10")
        assert res.status_code == 200

    # Query count must remain bounded (count, posts, covers, authors, og_images <= 6 queries)
    assert len(queries) <= 6, (
        f"Expected <= 6 queries for post list with share images, got {len(queries)}"
    )
