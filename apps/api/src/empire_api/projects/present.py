"""Rows → response shapes for the projects module, with the computed read-only fields
(`display` strings, `directions_url`, tower progress, configuration labels, blockers).

Collaborators: routes*.py call these after the services; display.py formats ₹ and area;
media/queries.py supplies the media fields (gallery, cover, RERA QR, floor plans, photos), which
the callers load and pass in. Nothing here touches the database.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from empire_api.content.schemas_marketing import Faq
from empire_api.media.queries import ProjectMedia
from empire_api.media.schemas import LinkedMedia, Media
from empire_api.projects import display, models
from empire_api.projects.blockers import Blocker
from empire_api.projects.models import PriceColumns, Project
from empire_api.projects.schemas import ProjectAdmin, ProjectAdminSummary
from empire_api.projects.schemas_catalogue import Amenity, City, Locality
from empire_api.projects.schemas_children import (
    Configuration,
    ConstructionUpdate,
    LocationAdvantage,
    PaymentPlan,
    PaymentPlanStage,
    Specification,
    Tower,
)
from empire_api.projects.schemas_shared import (
    Area,
    CityRef,
    LocalityRef,
    Location,
    Price,
    Rera,
    ReraAccount,
    Seo,
    Translations,
)

DIRECTIONS_URL: Final = "https://www.google.com/maps/dir/?api=1&destination={lat},{lng}"
PROPERTY_TYPE_LABELS: Final = {
    "apartment": "Apartment",
    "villa": "Villa",
    "plot": "Plot",
    "penthouse": "Penthouse",
    "shop": "Shop",
    "office": "Office",
    "other": "Other",
}


def _float(value: Decimal | None) -> float | None:
    return None if value is None else float(value)


def price_of(row: PriceColumns) -> Price:
    return Price(
        on_request=row.price_on_request,
        min_inr=row.price_min_inr,
        max_inr=row.price_max_inr,
        rate_inr=row.rate_inr,
        rate_unit=row.rate_unit,
        note=row.price_note,
        display=display.price_display(
            on_request=row.price_on_request,
            min_inr=row.price_min_inr,
            max_inr=row.price_max_inr,
            rate_inr=row.rate_inr,
            rate_unit=row.rate_unit,
        ),
    )


def area_of(
    min_sqm: Decimal | None, max_sqm: Decimal | None, basis: str, display_unit: str
) -> Area:
    return Area(
        min_sqm=_float(min_sqm),
        max_sqm=_float(max_sqm),
        basis=basis,
        display_unit=display_unit,
        display=display.area_display(
            min_sqm=min_sqm, max_sqm=max_sqm, basis=basis, display_unit=display_unit
        ),
    )


def directions_url(lat: Decimal | None, lng: Decimal | None) -> str | None:
    """Google Maps directions to the pin (ARCHITECTURE §13), or None without a pin."""
    if lat is None or lng is None:
        return None
    return DIRECTIONS_URL.format(lat=f"{lat:f}", lng=f"{lng:f}")


def city_ref(city: models.City | None) -> CityRef | None:
    return CityRef(id=city.id, name=city.name, slug=city.slug, state=city.state) if city else None


def locality_ref(locality: models.Locality | None) -> LocalityRef | None:
    if locality is None:
        return None
    return LocalityRef(id=locality.id, name=locality.name, slug=locality.slug)


# --- Children --------------------------------------------------------------------------------


def tower_progress(updates: Iterable[models.ConstructionUpdate]) -> dict[uuid.UUID, int]:
    """tower id → progress % of its latest *published* update that states one."""
    latest: dict[uuid.UUID, models.ConstructionUpdate] = {}
    for update in updates:
        if update.tower_id is None or update.progress_percent is None:
            continue
        if update.publish_state != "published":
            continue
        current = latest.get(update.tower_id)
        if current is None or (update.update_date, update.id) > (current.update_date, current.id):
            latest[update.tower_id] = update
    return {tower_id: int(u.progress_percent or 0) for tower_id, u in latest.items()}


def tower_out(row: models.Tower, progress: int | None) -> Tower:
    return Tower(
        id=row.id,
        name=row.name,
        kind=row.kind,
        floors=row.floors,
        units_count=row.units_count,
        status=row.status,
        rera_number=row.rera_number,
        possession_date=row.possession_date,
        progress_percent=progress,
        sort_order=row.sort_order,
    )


def configuration_out(
    row: models.Configuration, floor_plans: list[LinkedMedia] | None = None
) -> Configuration:
    return Configuration(
        id=row.id,
        slug=row.slug,
        name=row.name,
        tower_id=row.tower_id,
        property_type=row.property_type,
        bhk=_float(row.bhk),
        bathrooms=row.bathrooms,
        balconies=row.balconies,
        area=area_of(row.area_min_sqm, row.area_max_sqm, row.area_basis, row.area_display_unit),
        price=price_of(row),
        sales_status=row.sales_status,
        floor_plans=floor_plans or [],
        sort_order=row.sort_order,
        is_sample=row.is_sample,
        translations=Translations(row.translations),
    )


def specification_out(row: models.Specification) -> Specification:
    return Specification(id=row.id, category=row.category, text=row.text, sort_order=row.sort_order)


def advantage_out(row: models.LocationAdvantage) -> LocationAdvantage:
    return LocationAdvantage(
        id=row.id,
        label=row.label,
        kind=row.kind,
        distance_km=_float(row.distance_km),
        travel_minutes=row.travel_minutes,
        sort_order=row.sort_order,
    )


def update_out(
    row: models.ConstructionUpdate, photos: list[LinkedMedia] | None = None
) -> ConstructionUpdate:
    return ConstructionUpdate(
        id=row.id,
        tower_id=row.tower_id,
        title=row.title,
        update_date=row.update_date,
        progress_percent=row.progress_percent,
        body=row.body,
        photos=photos or [],
        publish_state=row.publish_state,
        sort_order=row.sort_order,
    )


def plan_out(row: models.PaymentPlan) -> PaymentPlan:
    return PaymentPlan(
        id=row.id,
        name=row.name,
        description=row.description,
        stages=[PaymentPlanStage.model_validate(stage) for stage in row.stages],
        is_visible=row.is_visible,
        sort_order=row.sort_order,
    )


# --- Catalogue -------------------------------------------------------------------------------


def amenity_out(row: models.Amenity) -> Amenity:
    return Amenity(
        id=row.id,
        name=row.name,
        slug=row.slug,
        icon=row.icon,
        category=row.category,
    )


def city_out(row: models.City, project_count: int) -> City:
    return City(
        id=row.id, name=row.name, slug=row.slug, state=row.state, project_count=project_count
    )


def locality_out(row: models.Locality, project_count: int) -> Locality:
    return Locality(
        id=row.id,
        city_id=row.city_id,
        name=row.name,
        slug=row.slug,
        project_count=project_count,
    )


# --- Project ---------------------------------------------------------------------------------


def configuration_labels(rows: Iterable[models.Configuration]) -> list[str]:
    """["2 BHK", "3 BHK", "Villa"]: BHK where given, else the property type; each once."""
    labels: list[str] = []
    for row in rows:
        if row.bhk is not None:
            label = f"{float(row.bhk):g} BHK"
        else:
            label = PROPERTY_TYPE_LABELS.get(row.property_type, row.property_type)
        if label not in labels:
            labels.append(label)
    return labels


def _property_types(rows: Iterable[models.Configuration]) -> list[str]:
    seen: list[str] = []
    for row in rows:
        if row.property_type not in seen:
            seen.append(row.property_type)
    return seen


def _rera(project: Project, qr: Media | None) -> Rera:
    """COMPLIANCE (D-002): `qr` is the project's *visible* RERA QR, the one the site shows."""
    return Rera(
        authority=project.rera_authority, number=project.rera_number, url=project.rera_url, qr=qr
    )


