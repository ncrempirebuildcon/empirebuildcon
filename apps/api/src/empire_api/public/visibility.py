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

from sqlalchemy import Select, case, exists, func, literal, or_, select, text
from sqlalchemy.orm import Session, aliased

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


def resolve_cover_image(links: Sequence[MediaLink], *, prod: bool = False) -> Media | None:
    """Hero/cover image decision rule (D-038):

    1. The pinned cover (`is_cover=True`) if visible, labelled (`label` non-empty),
       and (in production) non-sample.
    2. Otherwise, the first visible labelled non-sample gallery photo in sort_order.
    3. Otherwise, None.
    """
    gallery_links = [
        lnk
        for lnk in links
        if lnk.role == "gallery"
        and lnk.is_visible
        and lnk.media
        and bool(lnk.media.label)
        and (not prod or not lnk.media.is_sample)
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


def set_search_trgm_threshold(db: Session, threshold: str = "0.5") -> None:
    """Set pg_trgm.word_similarity_threshold transaction-locally (D-038).

    COMPLIANCE: Uses is_local=true so this setting applies only to the current transaction.
    This works reliably across connection poolers (e.g. PgBouncer on Neon in transaction mode)
    without depending on session persistence or startup parameters.
    """
    db.execute(
        text("SELECT set_config('pg_trgm.word_similarity_threshold', :val, true)"),
        {"val": threshold},
    )


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

    # Word similarity on project name and tagline using gin_trgm_ops index:
    trgm_name = literal(cleaned_q).op("<%")(Project.name)
    trgm_tagline = literal(cleaned_q).op("<%")(func.coalesce(Project.tagline, ""))

    # Use aliased EXISTS subqueries for City and Locality so we never cause duplicate join aliases
    # or auto-correlation conflicts with outer city/locality filters
    search_city = aliased(City)
    city_tsv = func.to_tsvector("english", func.coalesce(search_city.name, ""))
    exists_city = (
        select(1)
        .select_from(search_city)
        .where(
            search_city.id == Project.city_id,
            or_(
                city_tsv.op("@@")(ts_query),
                literal(cleaned_q).op("<%")(search_city.name),
            ),
        )
        .correlate(Project)
        .exists()
    )

    search_locality = aliased(Locality)
    loc_tsv = func.to_tsvector("english", func.coalesce(search_locality.name, ""))
    exists_locality = (
        select(1)
        .select_from(search_locality)
        .where(
            search_locality.id == Project.locality_id,
            or_(
                loc_tsv.op("@@")(ts_query),
                literal(cleaned_q).op("<%")(search_locality.name),
            ),
        )
        .correlate(Project)
        .exists()
    )

    return stmt.where(
        or_(
            fts_project,
            trgm_name,
            trgm_tagline,
            exists_city,
            exists_locality,
        )
    )


def _apply_order_by(
    stmt: Select[Any],
    sort: str | None,
    q: str | None = None,
) -> Select[Any]:
    sales_order = case((Project.sales_status == "available", 0), else_=1)
    featured_order = case((Project.is_featured.is_(True), 0), else_=1)

    order_clauses: list[Any] = [
        sales_order,
        featured_order,
        Project.featured_order.asc().nulls_last(),
    ]

    cleaned_q = q.strip() if q else None
    sort_type = (sort or "recommended").lower()

    # S11: When q is provided with default recommended sort, order by relevance first
    if sort_type == "recommended" and cleaned_q:
        ts_query = func.plainto_tsquery("english", cleaned_q)
        order_clauses.append(func.ts_rank(Project.search_vector, ts_query).desc())
        order_clauses.append(func.similarity(Project.name, cleaned_q).desc())

    # S5: Treat price_on_request projects as NULL price so hidden numbers cannot be bisected
    eff_min = case((Project.price_on_request.is_(True), None), else_=Project.price_min_inr)
    eff_max = case((Project.price_on_request.is_(True), None), else_=Project.price_max_inr)

    if sort_type == "price_asc":
        order_clauses.append(eff_min.asc().nulls_last())
    elif sort_type == "price_desc":
        order_clauses.append(eff_max.desc().nulls_last())
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
    db: Session | None = None,
) -> Select[Any]:
    """Apply the public projects catalog filters and sorting rules."""
    if q and q.strip() and db is not None:
        set_search_trgm_threshold(db)
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

    # S5: Treat price_on_request as NULL price.
    # Bisection protection: NULL price never matches budget bounds.
    eff_min = case((Project.price_on_request.is_(True), None), else_=Project.price_min_inr)
    eff_max = case((Project.price_on_request.is_(True), None), else_=Project.price_max_inr)

    if budget_min is not None:
        stmt = stmt.where(eff_max.is_not(None) & (eff_max >= budget_min))
    if budget_max is not None:
        stmt = stmt.where(eff_min.is_not(None) & (eff_min <= budget_max))

    stmt = _apply_search_filter(stmt, q)
    if order:
        return _apply_order_by(stmt, sort, q=q)
    return stmt
