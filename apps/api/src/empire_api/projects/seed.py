"""Seed data for the projects module: the default amenity catalogue, and sample projects for
development and demos (`empire-api seed --sample`).

Collaborators: cli.py (`empire-api seed`), models.py.
Implements: D-015 (sample data until real projects arrive), CODE_STYLE §7 (honest seeds).

COMPLIANCE (D-015, AGENTS.md "Honest content"):
  - The amenity catalogue lists generic options staff can pick, not claims about any project.
  - Sample rows say "Sample" in their names, carry `is_sample = true`, use RERA placeholders
    like UPRERAPRJ-SAMPLE-01 and `[bracketed]` placeholders for every fact, and stay drafts.
  - `seed_sample` refuses to run when APP_ENV is production, and publishing a sample is
    blocked there too (blockers.py).
Both seeds are idempotent: rows are matched by slug and existing rows are never changed, so
staff edits survive a re-run.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.projects.common import slugify
from empire_api.projects.models import (
    Amenity,
    City,
    Configuration,
    ConstructionUpdate,
    Locality,
    LocationAdvantage,
    PaymentPlan,
    Project,
    ProjectAmenity,
    Specification,
    Tower,
)

# (name, icon key, category). WHY plain icon keys: handbook/DESIGN_SYSTEM.md §6 sets the icon
# style but no named icon set yet; the web app maps these keys to its line icons.
DEFAULT_AMENITIES: Final = (
    ("Swimming pool", "swimming-pool", "lifestyle"),
    ("Gym", "gym", "sports"),
    ("Clubhouse", "clubhouse", "lifestyle"),
    ("Children's play area", "play-area", "kids"),
    ("Power backup", "power-backup", "convenience"),
    ("24×7 security", "security", "security"),
    ("Landscaped garden", "garden", "green"),
    ("Jogging track", "jogging-track", "sports"),
    ("Car parking", "parking", "convenience"),
    ("Lift", "lift", "convenience"),
    ("Rainwater harvesting", "rainwater-harvesting", "green"),
    ("CCTV", "cctv", "security"),
)

SQM_PER_SQFT: Final = Decimal("0.092903")


class SampleRefusedError(RuntimeError):
    """Sample data is never added in production (D-015)."""


@dataclass(frozen=True)
class SampleResult:
    projects_added: int
    projects_skipped: int


def seed_amenities(db: Session) -> int:
    """Add missing catalogue amenities. Returns how many were added. Caller commits."""
    existing = set(db.scalars(select(Amenity.slug)))
    added = 0
    for name, icon, category in DEFAULT_AMENITIES:
        slug = slugify(name)
        if slug not in existing:
            db.add(Amenity(name=name, slug=slug, icon=icon, category=category))
            added += 1
    return added


def _sqm(sqft: int) -> Decimal:
    return (sqft * SQM_PER_SQFT).quantize(Decimal("0.01"))


def _get_or_add(db: Session, model: type[Any], lookup: dict[str, Any], **values: Any) -> Any:
    row = db.scalar(select(model).filter_by(**lookup))
    if row is None:
        row = model(**lookup, **values)
        db.add(row)
        db.flush()
    return row


def seed_sample(db: Session) -> SampleResult:
    """Add Sample City, a locality and "Sample — Project A/B" with their children.

    Raises:
        SampleRefusedError: APP_ENV is production.
    """
    if get_settings().app_env == "production":
        raise SampleRefusedError("Sample data is never added in production (D-015).")
    seed_amenities(db)
    db.flush()
    city = _get_or_add(db, City, {"slug": "sample-city"}, name="Sample City", state="Uttar Pradesh")
    locality = _get_or_add(
        db, Locality, {"city_id": city.id, "slug": "sample-locality"}, name="Sample Locality"
    )
    amenities = list(db.scalars(select(Amenity).order_by(Amenity.name)))
    added = skipped = 0
    for build in (_project_a, _project_b):
        project = build(city, locality)
        if db.scalar(select(Project.id).where(Project.slug == project.slug)) is not None:
            skipped += 1
            continue
        db.add(project)
        db.flush()
        _children(db, project, amenities)
        added += 1
    return SampleResult(projects_added=added, projects_skipped=skipped)


def _base(slug: str, name: str, city: City, locality: Locality, number: str) -> dict[str, Any]:
    return {
        "slug": slug,
        "name": name,
        "tagline": "SAMPLE — [Tagline written by Empire's team]",
        "description": (
            "SAMPLE — [Two or three plain sentences about the project, written by Empire's "
            "team.]\n- [Key feature]\n- [Key feature]"
        ),
        "rera_authority": "UP-RERA",
        "rera_number": f"UPRERAPRJ-SAMPLE-{number}",
        "rera_url": "https://www.up-rera.in",
        "address_line": "[Plot no.], [Sector], Sample Locality",
        "city_id": city.id,
        "locality_id": locality.id,
        "state": city.state,
        "publish_state": "draft",
        "is_sample": True,
        "seo": {"title": f"{name} | Empire", "noindex": True},
    }


def _project_a(city: City, locality: Locality) -> Project:
    return Project(
        **_base("sample-project-a", "Sample — Project A", city, locality, "01"),
        status="ongoing",
        sales_status="available",
        project_type="residential",
        possession_date=date(2029, 6, 30),
        price_min_inr=78_00_000,
        price_max_inr=1_25_00_000,
    )


def _project_b(city: City, locality: Locality) -> Project:
    return Project(
        **_base("sample-project-b", "Sample — Project B", city, locality, "02"),
        status="completed",
        sales_status="available",
        project_type="plots",
        price_on_request=True,
        land_area_min_sqm=_sqm(2_17_800),
        land_area_basis="plot",
        land_area_display_unit="sqft",
    )


def _children(db: Session, project: Project, amenities: list[Amenity]) -> None:
    """Towers, configurations and the rest, all marked as samples or with [placeholders]."""
    is_a = project.slug == "sample-project-a"
    first = Tower(
        project_id=project.id,
        name="Tower A" if is_a else "Phase 1",
        kind="tower" if is_a else "phase",
        floors=16 if is_a else None,
        status="under_construction" if is_a else "completed",
        sort_order=0,
    )
    db.add(first)
    if is_a:
        db.add(Tower(project_id=project.id, name="Tower B", kind="tower", floors=16, sort_order=1))
    db.flush()
    for order, (name, kind, bhk, sqft, low, high, status) in enumerate(_configurations(is_a)):
        db.add(
            Configuration(
                project_id=project.id,
                tower_id=first.id,
                slug=slugify(name),
                name=name,
                property_type=kind,
                bhk=bhk,
                area_min_sqm=_sqm(sqft[0]),
                area_max_sqm=_sqm(sqft[1]),
                area_basis="carpet" if kind == "apartment" else "plot",
                area_display_unit="sqft" if kind == "apartment" else "sqyd",
                price_min_inr=low,
                price_max_inr=high,
                sales_status=status,
                sort_order=order,
                is_sample=True,
            )
        )
    _details(db, project, first, amenities)


def _configurations(is_a: bool) -> list[tuple[Any, ...]]:
    if is_a:
        return [
            ("2 BHK", "apartment", Decimal(2), (720, 780), 78_00_000, 86_00_000, "available"),
            ("3 BHK", "apartment", Decimal(3), (980, 1120), 1_08_00_000, 1_25_00_000, "available"),
        ]
    return [
        ("Plot 150 sq yd", "plot", None, (1350, 1350), None, None, "available"),
        ("Plot 200 sq yd", "plot", None, (1800, 1800), None, None, "sold_out"),
    ]


def _details(db: Session, project: Project, tower: Tower, amenities: list[Amenity]) -> None:
    db.add_all(
        [
            Specification(
                project_id=project.id, category="Flooring", text="[Flooring finish]", sort_order=0
            ),
            Specification(
                project_id=project.id, category="Kitchen", text="[Kitchen fittings]", sort_order=1
            ),
            LocationAdvantage(
                project_id=project.id,
                label="[Nearest metro station]",
                kind="transport",
                distance_km=Decimal("1.8"),
                travel_minutes=6,
                sort_order=0,
            ),
            LocationAdvantage(
                project_id=project.id,
                label="[School name]",
                kind="school",
                distance_km=Decimal("1.0"),
                sort_order=1,
            ),
            ConstructionUpdate(
                project_id=project.id,
                tower_id=tower.id,
                title=f"SAMPLE — {tower.name} progress",
                update_date=date(2026, 9, 30),
                progress_percent=40,
                body="[What changed this month, tower by tower]",
                publish_state="published",
                sort_order=0,
            ),
            PaymentPlan(
                project_id=project.id,
                name="Construction-linked plan (sample)",
                description="[Plan notes]",
                stages=[
                    {"label": "On booking", "percent": 10, "sort_order": 0},
                    {"label": "[Construction milestone]", "percent": 40, "sort_order": 1},
                    {"label": "[Construction milestone]", "percent": 30, "sort_order": 2},
                    {"label": "On possession", "percent": 20, "sort_order": 3},
                ],
                sort_order=0,
            ),
        ]
    )
    db.add_all(
        ProjectAmenity(project_id=project.id, amenity_id=amenity.id, sort_order=order)
        for order, amenity in enumerate(amenities[:6])
    )
    db.flush()