def project_summary(
    project: Project, cover: Media | None = None, rera_qr: Media | None = None
) -> ProjectAdminSummary:
    """A CMS list row. Needs `city`, `locality` and `configurations` loaded; the cover (pinned,
    else first visible photo) and the visible RERA QR come from media/queries.py."""
    return ProjectAdminSummary(
        id=project.id,
        slug=project.slug,
        name=project.name,
        status=project.status,
        sales_status=project.sales_status,
        city=city_ref(project.city),
        locality=locality_ref(project.locality),
        price=price_of(project),
        configuration_labels=configuration_labels(project.configurations),
        property_types=_property_types(project.configurations),
        cover=cover,
        rera=_rera(project, rera_qr),
        possession_date=project.possession_date,
        is_featured=project.is_featured,
        is_sample=project.is_sample,
        publish_state=project.publish_state,
        published_at=project.published_at,
        updated_at=project.updated_at,
    )


def _location(project: Project) -> Location:
    return Location(
        address_line=project.address_line,
        city=city_ref(project.city),
        locality=locality_ref(project.locality),
        state=project.state,
        pincode=project.pincode,
        lat=_float(project.lat),
        lng=_float(project.lng),
        google_maps_url=project.google_maps_url,
        plus_code=project.plus_code,
        pin_source=project.pin_source,
        directions_url=directions_url(project.lat, project.lng),
    )


