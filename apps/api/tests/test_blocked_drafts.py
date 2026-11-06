"""The dashboard's blocked drafts: one rule set with the single-project check, in a fixed
number of queries however many drafts there are (task L7a; L1 saw seconds at 1,500 drafts).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from empire_api.media.models import Media, MediaLink
from empire_api.projects import blockers, queries
from empire_api.projects.models import Configuration, Project
from test_public_perf_queries import count_queries


def _draft(db: Session, i: int, *, rera: bool, qr: bool, qr_visible: bool, config: bool) -> Project:
    project = Project(
        slug=f"l7a-draft-{i}-{uuid.uuid4().hex[:6]}",
        name=f"L7a draft {i}",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="draft",
        rera_number=f"UPRERAL7A{i}" if rera else None,
    )
    db.add(project)
    db.flush()
    if config:
        db.add(
            Configuration(
                project_id=project.id,
                slug="home",
                name="2 BHK",
                property_type="apartment",
                bhk=Decimal("2"),
                area_min_sqm=Decimal("100"),
                area_max_sqm=Decimal("100"),
                sort_order=0,
            )
        )
    if qr:
        media = Media(
            kind="image",
            store="cloudinary",
            resource_type="image",
            public_id=f"l7a-qr-{uuid.uuid4().hex[:8]}",
            title="QR",
            version=1,
            format="png",
            bytes=1000,
            width=300,
            height=300,
            created_by=uuid.uuid4(),
        )
        db.add(media)
        db.flush()
        db.add(
            MediaLink(
                media_id=media.id,
                project_id=project.id,
                role="rera_qr",
                sort_order=0,
                is_visible=qr_visible,
                is_cover=False,
            )
        )
    db.flush()
    return project


def test_blocked_drafts_match_the_single_project_rules_in_fixed_queries(db: Session) -> None:
    made: list[Project] = []
    # Every combination of the three facts, plus a hidden QR (which doesn't count, D-002).
    for i in range(8):
        made.append(
            _draft(db, i, rera=bool(i & 1), qr=bool(i & 2), qr_visible=True, config=bool(i & 4))
        )
    made.append(_draft(db, 8, rera=True, qr=True, qr_visible=False, config=True))

    with count_queries() as seen:
        found = {item.ref.id: item.blockers for item in queries.blocked_drafts(db)}
    # The drafts, the visible QR codes, the configurations: three, whatever the number of drafts.
    assert len(seen) == 3, seen

    for project in made:
        expected = blockers.publish_blockers(db, project)
        assert found.get(project.id, []) == expected, project.name
    # The fully ready draft (rera, visible QR, configuration) is not listed.
    assert made[7].id not in found
    hidden_qr = [b.message for b in found[made[8].id]]
    assert hidden_qr == [blockers.RERA_QR_MISSING]
