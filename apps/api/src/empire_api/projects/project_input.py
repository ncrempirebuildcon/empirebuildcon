"""From a project request body to column values, and the rules that span several fields.

Collaborators: service.py (create and update), schemas.py (ProjectInput, ProjectUpdate).
Implements: ARCHITECTURE §6 (money in whole rupees, area in square metres, min ≤ max), §13
(pin source), D-002 (RERA number while published).

WHY validation runs on merged values: a PATCH may send only `{"price": {"min_inr": …}}`, so
"min ≤ max" can only be checked against the stored maximum. Everything is checked before any
column is changed, so a 422 never leaves a half-applied edit in the session.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Final

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.projects.common import (
    FieldError,
    check_area,
    check_price,
    conflict,
    invalid,
    jsonable,
    price_columns,
    to_sqm,
)
from empire_api.projects.models import City, Locality, Project

SLUG_TAKEN: Final = "Another project already uses this web address. Choose a different one."

_PLAIN: Final = (
    "name",
    "slug",
    "tagline",
    "description",
    "status",
    "sales_status",
    "project_type",
    "rera_authority",
    "rera_number",
    "rera_url",
    "possession_date",
    "launch_date",
    "total_units",
    "is_featured",
    "featured_order",
    "brochure_gated",
)
_LAND: Final = {
    "min_sqm": "land_area_min_sqm",
    "max_sqm": "land_area_max_sqm",
    "basis": "land_area_basis",
    "display_unit": "land_area_display_unit",
}
_ACCOUNT: Final = {
    "bank_name": "rera_bank_name",
    "account_name": "rera_account_name",
    "account_number": "rera_account_number",
}
_LOCATION: Final = (
    "address_line",
    "city_id",
    "locality_id",
    "state",
    "pincode",
    "lat",
    "lng",
    "google_maps_url",
    "plus_code",
    "pin_source",
)


def columns(db: Session, project: Project | None, sent: Mapping[str, Any]) -> dict[str, Any]:
    """API body (possibly partial) → column values. Nested objects only change what they send."""
    changes = {key: sent[key] for key in _PLAIN if key in sent}
    if "price" in sent:
        changes.update(price_columns(sent["price"]))
    if "land_area" in sent:
        changes.update(_land_columns(project, sent["land_area"]))
    if "rera_account" in sent:
        account = sent["rera_account"] or {}
        changes.update({column: account.get(key) for key, column in _ACCOUNT.items()})
    if "location" in sent:
        changes.update(_location_columns(db, sent["location"]))
    if "seo" in sent:
        changes["seo"] = {**(project.seo if project else {}), **jsonable(sent["seo"])}
    if "translations" in sent:
        changes["translations"] = sent["translations"]
    return changes


def _land_columns(project: Project | None, sent: Mapping[str, Any] | None) -> dict[str, Any]:
    if sent is None:
        return dict.fromkeys(_LAND.values())
    out: dict[str, Any] = {}
    for key in ("min_sqm", "max_sqm"):
        if key in sent:
            out[_LAND[key]] = to_sqm(sent[key])
    # WHY "plot": a project's land area is a site area, never a carpet area.
    out["land_area_basis"] = sent.get("basis") or (project and project.land_area_basis) or "plot"
    out["land_area_display_unit"] = (
        sent.get("display_unit") or (project and project.land_area_display_unit) or "sqft"
    )
    return out


def _location_columns(db: Session, sent: Mapping[str, Any]) -> dict[str, Any]:
    out = {key: sent[key] for key in _LOCATION if key in sent}
    for key in ("lat", "lng"):
        if out.get(key) is not None:
            out[key] = Decimal(str(round(out[key], 6)))  # six decimals ≈ 11 cm
    if ("lat" in out or "lng" in out) and "pin_source" not in out:
        out["pin_source"] = "manual"  # typed by hand unless the client says otherwise
    if "lat" in out and out["lat"] is None and out.get("lng") is None:
        out["pin_source"] = None
    if out.get("city_id") and "state" not in sent:
        # A chosen city brings its state, unless the client sent one.
        city = db.get(City, out["city_id"])
        if city is not None:
            out["state"] = city.state
    return out


def validate(db: Session, state: Mapping[str, Any]) -> None:
    """Rules across fields, on the merged values. 422 with every problem at once."""
    errors = check_price(state)
    errors += check_area(
        state.get("land_area_min_sqm"), state.get("land_area_max_sqm"), "land_area"
    )
    lat, lng = state.get("lat"), state.get("lng")
    if (lat is None) != (lng is None):
        field = "location.lng" if lng is None else "location.lat"
        errors.append(FieldError(field, "Enter both latitude and longitude, or neither."))
    if state.get("pin_source") and lat is None:
        errors.append(FieldError("location.pin_source", "Set the pin before its source."))
    errors += _city_and_locality(db, state.get("city_id"), state.get("locality_id"))
    if state.get("publish_state") == "published" and not (state.get("rera_number") or "").strip():
        # COMPLIANCE: a live project page must always show its RERA number (D-002).
        errors.append(
            FieldError(
                "rera_number",
                "A published project must show its RERA registration number. "
                "Unpublish it before removing the number.",
            )
        )
    if errors:
        raise invalid(errors)


def _city_and_locality(
    db: Session, city_id: uuid.UUID | None, locality_id: uuid.UUID | None
) -> list[FieldError]:
    """INVARIANT (models.py header): the locality belongs to the chosen city."""
    if city_id is not None and db.get(City, city_id) is None:
        return [FieldError("location.city_id", "No city with this id.")]
    if locality_id is None:
        return []
    if city_id is None:
        return [FieldError("location.city_id", "Choose the city before the locality.")]
    locality = db.get(Locality, locality_id)
    if locality is None:
        return [FieldError("location.locality_id", "No locality with this id.")]
    if locality.city_id != city_id:
        return [FieldError("location.locality_id", "This locality is not in the chosen city.")]
    return []


def slug_must_be_free(db: Session, slug: str, exclude_id: uuid.UUID | None = None) -> None:
    """409 with a field error when another project already has this slug."""
    stmt = select(Project.id).where(Project.slug == slug)
    if exclude_id is not None:
        stmt = stmt.where(Project.id != exclude_id)
    if db.scalar(stmt) is not None:
        raise conflict(SLUG_TAKEN, "slug", SLUG_TAKEN)