def _land_area(project: Project) -> Area | None:
    if project.land_area_min_sqm is None and project.land_area_max_sqm is None:
        return None
    return area_of(
        project.land_area_min_sqm,
        project.land_area_max_sqm,
        project.land_area_basis or "plot",
        project.land_area_display_unit or "sqft",
    )


def _rera_account(project: Project) -> ReraAccount | None:
    if not (project.rera_bank_name or project.rera_account_name or project.rera_account_number):
        return None
    return ReraAccount(
        bank_name=project.rera_bank_name,
        account_name=project.rera_account_name,
        account_number=project.rera_account_number,
    )


@dataclass(frozen=True)
class AdminMedia:
    """Everything media-backed in ProjectAdmin, loaded by the caller (routes.admin_view)."""

    project: ProjectMedia
    floor_plans: dict[uuid.UUID, list[LinkedMedia]]
    photos: dict[uuid.UUID, list[LinkedMedia]]
    share_image: Media | None


def project_admin(
    project: Project, blockers: list[Blocker], media: AdminMedia, faqs: list[Faq]
) -> ProjectAdmin:
    """The full CMS view of a project with its children, each in its saved order."""
    summary = project_summary(project, media.project.cover, media.project.rera_qr).model_dump(
        exclude={"publish_state", "published_at"}
    )
    progress = tower_progress(project.construction_updates)
    return ProjectAdmin(
        **summary,
        tagline=project.tagline,
        description=project.description,
        project_type=project.project_type,
        land_area=_land_area(project),
        total_units=project.total_units,
        launch_date=project.launch_date,
        location=_location(project),
        towers=[tower_out(t, progress.get(t.id)) for t in project.towers],
        configurations=[
            configuration_out(c, media.floor_plans.get(c.id)) for c in project.configurations
        ],
        amenities=[amenity_out(link.amenity) for link in project.amenity_links],
        specifications=[specification_out(s) for s in project.specifications],
        location_advantages=[advantage_out(a) for a in project.location_advantages],
        construction_updates=[
            update_out(u, media.photos.get(u.id)) for u in project.construction_updates
        ],
        payment_plans=[plan_out(p) for p in project.payment_plans],
        gallery=media.project.gallery,
        videos=media.project.videos,
        documents=media.project.documents,
        brochure=media.project.brochure,
        brochure_gated=project.brochure_gated,
        faqs=faqs,
        seo=Seo.model_validate(project.seo),
        translations=Translations(project.translations),
        publish_state=project.publish_state,
        published_at=project.published_at,
        created_at=project.created_at,
        created_by=project.created_by,
        updated_by=project.updated_by,
        publish_blockers=[b.message for b in blockers],
        rera_account=_rera_account(project),
        featured_order=project.featured_order,
        og_image=media.share_image,
    )
