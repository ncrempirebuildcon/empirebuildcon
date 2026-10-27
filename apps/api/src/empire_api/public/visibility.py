"""Visibility, honest-content, and translation overlay rules for public endpoints (Task 5.1).

Implements:
- ARCHITECTURE §6, §7: only published, non-off-market items; sold_out after available.
- D-015: in production (APP_ENV=production), sample data (is_sample=True) is NEVER returned.
- D-014: Hindi translations overlay from `translations` JSON column with English fallback;
  `hi` locale is gated by the `locale_hi` feature flag.
- D-038: Hero/cover image selection: pinned cover if visible and labelled, else first visible
  labelled gallery photo, else None.
- Placeholders: string values holding [placeholder] (text in square brackets) are sanitized to
  null in production, but preserved in dev/test/staging.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any, TypeVar

from sqlalchemy import Select, case, exists, func, or_
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.media.models import Media, MediaLink
from empire_api.projects.models import City, Configuration, Locality, Project
from empire_api.site_settings import flags

T = TypeVar("T")

_PLACEHOLDER_PATTERN = re.compile(r"\[.*?\]")


def is_production() -> bool:
    """True only when running in production environment."""
    return get_settings().app_env == "production"


def sanitize_placeholders(value: Any, *, in_production: bool | None = None) -> Any:
    """Convert any string with bracketed [placeholder] to None when in production.

    In development, test, and staging, placeholders are returned as-is so teams can inspect them.
    """
    prod = is_production() if in_production is None else in_production
    if not prod:
        return value
    if isinstance(value, str):
        if _PLACEHOLDER_PATTERN.search(value):
            return None
        return value
    if isinstance(value, dict):
        return {k: sanitize_placeholders(v, in_production=prod) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_placeholders(v, in_production=prod) for v in value]
    return value


def resolve_cover_image(links: Sequence[MediaLink]) -> Media | None:
    """Hero/cover image decision rule (D-038):

    1. The pinned cover (`is_cover=True`) if visible and labelled (`label` non-empty).
    2. Otherwise, the first visible labelled gallery photo in sort_order.
    3. Otherwise, None.
    """
    gallery_links = [
        lnk
        for lnk in links
        if lnk.role == "gallery" and lnk.is_visible and lnk.media and bool(lnk.media.label)
    ]
    if not gallery_links:
        return None

    # Sort by sort_order
    sorted_links = sorted(gallery_links, key=lambda lnk_item: (lnk_item.sort_order, lnk_item.id))
    # 1. Pinned cover
    for lnk in sorted_links:
        if lnk.is_cover:
            return lnk.media
    # 2. First visible labelled photo
    return sorted_links[0].media


def is_hindi_active(db: Session, requested_locale: str | None) -> bool:
    """True only if Hindi locale was requested AND feature flag `locale_hi` is enabled."""
    if (requested_locale or "en").lower() != "hi":
        return False
    return flags.is_enabled(db, "locale_hi")


def translate_text(
    translations_dict: dict[str, Any] | None,
    field_name: str,
    default_text: str | None,
    *,
    is_hi: bool,
) -> str | None:
    """Return Hindi overlay text if requested and active, else English fallback."""
    if not is_hi or not translations_dict or not isinstance(translations_dict, dict):
        return default_text
    hi_dict = translations_dict.get("hi")
    if isinstance(hi_dict, dict) and field_name in hi_dict and hi_dict[field_name]:
        return str(hi_dict[field_name])
    return default_text


def _apply_config_filter(
    stmt: Select[Any],
    *,
    property_type: str | None,
    bhk: float | None,
    prod: bool,
) -> Select[Any]:
    if not property_type and bhk is None:
        return stmt

    config_filters = [
        Configuration.project_id == Project.id,
        Configuration.sales_status != "off_market",
    ]
    if prod:
        config_filters.append(Configuration.is_sample.is_(False))
    if property_type:
        config_filters.append(Configuration.property_type == property_type)
    if bhk is not None:
        config_filters.append(Configuration.bhk == bhk)

    return stmt.where(exists().where(*config_filters))


def _apply_search_filter(
    stmt: Select[Any],
    q: str | None,
) -> Select[Any]:
    if not q or not q.strip():
        return stmt

    cleaned_q = q.strip()
    ts_query = func.plainto_tsquery("english", cleaned_q)
    fts_project = Project.search_vector.op("@@")(ts_query)
    fts_city = func.to_tsvector("english", func.coalesce(City.name, "")).op("@@")(ts_query)
    fts_locality = func.to_tsvector("english", func.coalesce(Locality.name, "")).op("@@")(ts_query)

    trgm_name = func.word_similarity(cleaned_q, Project.name) >= 0.3
    trgm_tagline = func.word_similarity(cleaned_q, func.coalesce(Project.tagline, "")) >= 0.3
    trgm_city = func.word_similarity(cleaned_q, func.coalesce(City.name, "")) >= 0.3
    trgm_locality = func.word_similarity(cleaned_q, func.coalesce(Locality.name, "")) >= 0.3

    stmt = stmt.outerjoin(City, Project.city_id == City.id)
    stmt = stmt.outerjoin(Locality, Project.locality_id == Locality.id)

    return stmt.where(
        or_(
            fts_project,
            fts_city,
            fts_locality,
            trgm_name,
            trgm_tagline,
            trgm_city,
            trgm_locality,
        )
    )


def _apply_order_by(
    stmt: Select[Any],
    sort: str | None,
) -> Select[Any]:
    sales_order = case((Project.sales_status == "available", 0), else_=1)
    featured_order = case((Project.is_featured.is_(True), 0), else_=1)

    order_clauses: list[Any] = [
        sales_order,
        featured_order,
        Project.featured_order.asc().nulls_last(),
    ]

    sort_type = (sort or "recommended").lower()
    if sort_type == "price_asc":
        order_clauses.append(Project.price_min_inr.asc().nulls_last())
    elif sort_type == "price_desc":
        order_clauses.append(Project.price_max_inr.desc().nulls_last())
    elif sort_type == "possession":
        order_clauses.append(Project.possession_date.asc().nulls_last())
    elif sort_type == "newest":
        order_clauses.append(Project.created_at.desc())
    else:  # "recommended"
        order_clauses.append(Project.possession_date.asc().nulls_last())
        order_clauses.append(Project.created_at.desc())

    order_clauses.append(Project.id)
    return stmt.order_by(*order_clauses)


def apply_project_filters(
    stmt: Select[Any],
    *,
    status: str | None = None,
    city_slug: str | None = None,
    locality_slug: str | None = None,
    property_type: str | None = None,
    bhk: float | None = None,
    budget_min: int | None = None,
    budget_max: int | None = None,
    featured: bool | None = None,
    sort: str | None = None,
    q: str | None = None,
    order: bool = True,
) -> Select[Any]:
    """Apply the public projects catalog filters and sorting rules."""
    prod = is_production()
    stmt = stmt.where(
        Project.publish_state == "published",
        Project.sales_status != "off_market",
    )
    if prod:
        stmt = stmt.where(Project.is_sample.is_(False))

    if status:
        stmt = stmt.where(Project.status == status)
    if featured is not None:
        stmt = stmt.where(Project.is_featured.is_(featured))

    if city_slug:
        stmt = stmt.join(Project.city).where(City.slug == city_slug)
    if locality_slug:
        stmt = stmt.join(Locality, Project.locality_id == Locality.id).where(
            Locality.slug == locality_slug
        )

    stmt = _apply_config_filter(stmt, property_type=property_type, bhk=bhk, prod=prod)

    if budget_min is not None:
        stmt = stmt.where((Project.price_max_inr.is_(None)) | (Project.price_max_inr >= budget_min))
    if budget_max is not None:
        stmt = stmt.where((Project.price_min_inr.is_(None)) | (Project.price_min_inr <= budget_max))

    stmt = _apply_search_filter(stmt, q)
    if order:
        return _apply_order_by(stmt, sort)
    return stmt
