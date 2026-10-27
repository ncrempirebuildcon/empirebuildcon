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

from empire_api.content.models import Faq, Page, PageBlock
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
    # Seed page with 15 blocks
    page = Page(
        slug="perf-multi-block-page",
        title="Multi Block Page",
        kind="standard",
        publish_state="published",
    )
    db.add(page)
    db.flush()

    # Seed 5 FAQs
    faqs = [
        Faq(question=f"Q{i}?", answer=f"A{i}.", sort_order=i, is_visible=True) for i in range(1, 6)
    ]
    db.add_all(faqs)

    # Seed 5 Media items
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
        for i in range(1, 6)
    ]
    db.add_all(media_items)
    db.flush()

    blocks = []
    # 5 image blocks
    for i, m in enumerate(media_items):
        blocks.append(
            PageBlock(
                page_id=page.id,
                type="image",
                data={"image_id": str(m.id)},
                sort_order=i,
            )
        )
    # 1 FAQ list block referencing all 5 FAQs
    blocks.append(
        PageBlock(
            page_id=page.id,
            type="faq_list",
            data={"faq_ids": [str(f.id) for f in faqs]},
            sort_order=10,
        )
    )
    db.add_all(blocks)
    db.commit()

    # Measure queries on GET /public/pages/{slug}
    with count_queries() as queries:
        res = client.get(f"/api/v1/public/pages/{page.slug}")
        assert res.status_code == 200

    # Ensure query count is strictly bounded (less than 10 queries for 6 blocks with 10 child items)
    assert len(queries) <= 10, f"Expected <= 10 queries for multi-block page, got {len(queries)}"
