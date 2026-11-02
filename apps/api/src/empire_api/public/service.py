"""Query and assembly service for public endpoints (Task 5.1).

Implements bounded queries (batch-loading) for project detail and page blocks to prevent N+1.
"""
# ruff: noqa: PLR0911, PLR0912, PLR0915

from __future__ import annotations

import contextlib
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import datetime
from typing import Any

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from empire_api.content.consent import current_text
from empire_api.content.models import (
    Faq,
    Offer,
    Page,
    PageBlock,
    Post,
    Testimonial,
)
from empire_api.content.offers_state import is_live
from empire_api.content.page_rules import is_draft_text
from empire_api.content.vocab import CONSENT_KINDS
from empire_api.media import content_links
from empire_api.media.models import Media, MediaLink
from empire_api.media.present import linked_out
from empire_api.media.store import AssetRef, get_store
from empire_api.pagination import PageParams
from empire_api.projects import queries as project_queries
from empire_api.projects.models import City, Configuration, Locality, Project, ProjectAmenity
from empire_api.projects.present import (
    area_of,
    configuration_labels,
    directions_url,
    price_of,
    tower_progress,
)
from empire_api.projects.schemas_catalogue import Amenity
from empire_api.projects.schemas_children import (
    ConstructionUpdate as ChildUpdate,
)
from empire_api.projects.schemas_children import (
    LocationAdvantage as ChildAdvantage,
)
from empire_api.projects.schemas_children import (
    PaymentPlan as ChildPlan,
)
from empire_api.projects.schemas_children import (
    PaymentPlanStage,
)
from empire_api.projects.schemas_children import (
    Specification as ChildSpec,
)
from empire_api.projects.schemas_children import (
    Tower as ChildTower,
)
from empire_api.projects.schemas_shared import (
    CityRef,
    LocalityRef,
    Location,
    Price,
)
from empire_api.public import schemas
from empire_api.public.visibility import (
    apply_project_filters,
    is_hindi_active,
    is_production,
    resolve_cover_image,
    sanitize_placeholders,
    translate_text,
)
from empire_api.search import set_search_trgm_threshold
from empire_api.seo.models import Redirect
from empire_api.seo.paths import city_path, page_path, post_path, project_path, property_path
from empire_api.site_settings import flags
from empire_api.site_settings.defaults import read_group
from empire_api.site_settings.models import FeatureFlag
from empire_api.timeutil import utcnow
from empire_api.users.directory import user_refs
from empire_api.users.schemas import PageMeta

# --- Helpers ---------------------------------------------------------------------------------


def _media_schema(row: Any | None, *, prod: bool = False) -> schemas.PublicMedia | None:
    if row is None:
        return None
    if prod and getattr(row, "is_sample", False):
        return None

    if hasattr(row, "storage_key") or (hasattr(row, "public_id") and not hasattr(row, "url")):
        urls = get_store().urls(
            AssetRef(
                kind=row.kind,
                public_id=row.public_id,
                resource_type=row.resource_type,
                version=row.version,
                format=row.format,
            )
        )
        url = urls.url
        thumbnail_url = urls.thumbnail_url
    else:
        url = getattr(row, "url", None) or ""
        thumbnail_url = getattr(row, "thumbnail_url", None)

    return schemas.PublicMedia(
        id=row.id,
        kind=row.kind,
        url=url,
        thumbnail_url=thumbnail_url,
        alt_text=row.alt_text,
        format=row.format,
        width=row.width,
        height=row.height,
        duration_s=float(row.duration_s) if row.duration_s is not None else None,
        label=row.label,
        label_month=str(row.label_month) if row.label_month else None,
        is_sample=row.is_sample,
    )


def _linked_media_schema(
    link: MediaLink | None, *, prod: bool = False
) -> schemas.PublicLinkedMedia | None:
    if link is None or link.media is None or not link.is_visible:
        return None
    m = _media_schema(link.media, prod=prod)
    if m is None:
        return None
    return schemas.PublicLinkedMedia(
        **m.model_dump(),
        role=link.role,
        sort_order=link.sort_order,
        is_cover=link.is_cover,
    )


def _build_public_seo(
    db: Session,
    raw_seo: Any,
    *,
    prod: bool = False,
    media_map: dict[uuid.UUID, Media] | None = None,
) -> schemas.PublicSeo:
    d = dict(raw_seo or {}) if not isinstance(raw_seo, dict) else raw_seo
    title = d.get("title")
    description = d.get("description")
    noindex = bool(d.get("noindex", False))
    canonical_path = d.get("canonical_path")
    og_img_id = d.get("og_image_id")
    og_image: schemas.PublicMedia | None = None
    if og_img_id:
        try:
            m_uuid = uuid.UUID(str(og_img_id))
            if media_map is not None:
                m_row = media_map.get(m_uuid)
            else:
                m_row = db.scalar(select(Media).where(Media.id == m_uuid))
            if m_row:
                og_image = _media_schema(m_row, prod=prod)
        except ValueError, TypeError:
            og_image = None

    return schemas.PublicSeo(
        title=title,
        description=description,
        og_image=og_image,
        noindex=noindex,
        canonical_path=canonical_path,
    )


def _public_price(row: Any, *, project_on_request: bool = False) -> Price:
    """The public price of a project or configuration.

    COMPLIANCE: when the project asks for "price on request", its configurations do too, even
    if staff left figures on them, so no figure for that project reaches the site (task 5.3,
    D-041). The budget filter and the price sorts follow the same rule.
    """
    base = price_of(row)
    std_note = "excludes GST, stamp duty and registration"
    if base.note and std_note not in base.note:
        note = f"{base.note} ({std_note})"
    else:
        note = base.note or std_note

    if base.on_request or project_on_request:
        return Price(
            on_request=True,
            min_inr=None,
            max_inr=None,
            rate_inr=None,
            rate_unit=None,
            note=note,
            display="Price on request",
        )
    return Price(
        on_request=False,
        min_inr=base.min_inr,
        max_inr=base.max_inr,
        rate_inr=base.rate_inr,
        rate_unit=base.rate_unit,
        note=note,
        display=base.display,
    )


# --- Public Site -----------------------------------------------------------------------------


def get_public_site(db: Session, *, locale: str | None = None) -> schemas.PublicSite:
    """Return public company details, regulator, nav, public flags, consent texts, and offers."""
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    company_vals = sanitize_placeholders(read_group(db, "company"), in_production=prod)
    contacts_vals = sanitize_placeholders(read_group(db, "contacts"), in_production=prod)

    phones = [
        p for p in [contacts_vals.get("sales_phone"), contacts_vals.get("customer_care_phone")] if p
    ]
    emails = [
        e for e in [contacts_vals.get("sales_email"), contacts_vals.get("customer_care_email")] if e
    ]

    company = schemas.PublicCompany(
        name=company_vals.get("brand_name") or company_vals.get("legal_name") or "Empire",
        legal_name=company_vals.get("legal_name"),
        tagline=translate_text(
            company_vals.get("translations"),
            "tagline",
            company_vals.get("tagline"),
            is_hi=is_hi,
        ),
        gstin=company_vals.get("gstin"),
        address=company_vals.get("corporate_address") or company_vals.get("registered_address"),
        registered_address=company_vals.get("registered_address"),
        corporate_address=company_vals.get("corporate_address"),
        phones=phones,
        whatsapp=contacts_vals.get("whatsapp_number"),
        whatsapp_message=contacts_vals.get("whatsapp_message"),
        office_hours=contacts_vals.get("office_hours"),
        emails=emails,
    )

    social_vals = sanitize_placeholders(read_group(db, "social"), in_production=prod)
    social = {k: v for k, v in social_vals.items() if v}

    reg_vals = sanitize_placeholders(read_group(db, "regulator"), in_production=prod)
    regulator = schemas.PublicRegulator(
        state=reg_vals.get("state") or "UP",
        authority=reg_vals.get("authority") or "UP-RERA",
        website=reg_vals.get("website") or "https://www.up-rera.in",
        name="Uttar Pradesh Real Estate Regulatory Authority",
        promoter_number=reg_vals.get("promoter_registration_number"),
    )

    nav_stmt = (
        select(Page)
        .where(
            Page.publish_state == "published",
            Page.show_in_nav.is_(True),
        )
        .order_by(Page.nav_order.asc().nulls_last(), Page.id.asc())
    )
    if prod:
        nav_stmt = nav_stmt.where(Page.is_sample.is_(False))
    nav_pages = db.scalars(nav_stmt).all()
    nav_items = [
        schemas.PublicNavItem(
            label=translate_text(p.translations, "title", p.title, is_hi=is_hi) or p.title,
            path=page_path(p.slug),
        )
        for p in nav_pages
    ]

    flag_rows = db.scalars(select(FeatureFlag).where(FeatureFlag.is_public.is_(True))).all()
    features = {f.key: f.enabled for f in flag_rows}

    consent_dict: dict[str, schemas.PublicConsentText | None] = {}
    for kind in CONSENT_KINDS:
        ct = current_text(db, kind)
        if ct:
            consent_dict[kind] = schemas.PublicConsentText(
                id=ct.id,
                kind=ct.kind,
                version=ct.version,
                body=ct.body,
                checkbox_label=ct.checkbox_label,
            )
        else:
            consent_dict[kind] = None

    now = utcnow()
    offer_stmt = (
        select(Offer)
        .where(Offer.is_active.is_(True))
        .order_by(Offer.priority.asc(), Offer.id.asc())
    )
    if prod:
        offer_stmt = offer_stmt.where(Offer.is_sample.is_(False))
    offer_rows = db.scalars(offer_stmt).all()

    offer_img_ids = [off.image_media_id for off in offer_rows if off.image_media_id]
    offer_images = content_links.library_items(db, offer_img_ids)

    # M5: Check project visibility for project-linked offers
    proj_ids_in_offers = [off.project_id for off in offer_rows if off.project_id]
    visible_proj_ids: set[uuid.UUID] = set()
    if proj_ids_in_offers:
        v_stmt = select(Project.id).where(
            Project.id.in_(proj_ids_in_offers),
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
        if prod:
            v_stmt = v_stmt.where(Project.is_sample.is_(False))
        visible_proj_ids = set(db.scalars(v_stmt).all())

    proj_refs = project_queries.project_refs(db, list(visible_proj_ids))

    public_offers: list[schemas.PublicOffer] = []
    for off in offer_rows:
        if is_live(off, now=now):
            if off.project_id and off.project_id not in visible_proj_ids:
                # Offer is linked to an unpublished or draft or off-market project - drop it!
                continue
            raw_im = offer_images.get(off.image_media_id) if off.image_media_id else None
            im = _media_schema(raw_im, prod=prod) if raw_im else None
            p_ref = proj_refs.get(off.project_id) if off.project_id else None
            public_offers.append(
                schemas.PublicOffer(
                    id=off.id,
                    title=off.title,
                    body=off.body,
                    image=im,
                    cta_label=off.cta_label,
                    cta_url=off.cta_url,
                    terms=off.terms,
                    terms_url=off.terms_url,
                    placement=off.placement,
                    project_slug=p_ref.slug if p_ref else None,
                    starts_at=off.starts_at,
                    ends_at=off.ends_at,
                )
            )

    seo_vals = sanitize_placeholders(read_group(db, "seo_defaults"), in_production=prod)
    seo_defaults = schemas.PublicSeoDefaults(
        default_title=seo_vals.get("default_title"),
        title_suffix=seo_vals.get("title_suffix") or " | Empire",
        default_description=seo_vals.get("default_description"),
    )

    available_locales = ["en"]
    if flags.is_enabled(db, "locale_hi"):
        available_locales.append("hi")

    has_sample = False
    if not prod:
        has_sample = bool(
            db.scalar(
                select(Project.id)
                .where(Project.is_sample.is_(True), Project.publish_state == "published")
                .limit(1)
            )
            or any(getattr(off, "is_sample", False) for off in offer_rows)
        )

    return schemas.PublicSite(
        company=company,
        social=social,
        regulator=regulator,
        nav=nav_items,
        features=features,
        tracking=None,
        consent=consent_dict,
        offers=public_offers,
        locales=available_locales,
        seo=seo_defaults,
        has_sample=has_sample,
    )


# --- Projects --------------------------------------------------------------------------------


def _build_public_summary(
    p: Project,
    links: Sequence[MediaLink],
    qr_media: Media | None,
    configs: Sequence[Configuration],
    *,
    is_hi: bool,
) -> schemas.PublicProjectSummary:
    prod = is_production()
    visible_configs = [
        c for c in configs if c.sales_status != "off_market" and (not prod or not c.is_sample)
    ]
    c_labels = configuration_labels(visible_configs)
    types = sorted({c.property_type for c in visible_configs if c.property_type})

    cover_m = resolve_cover_image(links, prod=prod)
    cover_schema = _media_schema(cover_m, prod=prod) if cover_m else None
    qr_schema = _media_schema(qr_media, prod=prod) if qr_media else None

    regulator_url = "https://www.up-rera.in"
    rera_block = schemas.PublicRera(
        authority="UP-RERA",
        number=p.rera_number,
        url=regulator_url,
        qr=qr_schema,
    )

    city_ref = (
        CityRef(id=p.city.id, name=p.city.name, slug=p.city.slug, state=p.city.state)
        if p.city
        else None
    )
    locality_ref = (
        LocalityRef(id=p.locality.id, name=p.locality.name, slug=p.locality.slug)
        if p.locality
        else None
    )

    return schemas.PublicProjectSummary(
        id=p.id,
        slug=p.slug,
        name=translate_text(p.translations, "name", p.name, is_hi=is_hi) or p.name,
        status=p.status,
        sales_status=p.sales_status,
        city=city_ref,
        locality=locality_ref,
        price=_public_price(p),
        configuration_labels=c_labels,
        property_types=types,
        cover=cover_schema,
        rera=rera_block,
        possession_date=p.possession_date,
        is_featured=p.is_featured,
        is_sample=p.is_sample,
    )


def list_public_projects(
    db: Session,
    paging: PageParams,
    *,
    status: str | None = None,
    city: str | None = None,
    locality: str | None = None,
    property_type: str | None = None,
    bhk: float | None = None,
    budget_min: int | None = None,
    budget_max: int | None = None,
    featured: bool | None = None,
    sort: str | None = None,
    q: str | None = None,
    locale: str | None = None,
) -> schemas.PublicProjectList:
    is_hi = is_hindi_active(db, locale)

    if q and q.strip():
        set_search_trgm_threshold(db)

    stmt = select(Project).options(
        joinedload(Project.city),
        joinedload(Project.locality),
        selectinload(Project.configurations),
    )
    stmt = apply_project_filters(
        stmt,
        status=status,
        city_slug=city,
        locality_slug=locality,
        property_type=property_type,
        bhk=bhk,
        budget_min=budget_min,
        budget_max=budget_max,
        featured=featured,
        sort=sort,
        q=q,
    )

    count_stmt = select(func.count(Project.id))
    count_stmt = apply_project_filters(
        count_stmt,
        status=status,
        city_slug=city,
        locality_slug=locality,
        property_type=property_type,
        bhk=bhk,
        budget_min=budget_min,
        budget_max=budget_max,
        featured=featured,
        sort=sort,
        q=q,
        order=False,
    )
    total = db.scalar(count_stmt) or 0

    paged_stmt = stmt.offset(paging.offset).limit(paging.per_page)
    projects = db.scalars(paged_stmt).unique().all()

    p_ids = [p.id for p in projects]
    links_by_p: dict[uuid.UUID, list[MediaLink]] = defaultdict(list)
    qr_by_p: dict[uuid.UUID, Media] = {}

    if p_ids:
        all_links = db.scalars(
            select(MediaLink)
            .where(
                MediaLink.project_id.in_(p_ids),
                MediaLink.is_visible.is_(True),
            )
            .options(joinedload(MediaLink.media))
        ).all()
        for lnk in all_links:
            if lnk.project_id:
                links_by_p[lnk.project_id].append(lnk)
                if lnk.role == "rera_qr":
                    qr_by_p[lnk.project_id] = lnk.media

    items = [
        _build_public_summary(
            p,
            links_by_p.get(p.id, []),
            qr_by_p.get(p.id),
            p.configurations,
            is_hi=is_hi,
        )
        for p in projects
    ]

    meta = PageMeta(**paging.meta(total))
    return schemas.PublicProjectList(items=items, meta=meta)


def _build_towers(towers: Sequence[Any], updates: Sequence[Any]) -> list[ChildTower]:
    progress_map = tower_progress(updates)
    return [
        ChildTower(
            id=t.id,
            name=t.name,
            kind=t.kind,
            floors=t.floors,
            units_count=t.units_count,
            status=t.status,
            rera_number=t.rera_number,
            possession_date=t.possession_date,
            progress_percent=progress_map.get(t.id),
            sort_order=t.sort_order,
        )
        for t in towers
    ]


def _build_configurations(
    configs: Sequence[Configuration],
    config_links: dict[uuid.UUID, list[MediaLink]],
    *,
    is_hi: bool,
    prod: bool,
    project_on_request: bool = False,
) -> list[schemas.PublicConfiguration]:
    active = [c for c in configs if c.sales_status != "off_market"]
    if prod:
        active = [c for c in active if not c.is_sample]
    active.sort(key=lambda c: (0 if c.sales_status == "available" else 1, c.sort_order, c.id))

    result: list[schemas.PublicConfiguration] = []
    for c in active:
        fp_links = [
            m
            for lnk in config_links.get(c.id, [])
            if lnk.role == "floor_plan" and (m := _linked_media_schema(lnk, prod=prod)) is not None
        ]
        result.append(
            schemas.PublicConfiguration(
                id=c.id,
                slug=c.slug,
                name=translate_text(c.translations, "name", c.name, is_hi=is_hi) or c.name,
                tower_id=c.tower_id,
                property_type=c.property_type,
                bhk=float(c.bhk) if c.bhk is not None else None,
                bathrooms=c.bathrooms,
                balconies=c.balconies,
                area=area_of(c.area_min_sqm, c.area_max_sqm, c.area_basis, c.area_display_unit),
                price=_public_price(c, project_on_request=project_on_request),
                sales_status=c.sales_status,
                floor_plans=fp_links,
                sort_order=c.sort_order,
                is_sample=c.is_sample,
            )
        )
    return result


def _build_updates(
    updates: Sequence[Any],
    update_links: dict[uuid.UUID, list[MediaLink]],
    *,
    prod: bool,
) -> list[ChildUpdate]:
    published = [u for u in updates if u.publish_state == "published"]
    result: list[ChildUpdate] = []
    store = get_store()
    for u in published:
        photos: list[Any] = []
        for lnk in update_links.get(u.id, []):
            if lnk.media and lnk.is_visible:
                if prod and getattr(lnk.media, "is_sample", False):
                    continue
                photos.append(linked_out(lnk, attached=1, store=store))
        result.append(
            ChildUpdate(
                id=u.id,
                tower_id=u.tower_id,
                title=u.title,
                update_date=u.update_date,
                progress_percent=u.progress_percent,
                body=u.body,
                photos=photos,
                publish_state=u.publish_state,
                sort_order=u.sort_order,
            )
        )
    return result


def _load_project_faqs(
    db: Session,
    project_id: uuid.UUID,
    *,
    is_hi: bool,
    prod: bool,
) -> list[schemas.PublicFaq]:
    faq_stmt = (
        select(Faq)
        .where(Faq.project_id == project_id, Faq.is_visible.is_(True))
        .order_by(Faq.sort_order.asc(), Faq.id.asc())
    )
    if prod:
        faq_stmt = faq_stmt.where(Faq.is_sample.is_(False))
    return [
        schemas.PublicFaq(
            id=f.id,
            question=translate_text(f.translations, "question", f.question, is_hi=is_hi)
            or f.question,
            answer=translate_text(f.translations, "answer", f.answer, is_hi=is_hi) or f.answer,
            sort_order=f.sort_order,
            is_visible=True,
        )
        for f in db.scalars(faq_stmt).all()
    ]


def get_public_project(
    db: Session,
    slug: str,
    *,
    locale: str | None = None,
) -> schemas.PublicProjectDetail | None:
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    stmt = (
        select(Project)
        .where(
            Project.slug == slug,
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
        .options(
            joinedload(Project.city),
            joinedload(Project.locality),
            selectinload(Project.towers),
            selectinload(Project.configurations),
            selectinload(Project.specifications),
            selectinload(Project.location_advantages),
            selectinload(Project.construction_updates),
            selectinload(Project.payment_plans),
            selectinload(Project.amenity_links).joinedload(ProjectAmenity.amenity),
        )
    )
    if prod:
        stmt = stmt.where(Project.is_sample.is_(False))

    p = db.scalar(stmt)
    if not p:
        return None

    config_ids = [c.id for c in p.configurations]
    update_ids = [u.id for u in p.construction_updates]

    all_links = db.scalars(
        select(MediaLink)
        .where(
            (MediaLink.project_id == p.id)
            | (MediaLink.configuration_id.in_(config_ids))
            | (MediaLink.construction_update_id.in_(update_ids)),
            MediaLink.is_visible.is_(True),
        )
        .options(joinedload(MediaLink.media))
    ).all()

    project_links: list[MediaLink] = []
    config_links: dict[uuid.UUID, list[MediaLink]] = defaultdict(list)
    update_links: dict[uuid.UUID, list[MediaLink]] = defaultdict(list)
    qr_media: Media | None = None
    brochure_media: MediaLink | None = None

    for link in all_links:
        if link.project_id == p.id:
            project_links.append(link)
            if link.role == "rera_qr":
                qr_media = link.media
            elif link.role == "brochure":
                brochure_media = link
        elif link.configuration_id:
            config_links[link.configuration_id].append(link)
        elif link.construction_update_id:
            update_links[link.construction_update_id].append(link)

    configurations = _build_configurations(
        p.configurations,
        config_links,
        is_hi=is_hi,
        prod=prod,
        project_on_request=bool(p.price_on_request),
    )
    summary = _build_public_summary(p, project_links, qr_media, p.configurations, is_hi=is_hi)
    towers = _build_towers(p.towers, p.construction_updates)
    construction_updates = _build_updates(p.construction_updates, update_links, prod=prod)
    project_faqs = _load_project_faqs(db, p.id, is_hi=is_hi, prod=prod)

    amenities = [
        Amenity(
            id=lnk.amenity.id,
            name=lnk.amenity.name,
            slug=lnk.amenity.slug,
            icon=lnk.amenity.icon,
            category=lnk.amenity.category,
        )
        for lnk in p.amenity_links
        if lnk.amenity
    ]

    specifications = [
        ChildSpec(id=s.id, category=s.category, text=s.text, sort_order=s.sort_order)
        for s in p.specifications
    ]

    location_advantages = [
        ChildAdvantage(
            id=a.id,
            label=a.label,
            kind=a.kind,
            distance_km=float(a.distance_km) if a.distance_km is not None else None,
            travel_minutes=a.travel_minutes,
            sort_order=a.sort_order,
        )
        for a in p.location_advantages
    ]

    payment_plans = [
        ChildPlan(
            id=pl.id,
            name=pl.name,
            description=pl.description,
            stages=[PaymentPlanStage.model_validate(st) for st in pl.stages],
            is_visible=pl.is_visible,
            sort_order=pl.sort_order,
        )
        for pl in p.payment_plans
        if pl.is_visible
    ]

    gallery = [
        m
        for lnk in project_links
        if lnk.role == "gallery"
        and lnk.media
        and bool(lnk.media.label)
        and (m := _linked_media_schema(lnk, prod=prod)) is not None
    ]
    videos = [
        m
        for lnk in project_links
        if lnk.role == "video" and (m := _linked_media_schema(lnk, prod=prod)) is not None
    ]
    documents = [
        m
        for lnk in project_links
        if lnk.role == "document" and (m := _linked_media_schema(lnk, prod=prod)) is not None
    ]
    brochure = (
        None
        if p.brochure_gated
        else (_linked_media_schema(brochure_media, prod=prod) if brochure_media else None)
    )

    location = Location(
        address_line=p.address_line,
        city=summary.city,
        locality=summary.locality,
        state=p.state,
        pincode=p.pincode,
        lat=float(p.lat) if p.lat is not None else None,
        lng=float(p.lng) if p.lng is not None else None,
        google_maps_url=p.google_maps_url,
        plus_code=p.plus_code,
        pin_source=p.pin_source,
        directions_url=directions_url(p.lat, p.lng),
    )

    land_area = (
        area_of(
            p.land_area_min_sqm,
            p.land_area_max_sqm,
            p.land_area_basis or "plot",
            p.land_area_display_unit or "sqft",
        )
        if (p.land_area_min_sqm or p.land_area_max_sqm)
        else None
    )

    detail = schemas.PublicProjectDetail(
        **summary.model_dump(),
        tagline=translate_text(p.translations, "tagline", p.tagline, is_hi=is_hi) or p.tagline,
        description=translate_text(p.translations, "description", p.description, is_hi=is_hi)
        or p.description,
        project_type=p.project_type,
        land_area=land_area,
        total_units=p.total_units,
        launch_date=p.launch_date,
        location=location,
        towers=towers,
        configurations=configurations,
        amenities=amenities,
        specifications=specifications,
        location_advantages=location_advantages,
        construction_updates=construction_updates,
        payment_plans=payment_plans,
        gallery=gallery,
        videos=videos,
        documents=documents,
        brochure=brochure,
        brochure_gated=p.brochure_gated,
        faqs=project_faqs,
        seo=_build_public_seo(db, p.seo or {}, prod=prod),
        updated_at=p.updated_at,
    )
    return detail


# --- Properties (Configurations) -------------------------------------------------------------


def _apply_property_filters(
    stmt: Select[Any],
    *,
    city: str | None,
    locality: str | None,
    property_type: str | None,
    bhk: float | None,
    budget_min: int | None,
    budget_max: int | None,
    project_status: str | None,
) -> Select[Any]:
    if city:
        stmt = stmt.join(Project.city).where(City.slug == city)
    if locality:
        stmt = stmt.join(Locality, Project.locality_id == Locality.id).where(
            Locality.slug == locality
        )
    if property_type:
        stmt = stmt.where(Configuration.property_type == property_type)
    if bhk is not None:
        stmt = stmt.where(Configuration.bhk == bhk)
    if project_status:
        stmt = stmt.where(Project.status == project_status)
    # WHY coalesce: "From ₹ 78 L" (no upper end) is one figure for the budget filter (5.3 fix).
    hidden = Configuration.price_on_request.is_(True) | Project.price_on_request.is_(True)
    eff_min = case(
        (hidden, None),
        else_=func.coalesce(Configuration.price_min_inr, Configuration.price_max_inr),
    )
    eff_max = case(
        (hidden, None),
        else_=func.coalesce(Configuration.price_max_inr, Configuration.price_min_inr),
    )

    if budget_min is not None:
        stmt = stmt.where(eff_max.is_not(None) & (eff_max >= budget_min))
    if budget_max is not None:
        stmt = stmt.where(eff_min.is_not(None) & (eff_min <= budget_max))
    return stmt


def _property_order_clauses(sort: str | None) -> list[Any]:
    order_clauses: list[Any] = [
        case((Configuration.sales_status == "available", 0), else_=1),
    ]
    # WHY coalesce: "From ₹ 78 L" (no upper end) is one figure for the budget filter (5.3 fix).
    hidden = Configuration.price_on_request.is_(True) | Project.price_on_request.is_(True)
    eff_min = case(
        (hidden, None),
        else_=func.coalesce(Configuration.price_min_inr, Configuration.price_max_inr),
    )
    eff_max = case(
        (hidden, None),
        else_=func.coalesce(Configuration.price_max_inr, Configuration.price_min_inr),
    )

    sort_type = (sort or "recommended").lower()
    if sort_type == "price_asc":
        order_clauses.append(eff_min.asc().nulls_last())
    elif sort_type == "price_desc":
        order_clauses.append(eff_max.desc().nulls_last())
    elif sort_type == "size_desc":
        order_clauses.append(Configuration.area_max_sqm.desc().nulls_last())
    else:
        order_clauses.append(Configuration.sort_order.asc())

    # S15: Append Configuration.id as stable tie-breaker
    order_clauses.append(Configuration.id.asc())
    return order_clauses


def list_public_properties(
    db: Session,
    paging: PageParams,
    *,
    city: str | None = None,
    locality: str | None = None,
    property_type: str | None = None,
    bhk: float | None = None,
    budget_min: int | None = None,
    budget_max: int | None = None,
    project_status: str | None = None,
    sort: str | None = None,
    locale: str | None = None,
) -> schemas.PublicPropertyList:
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    stmt = (
        select(Configuration)
        .join(Project, Configuration.project_id == Project.id)
        .where(
            Configuration.sales_status != "off_market",
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
    )
    if prod:
        stmt = stmt.where(Configuration.is_sample.is_(False), Project.is_sample.is_(False))

    stmt = _apply_property_filters(
        stmt,
        city=city,
        locality=locality,
        property_type=property_type,
        bhk=bhk,
        budget_min=budget_min,
        budget_max=budget_max,
        project_status=project_status,
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    order_clauses = _property_order_clauses(sort)

    paged_stmt = stmt.order_by(*order_clauses).offset(paging.offset).limit(paging.per_page)
    configs = db.scalars(paged_stmt).unique().all()

    proj_ids = list({c.project_id for c in configs})
    projs_map: dict[uuid.UUID, Project] = {}
    qr_by_project: dict[uuid.UUID, Media] = {}

    if proj_ids:
        loaded_projs = db.scalars(
            select(Project)
            .where(Project.id.in_(proj_ids))
            .options(joinedload(Project.city), joinedload(Project.locality))
        ).all()
        for prj in loaded_projs:
            projs_map[prj.id] = prj

        qr_links = db.scalars(
            select(MediaLink)
            .where(
                MediaLink.project_id.in_(proj_ids),
                MediaLink.role == "rera_qr",
                MediaLink.is_visible.is_(True),
            )
            .options(joinedload(MediaLink.media))
        ).all()
        for lnk in qr_links:
            if lnk.project_id:
                qr_by_project[lnk.project_id] = lnk.media

    config_ids = [c.id for c in configs]
    fp_map: dict[uuid.UUID, list[MediaLink]] = defaultdict(list)
    if config_ids:
        c_links = db.scalars(
            select(MediaLink)
            .where(
                MediaLink.configuration_id.in_(config_ids),
                MediaLink.role == "floor_plan",
                MediaLink.is_visible.is_(True),
            )
            .options(joinedload(MediaLink.media))
        ).all()
        for lnk in c_links:
            if lnk.configuration_id:
                fp_map[lnk.configuration_id].append(lnk)

    items: list[schemas.PublicPropertySummary] = []
    for c in configs:
        p = projs_map.get(c.project_id)
        if not p:
            continue
        qr_m = qr_by_project.get(p.id)
        rera = schemas.PublicRera(
            authority="UP-RERA",
            number=p.rera_number,
            url="https://www.up-rera.in",
            qr=_media_schema(qr_m, prod=prod) if qr_m else None,
        )
        proj_ref = schemas.PublicProjectRef(
            slug=p.slug,
            name=translate_text(p.translations, "name", p.name, is_hi=is_hi) or p.name,
            status=p.status,
            city=CityRef(id=p.city.id, name=p.city.name, slug=p.city.slug, state=p.city.state)
            if p.city
            else None,
            locality=LocalityRef(id=p.locality.id, name=p.locality.name, slug=p.locality.slug)
            if p.locality
            else None,
            rera=rera,
        )

        visible_floor_plans = [
            lnk.media
            for lnk in fp_map.get(c.id, [])
            if lnk.role == "floor_plan"
            and lnk.is_visible
            and lnk.media
            and (not prod or not lnk.media.is_sample)
        ]
        cover_media = visible_floor_plans[0] if visible_floor_plans else None

        items.append(
            schemas.PublicPropertySummary(
                id=c.id,
                slug=c.slug,
                name=translate_text(c.translations, "name", c.name, is_hi=is_hi) or c.name,
                property_type=c.property_type,
                bhk=float(c.bhk) if c.bhk is not None else None,
                area=area_of(c.area_min_sqm, c.area_max_sqm, c.area_basis, c.area_display_unit),
                price=_public_price(c, project_on_request=bool(p.price_on_request)),
                sales_status=c.sales_status,
                cover=_media_schema(cover_media, prod=prod) if cover_media else None,
                project=proj_ref,
                is_sample=c.is_sample,
            )
        )

    meta = PageMeta(**paging.meta(total))
    return schemas.PublicPropertyList(items=items, meta=meta)


def get_public_property(
    db: Session,
    *,
    project_slug: str,
    config_slug: str,
    locale: str | None = None,
) -> schemas.PublicPropertyDetail | None:
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    # N11: Load project directly without full project detail graph
    p_stmt = (
        select(Project)
        .where(
            Project.slug == project_slug,
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
        .options(
            joinedload(Project.city),
            joinedload(Project.locality),
            selectinload(Project.configurations),
        )
    )
    if prod:
        p_stmt = p_stmt.where(Project.is_sample.is_(False))
    p = db.scalar(p_stmt)
    if not p:
        return None

    stmt = select(Configuration).where(
        Configuration.slug == config_slug,
        Configuration.project_id == p.id,
        Configuration.sales_status != "off_market",
    )
    if prod:
        stmt = stmt.where(Configuration.is_sample.is_(False))

    c = db.scalar(stmt)
    if not c:
        return None

    c_links = db.scalars(
        select(MediaLink)
        .where(
            MediaLink.configuration_id == c.id,
            MediaLink.role == "floor_plan",
            MediaLink.is_visible.is_(True),
        )
        .options(joinedload(MediaLink.media))
    ).all()

    fp_links = [m for lnk in c_links if (m := _linked_media_schema(lnk, prod=prod)) is not None]

    p_links = db.scalars(
        select(MediaLink)
        .where(MediaLink.project_id == p.id, MediaLink.is_visible.is_(True))
        .options(joinedload(MediaLink.media))
    ).all()
    qr_media = next((lnk.media for lnk in p_links if lnk.role == "rera_qr"), None)
    vis_configs = [
        cfg
        for cfg in p.configurations
        if cfg.sales_status != "off_market" and (not prod or not cfg.is_sample)
    ]
    proj_summary = _build_public_summary(p, p_links, qr_media, vis_configs, is_hi=is_hi)

    return schemas.PublicPropertyDetail(
        id=c.id,
        slug=c.slug,
        name=translate_text(c.translations, "name", c.name, is_hi=is_hi) or c.name,
        tower_id=c.tower_id,
        property_type=c.property_type,
        bhk=float(c.bhk) if c.bhk is not None else None,
        bathrooms=c.bathrooms,
        balconies=c.balconies,
        area=area_of(c.area_min_sqm, c.area_max_sqm, c.area_basis, c.area_display_unit),
        price=_public_price(c, project_on_request=bool(p.price_on_request)),
        sales_status=c.sales_status,
        floor_plans=fp_links,
        sort_order=c.sort_order,
        is_sample=c.is_sample,
        project=proj_summary,
    )


# --- Cities ----------------------------------------------------------------------------------


def list_public_cities(db: Session) -> list[schemas.PublicCity]:
    """Cities that have at least one published, visible project."""
    prod = is_production()
    p_filter = [
        Project.publish_state == "published",
        Project.sales_status != "off_market",
    ]
    if prod:
        p_filter.append(Project.is_sample.is_(False))

    count_subq = (
        select(Project.city_id, func.count().label("p_count"))
        .where(*p_filter)
        .group_by(Project.city_id)
        .subquery()
    )

    stmt = (
        select(City, count_subq.c.p_count)
        .join(count_subq, City.id == count_subq.c.city_id)
        .where(count_subq.c.p_count > 0)
        .order_by(City.name.asc())
    )

    rows = db.execute(stmt).all()
    return [
        schemas.PublicCity(
            id=city_row.id,
            name=city_row.name,
            slug=city_row.slug,
            state=city_row.state,
            project_count=int(cnt),
        )
        for city_row, cnt in rows
    ]


# --- Pages & Blocks --------------------------------------------------------------------------


def _collect_block_entity_ids(
    blocks: Sequence[PageBlock],
) -> tuple[set[uuid.UUID], set[uuid.UUID], set[uuid.UUID], set[uuid.UUID]]:
    media_ids: set[uuid.UUID] = set()
    faq_ids: set[uuid.UUID] = set()
    testimonial_ids: set[uuid.UUID] = set()
    offer_ids: set[uuid.UUID] = set()

    for b in blocks:
        d = b.data or {}
        if b.type in ("image", "hero") and d.get("image_id"):
            media_ids.add(uuid.UUID(str(d["image_id"])))
        elif b.type == "video" and d.get("media_id"):
            media_ids.add(uuid.UUID(str(d["media_id"])))
        elif b.type == "gallery":
            for i in d.get("image_ids", []):
                media_ids.add(uuid.UUID(str(i)))
        elif b.type == "faq_list":
            for i in d.get("faq_ids", []):
                faq_ids.add(uuid.UUID(str(i)))
        elif b.type == "testimonials":
            for i in d.get("testimonial_ids", []):
                testimonial_ids.add(uuid.UUID(str(i)))
        elif b.type == "offer_banner" and d.get("offer_id"):
            offer_ids.add(uuid.UUID(str(d["offer_id"])))

    return media_ids, faq_ids, testimonial_ids, offer_ids


def _batch_load_page_entities(
    db: Session,
    blocks: Sequence[PageBlock],
    *,
    prod: bool,
    is_hi: bool = False,
) -> tuple[
    dict[uuid.UUID, schemas.PublicMedia],
    dict[uuid.UUID, schemas.PublicFaq],
    dict[uuid.UUID, schemas.PublicTestimonial],
    dict[uuid.UUID, schemas.PublicOffer],
]:
    media_ids, faq_ids, testimonial_ids, offer_ids = _collect_block_entity_ids(blocks)

    loaded_media: dict[uuid.UUID, schemas.PublicMedia] = {}
    if media_ids:
        m_stmt = select(Media).where(Media.id.in_(media_ids))
        if prod:
            m_stmt = m_stmt.where(Media.is_sample.is_(False))
        for m in db.scalars(m_stmt).all():
            schema_m = _media_schema(m, prod=prod)
            if schema_m:
                loaded_media[m.id] = schema_m

    loaded_faqs: dict[uuid.UUID, schemas.PublicFaq] = {}
    if faq_ids:
        f_stmt = (
            select(Faq)
            .outerjoin(Project, Faq.project_id == Project.id)
            .where(
                Faq.id.in_(faq_ids),
                Faq.is_visible.is_(True),
                or_(
                    Faq.project_id.is_(None),
                    and_(
                        Project.publish_state == "published",
                        Project.sales_status != "off_market",
                    ),
                ),
            )
        )
        if prod:
            f_stmt = f_stmt.where(
                Faq.is_sample.is_(False),
                or_(Faq.project_id.is_(None), Project.is_sample.is_(False)),
            )
        for f in db.scalars(f_stmt).all():
            loaded_faqs[f.id] = schemas.PublicFaq(
                id=f.id,
                question=translate_text(f.translations, "question", f.question, is_hi=is_hi)
                or f.question,
                answer=translate_text(f.translations, "answer", f.answer, is_hi=is_hi) or f.answer,
                sort_order=f.sort_order,
                is_visible=True,
            )

    loaded_testimonials: dict[uuid.UUID, schemas.PublicTestimonial] = {}
    if testimonial_ids:
        t_stmt = (
            select(Testimonial)
            .outerjoin(Project, Testimonial.project_id == Project.id)
            .where(
                Testimonial.id.in_(testimonial_ids),
                Testimonial.is_visible.is_(True),
                Testimonial.source.isnot(None),
                Testimonial.consent_date.isnot(None),
                or_(
                    Testimonial.project_id.is_(None),
                    and_(
                        Project.publish_state == "published",
                        Project.sales_status != "off_market",
                    ),
                ),
            )
        )
        if prod:
            t_stmt = t_stmt.where(
                or_(Testimonial.project_id.is_(None), Project.is_sample.is_(False))
            )
        t_rows = db.scalars(t_stmt).all()
        t_photo_ids = [t.photo_media_id for t in t_rows if t.photo_media_id]
        t_photos = content_links.library_items(db, t_photo_ids) if t_photo_ids else {}
        for t in t_rows:
            raw_ph = t_photos.get(t.photo_media_id) if t.photo_media_id else None
            ph = _media_schema(raw_ph, prod=prod) if raw_ph else None
            loaded_testimonials[t.id] = schemas.PublicTestimonial(
                id=t.id,
                person_name=t.person_name,
                person_detail=t.person_detail,
                quote=t.quote,
                rating=t.rating,
                photo=ph,
            )

    loaded_offers: dict[uuid.UUID, schemas.PublicOffer] = {}
    if offer_ids:
        now = utcnow()
        off_stmt = select(Offer).where(Offer.id.in_(offer_ids), Offer.is_active.is_(True))
        if prod:
            off_stmt = off_stmt.where(Offer.is_sample.is_(False))
        off_rows = db.scalars(off_stmt).all()

        proj_ids_in_offers = [off.project_id for off in off_rows if off.project_id]
        visible_proj_ids: set[uuid.UUID] = set()
        if proj_ids_in_offers:
            v_stmt = select(Project.id).where(
                Project.id.in_(proj_ids_in_offers),
                Project.publish_state == "published",
                Project.sales_status != "off_market",
            )
            if prod:
                v_stmt = v_stmt.where(Project.is_sample.is_(False))
            visible_proj_ids = set(db.scalars(v_stmt).all())

        off_p_refs = project_queries.project_refs(db, list(visible_proj_ids))
        off_images = content_links.library_items(
            db, [off.image_media_id for off in off_rows if off.image_media_id]
        )
        for off in off_rows:
            if is_live(off, now=now):
                if off.project_id and off.project_id not in visible_proj_ids:
                    continue
                raw_m = off_images.get(off.image_media_id) if off.image_media_id else None
                im = _media_schema(raw_m, prod=prod) if raw_m else None
                pref = off_p_refs.get(off.project_id) if off.project_id else None
                loaded_offers[off.id] = schemas.PublicOffer(
                    id=off.id,
                    title=off.title,
                    body=off.body,
                    image=im,
                    cta_label=off.cta_label,
                    cta_url=off.cta_url,
                    terms=off.terms,
                    terms_url=off.terms_url,
                    placement=off.placement,
                    project_slug=pref.slug if pref else None,
                )

    return loaded_media, loaded_faqs, loaded_testimonials, loaded_offers


def _resolve_media_block(
    data: dict[str, Any],
    b_type: str,
    loaded_media: dict[uuid.UUID, schemas.PublicMedia],
) -> bool:
    if b_type == "image":
        img_id = uuid.UUID(str(data["image_id"])) if data.get("image_id") else None
        if not img_id or img_id not in loaded_media:
            return False
        data["image"] = loaded_media[img_id].model_dump()
    elif b_type == "hero" and data.get("image_id"):
        img_id = uuid.UUID(str(data["image_id"]))
        data["image"] = loaded_media[img_id].model_dump() if img_id in loaded_media else None
    elif b_type == "gallery":
        raw_ids = [uuid.UUID(str(i)) for i in data.get("image_ids", [])]
        valid_images = [loaded_media[i].model_dump() for i in raw_ids if i in loaded_media]
        if not valid_images:
            return False
        data["images"] = valid_images
    return True


def _resolve_faq_block(
    db: Session,
    data: dict[str, Any],
    loaded_faqs: dict[uuid.UUID, schemas.PublicFaq],
    *,
    is_hi: bool,
    prod: bool,
) -> bool:
    # M2: Only treat as picked FAQs if faq_ids is non-empty
    if data.get("faq_ids"):
        picked = [uuid.UUID(str(i)) for i in data["faq_ids"]]
        faqs = [loaded_faqs[i].model_dump() for i in picked if i in loaded_faqs]
        if not faqs:
            return False
        data["faqs"] = faqs
        return True

    pid = uuid.UUID(str(data["project_id"])) if data.get("project_id") else None
    if pid:
        # Check project visibility
        p_check = select(Project.id).where(
            Project.id == pid,
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
        if prod:
            p_check = p_check.where(Project.is_sample.is_(False))
        if not db.scalar(p_check):
            return False

    f_stmt = (
        select(Faq).where(Faq.is_visible.is_(True)).order_by(Faq.sort_order.asc(), Faq.id.asc())
    )
    f_stmt = f_stmt.where(Faq.project_id == pid) if pid else f_stmt.where(Faq.project_id.is_(None))
    if prod:
        f_stmt = f_stmt.where(Faq.is_sample.is_(False))
    data["faqs"] = [
        schemas.PublicFaq(
            id=f.id,
            question=translate_text(f.translations, "question", f.question, is_hi=is_hi)
            or f.question,
            answer=translate_text(f.translations, "answer", f.answer, is_hi=is_hi) or f.answer,
            sort_order=f.sort_order,
            is_visible=True,
        ).model_dump()
        for f in db.scalars(f_stmt).all()
    ]
    return bool(data["faqs"])


def _resolve_testimonial_block(
    db: Session,
    data: dict[str, Any],
    loaded_testimonials: dict[uuid.UUID, schemas.PublicTestimonial],
    *,
    prod: bool,
) -> bool:
    limit = int(data.get("limit") or 3)
    # M2: Only treat as picked testimonials if testimonial_ids is non-empty
    if data.get("testimonial_ids"):
        picked = [uuid.UUID(str(i)) for i in data["testimonial_ids"]]
        tests = [loaded_testimonials[i].model_dump() for i in picked if i in loaded_testimonials]
        if not tests:
            return False
        data["testimonials"] = tests[:limit]
        return True

    pid = uuid.UUID(str(data["project_id"])) if data.get("project_id") else None
    if pid:
        p_check = select(Project.id).where(
            Project.id == pid,
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
        if prod:
            p_check = p_check.where(Project.is_sample.is_(False))
        if not db.scalar(p_check):
            return False

    t_stmt = select(Testimonial).where(
        Testimonial.is_visible.is_(True),
        Testimonial.source.isnot(None),
        Testimonial.consent_date.isnot(None),
    )
    if pid:
        t_stmt = t_stmt.where(Testimonial.project_id == pid)
    t_rows = db.scalars(t_stmt.order_by(Testimonial.created_at.desc()).limit(limit)).all()
    photo_ids = [t.photo_media_id for t in t_rows if t.photo_media_id]
    photos = content_links.library_items(db, photo_ids) if photo_ids else {}

    data["testimonials"] = [
        schemas.PublicTestimonial(
            id=t.id,
            person_name=t.person_name,
            person_detail=t.person_detail,
            quote=t.quote,
            rating=t.rating,
            photo=_media_schema(photos.get(t.photo_media_id), prod=prod)
            if t.photo_media_id
            else None,
        ).model_dump()
        for t in t_rows
    ]
    return bool(data["testimonials"])


def _batch_load_grid_blocks(
    db: Session,
    blocks: Sequence[PageBlock],
    *,
    prod: bool,
    is_hi: bool,
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """Batch-load project_grid and property_grid blocks by kind (Part B Item 3).

    Eliminates redundant per-grid queries by:
    1. Caching project/config list queries across blocks that share query parameters.
    2. Batching all MediaLink lookups (covers, QR, floor plans) across blocks in single queries.
    """
    grid_results: dict[uuid.UUID, list[dict[str, Any]]] = {}

    project_blocks = [b for b in blocks if b.type == "project_grid"]
    property_blocks = [b for b in blocks if b.type == "property_grid"]

    # 1. Batch project_grid blocks
    if project_blocks:
        filter_groups: dict[tuple[Any, ...], list[PageBlock]] = defaultdict(list)
        for b in project_blocks:
            d = b.data or {}
            city_id = uuid.UUID(str(d["city_id"])) if d.get("city_id") else None
            featured_only = bool(d.get("featured_only"))
            status = d.get("status")
            p_ids = tuple(sorted(str(i) for i in d.get("project_ids", [])))
            filter_groups[(city_id, featured_only, status, p_ids)].append(b)

        block_projs: dict[uuid.UUID, list[Project]] = {}
        all_projs: list[Project] = []

        for (city_id, featured_only, status, p_ids), group_blocks in filter_groups.items():
            max_limit = max(int((b.data or {}).get("limit") or 6) for b in group_blocks)
            stmt = (
                select(Project)
                .where(
                    Project.publish_state == "published",
                    Project.sales_status != "off_market",
                )
                .options(
                    joinedload(Project.city),
                    joinedload(Project.locality),
                    selectinload(Project.configurations),
                )
            )
            if prod:
                stmt = stmt.where(Project.is_sample.is_(False))
            if city_id:
                stmt = stmt.where(Project.city_id == city_id)
            if featured_only:
                stmt = stmt.where(Project.is_featured.is_(True))
            if status:
                stmt = stmt.where(Project.status == status)
            if p_ids:
                stmt = stmt.where(Project.id.in_([uuid.UUID(i) for i in p_ids]))

            sales_order = case((Project.sales_status == "available", 0), else_=1)
            featured_order = case((Project.is_featured.is_(True), 0), else_=1)
            stmt = stmt.order_by(
                sales_order,
                featured_order,
                Project.featured_order.asc().nulls_last(),
                Project.possession_date.asc().nulls_last(),
                Project.created_at.desc(),
                Project.id,
            ).limit(max_limit)

            projs = list(db.scalars(stmt).unique().all())
            all_projs.extend(projs)

            for b in group_blocks:
                b_limit = int((b.data or {}).get("limit") or 6)
                block_projs[b.id] = projs[:b_limit]

        all_proj_ids = list({p.id for p in all_projs})
        links_by_p: dict[uuid.UUID, list[MediaLink]] = defaultdict(list)
        qr_by_p: dict[uuid.UUID, Media] = {}
        if all_proj_ids:
            all_links = db.scalars(
                select(MediaLink)
                .where(MediaLink.project_id.in_(all_proj_ids), MediaLink.is_visible.is_(True))
                .options(joinedload(MediaLink.media))
            ).all()
            for lnk in all_links:
                if lnk.project_id:
                    links_by_p[lnk.project_id].append(lnk)
                    if lnk.role == "rera_qr" and lnk.media:
                        qr_by_p[lnk.project_id] = lnk.media

        for b in project_blocks:
            projs = block_projs[b.id]
            items = [
                _build_public_summary(
                    p,
                    links_by_p.get(p.id, []),
                    qr_by_p.get(p.id),
                    [
                        c
                        for c in p.configurations
                        if c.sales_status != "off_market" and (not prod or not c.is_sample)
                    ],
                    is_hi=is_hi,
                ).model_dump()
                for p in projs
            ]
            grid_results[b.id] = items

    # 2. Batch property_grid blocks
    if property_blocks:
        cfg_groups: dict[tuple[Any, ...], list[PageBlock]] = defaultdict(list)
        for b in property_blocks:
            d = b.data or {}
            city_id = uuid.UUID(str(d["city_id"])) if d.get("city_id") else None
            c_ids = tuple(sorted(str(i) for i in d.get("configuration_ids", [])))
            cfg_groups[(city_id, c_ids)].append(b)

        block_configs: dict[uuid.UUID, list[Configuration]] = {}
        all_configs: list[Configuration] = []

        for (city_id, c_ids), group_blocks in cfg_groups.items():
            max_limit = max(int((b.data or {}).get("limit") or 6) for b in group_blocks)
            cfg_stmt = (
                select(Configuration)
                .join(Project, Configuration.project_id == Project.id)
                .where(
                    Configuration.sales_status != "off_market",
                    Project.publish_state == "published",
                    Project.sales_status != "off_market",
                )
            )
            if prod:
                cfg_stmt = cfg_stmt.where(
                    Configuration.is_sample.is_(False), Project.is_sample.is_(False)
                )
            if city_id:
                cfg_stmt = cfg_stmt.where(Project.city_id == city_id)
            if c_ids:
                cfg_stmt = cfg_stmt.where(Configuration.id.in_([uuid.UUID(i) for i in c_ids]))

            cfg_stmt = cfg_stmt.order_by(
                case((Configuration.sales_status == "available", 0), else_=1),
                Configuration.sort_order.asc(),
                Configuration.id.asc(),
            ).limit(max_limit)

            configs = list(db.scalars(cfg_stmt).unique().all())
            all_configs.extend(configs)

            for b in group_blocks:
                b_limit = int((b.data or {}).get("limit") or 6)
                block_configs[b.id] = configs[:b_limit]

        all_c_ids = list({c.id for c in all_configs})
        all_p_ids = list({c.project_id for c in all_configs})

        p_map: dict[uuid.UUID, Project] = {}
        if all_p_ids:
            prop_projs = list(
                db.scalars(
                    select(Project)
                    .where(Project.id.in_(all_p_ids))
                    .options(joinedload(Project.city), joinedload(Project.locality))
                ).all()
            )
            p_map = {p.id: p for p in prop_projs}

        fp_map: dict[uuid.UUID, Media] = {}
        if all_c_ids:
            fp_links = db.scalars(
                select(MediaLink)
                .where(
                    MediaLink.configuration_id.in_(all_c_ids),
                    MediaLink.role == "floor_plan",
                    MediaLink.is_visible.is_(True),
                )
                .options(joinedload(MediaLink.media))
            ).all()
            for lnk in fp_links:
                if lnk.configuration_id and lnk.media:
                    fp_map[lnk.configuration_id] = lnk.media

        qr_by_p = {}
        if all_p_ids:
            qr_links = db.scalars(
                select(MediaLink)
                .where(
                    MediaLink.project_id.in_(all_p_ids),
                    MediaLink.role == "rera_qr",
                    MediaLink.is_visible.is_(True),
                )
                .options(joinedload(MediaLink.media))
            ).all()
            qr_by_p = {
                lnk.project_id: lnk.media for lnk in qr_links if lnk.project_id and lnk.media
            }

        for b in property_blocks:
            configs = block_configs[b.id]
            prop_items = []
            for c in configs:
                p = p_map.get(c.project_id)
                if not p:
                    continue
                qr_m = qr_by_p.get(p.id)
                rera = schemas.PublicRera(
                    authority="UP-RERA",
                    number=p.rera_number,
                    url="https://www.up-rera.in",
                    qr=_media_schema(qr_m, prod=prod) if qr_m else None,
                )
                proj_ref = schemas.PublicProjectRef(
                    slug=p.slug,
                    name=translate_text(p.translations, "name", p.name, is_hi=is_hi) or p.name,
                    status=p.status,
                    city=CityRef(
                        id=p.city.id, name=p.city.name, slug=p.city.slug, state=p.city.state
                    )
                    if p.city
                    else None,
                    locality=LocalityRef(
                        id=p.locality.id, name=p.locality.name, slug=p.locality.slug
                    )
                    if p.locality
                    else None,
                    rera=rera,
                )
                fp_m = fp_map.get(c.id)
                prop_items.append(
                    schemas.PublicPropertySummary(
                        id=c.id,
                        slug=c.slug,
                        name=translate_text(c.translations, "name", c.name, is_hi=is_hi) or c.name,
                        property_type=c.property_type,
                        bhk=float(c.bhk) if c.bhk is not None else None,
                        area=area_of(
                            c.area_min_sqm, c.area_max_sqm, c.area_basis, c.area_display_unit
                        ),
                        price=_public_price(c, project_on_request=bool(p.price_on_request)),
                        sales_status=c.sales_status,
                        cover=_media_schema(fp_m, prod=prod) if fp_m else None,
                        project=proj_ref,
                        is_sample=c.is_sample,
                    ).model_dump()
                )
            grid_results[b.id] = prop_items

    return grid_results


def _resolve_grid_block(
    db: Session,
    data: dict[str, Any],
    b_type: str,
    *,
    is_hi: bool,
    prod: bool,
) -> bool:
    """Fallback single-grid resolver using the unified _batch_load_grid_blocks (S9)."""
    # WHY: transient PageBlock instance passed to _batch_load_grid_blocks
    # without attaching to DB session (Note 9)
    dummy = PageBlock(id=uuid.uuid4(), type=b_type, data=data)
    results = _batch_load_grid_blocks(db, [dummy], prod=prod, is_hi=is_hi)
    items = results.get(dummy.id, [])
    if not items:
        return False
    if b_type == "project_grid":
        data["projects"] = items
    else:
        data["properties"] = items
    return True


def _resolve_single_block(
    db: Session,
    b: PageBlock,
    loaded_media: dict[uuid.UUID, schemas.PublicMedia],
    loaded_faqs: dict[uuid.UUID, schemas.PublicFaq],
    loaded_testimonials: dict[uuid.UUID, schemas.PublicTestimonial],
    loaded_offers: dict[uuid.UUID, schemas.PublicOffer],
    *,
    grid_map: dict[uuid.UUID, list[dict[str, Any]]] | None = None,
    is_hi: bool,
    prod: bool,
) -> tuple[dict[str, Any] | None, bool]:
    data = dict(b.data or {})
    b_type = b.type

    if b_type in ("image", "hero", "gallery"):
        if not _resolve_media_block(data, b_type, loaded_media):
            return None, False
    elif b_type == "video":
        if data.get("media_id"):
            mid = uuid.UUID(str(data["media_id"]))
            if mid not in loaded_media:
                return None, False
            data["media"] = loaded_media[mid].model_dump()
    elif b_type == "map":
        pid = uuid.UUID(str(data["project_id"])) if data.get("project_id") else None
        if not pid:
            return None, False
        p_stmt = (
            select(Project)
            .where(
                Project.id == pid,
                Project.publish_state == "published",
                Project.sales_status != "off_market",
            )
            .options(joinedload(Project.city), joinedload(Project.locality))
        )
        if prod:
            p_stmt = p_stmt.where(Project.is_sample.is_(False))
        p = db.scalar(p_stmt)
        if not p:
            return None, False
        city_name = p.city.name if p.city else None
        locality_name = p.locality.name if p.locality else None
        parts = [p.address_line, locality_name, city_name, p.state, p.pincode]
        full_address = ", ".join([pt for pt in parts if pt])
        data["project"] = {
            "id": str(p.id),
            "slug": p.slug,
            "name": translate_text(p.translations, "name", p.name, is_hi=is_hi) or p.name,
            "lat": float(p.lat) if p.lat is not None else None,
            "lng": float(p.lng) if p.lng is not None else None,
            "address": full_address,
            "directions_url": directions_url(p.lat, p.lng),
        }
    elif b_type == "faq_list":
        if not _resolve_faq_block(db, data, loaded_faqs, is_hi=is_hi, prod=prod):
            return None, False
    elif b_type == "testimonials":
        if not _resolve_testimonial_block(db, data, loaded_testimonials, prod=prod):
            return None, False
    elif b_type == "offer_banner":
        off_id = uuid.UUID(str(data["offer_id"])) if data.get("offer_id") else None
        placement = data.get("placement")
        off_data: schemas.PublicOffer | None = None
        if off_id and off_id in loaded_offers:
            off_data = loaded_offers[off_id]
        elif placement:
            now = utcnow()
            o_stmt = (
                select(Offer)
                .where(
                    Offer.placement == placement,
                    Offer.is_active.is_(True),
                )
                .order_by(Offer.priority.asc(), Offer.id.asc())
            )
            if prod:
                o_stmt = o_stmt.where(Offer.is_sample.is_(False))
            candidate_offers = db.scalars(o_stmt).all()
            cand_pids = [c.project_id for c in candidate_offers if c.project_id]
            visible_pids: set[uuid.UUID] = set()
            p_slugs: dict[uuid.UUID, str] = {}
            if cand_pids:
                p_check = select(Project.id, Project.slug).where(
                    Project.id.in_(cand_pids),
                    Project.publish_state == "published",
                    Project.sales_status != "off_market",
                )
                if prod:
                    p_check = p_check.where(Project.is_sample.is_(False))
                p_rows = db.execute(p_check).all()
                visible_pids = {r[0] for r in p_rows}
                p_slugs = {r[0]: r[1] for r in p_rows}

            cand_img_ids = [c.image_media_id for c in candidate_offers if c.image_media_id]
            cand_images: dict[uuid.UUID, Media] = {}
            if cand_img_ids:
                m_rows = db.scalars(select(Media).where(Media.id.in_(cand_img_ids))).all()
                cand_images = {m.id: m for m in m_rows}

            for cand in candidate_offers:
                if is_live(cand, now=now):
                    if cand.project_id and cand.project_id not in visible_pids:
                        continue
                    raw_im = cand_images.get(cand.image_media_id) if cand.image_media_id else None
                    im = _media_schema(raw_im, prod=prod) if raw_im else None
                    p_slug = p_slugs.get(cand.project_id) if cand.project_id else None
                    off_data = schemas.PublicOffer(
                        id=cand.id,
                        title=cand.title,
                        body=cand.body,
                        image=im,
                        cta_label=cand.cta_label,
                        cta_url=cand.cta_url,
                        terms=cand.terms,
                        terms_url=cand.terms_url,
                        placement=cand.placement,
                        project_slug=p_slug,
                    )
                    break
        if not off_data:
            return None, False
        data["offer"] = off_data.model_dump()
    elif b_type in ("project_grid", "property_grid"):
        if grid_map is not None and b.id in grid_map:
            items = grid_map[b.id]
            if not items:
                return None, False
            if b_type == "project_grid":
                data["projects"] = items
            else:
                data["properties"] = items
        elif not _resolve_grid_block(db, data, b_type, is_hi=is_hi, prod=prod):
            return None, False
    elif b_type == "lead_form":
        if data.get("project_id"):
            pid = uuid.UUID(str(data["project_id"]))
            form_p_stmt = select(Project.id).where(
                Project.id == pid,
                Project.publish_state == "published",
                Project.sales_status != "off_market",
            )
            if prod:
                form_p_stmt = form_p_stmt.where(Project.is_sample.is_(False))
            p_vis = db.scalar(form_p_stmt)
            if not p_vis:
                return None, False
        ct_lead = current_text(db, "lead_form")
        if ct_lead:
            data["consent"] = schemas.PublicConsentText(
                id=ct_lead.id,
                kind=ct_lead.kind,
                version=ct_lead.version,
                body=ct_lead.body,
                checkbox_label=ct_lead.checkbox_label,
            ).model_dump()
        ct_mkt = current_text(db, "marketing")
        if ct_mkt:
            data["marketing_consent"] = schemas.PublicConsentText(
                id=ct_mkt.id,
                kind=ct_mkt.kind,
                version=ct_mkt.version,
                body=ct_mkt.body,
                checkbox_label=ct_mkt.checkbox_label,
            ).model_dump()

    return data, True


def get_public_page(
    db: Session,
    slug: str,
    *,
    locale: str | None = None,
) -> schemas.PublicPage | None:
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    stmt = (
        select(Page)
        .where(Page.slug == slug, Page.publish_state == "published")
        .options(selectinload(Page.blocks))
    )
    if prod:
        stmt = stmt.where(Page.is_sample.is_(False))

    page_row = db.scalar(stmt)
    if not page_row:
        return None

    visible_blocks = [b for b in page_row.blocks if b.is_visible]
    visible_blocks.sort(key=lambda b: (b.sort_order, b.id))

    media_map, faq_map, test_map, offer_map = _batch_load_page_entities(
        db, visible_blocks, prod=prod, is_hi=is_hi
    )
    grid_map = _batch_load_grid_blocks(db, visible_blocks, prod=prod, is_hi=is_hi)

    resolved_blocks: list[schemas.PublicBlock] = []
    for b in visible_blocks:
        data, keep = _resolve_single_block(
            db,
            b,
            media_map,
            faq_map,
            test_map,
            offer_map,
            grid_map=grid_map,
            is_hi=is_hi,
            prod=prod,
        )
        if keep and data is not None:
            resolved_blocks.append(
                schemas.PublicBlock(
                    id=b.id,
                    type=b.type,
                    data=data,
                    sort_order=b.sort_order,
                    is_visible=True,
                )
            )

    seo_obj = dict(page_row.seo or {})
    if page_row.kind == "landing":
        seo_obj["noindex"] = True

    is_draft = is_draft_text(page_row)
    title = (
        translate_text(page_row.translations, "title", page_row.title, is_hi=is_hi)
        or page_row.title
    )

    return schemas.PublicPage(
        id=page_row.id,
        slug=page_row.slug,
        title=title,
        kind=page_row.kind,
        show_in_nav=page_row.show_in_nav,
        nav_order=page_row.nav_order,
        blocks=resolved_blocks,
        legal_version=page_row.legal_version,
        is_draft_text=is_draft,
        seo=_build_public_seo(db, seo_obj, prod=prod),
        updated_at=page_row.updated_at,
    )


# --- Posts -----------------------------------------------------------------------------------


def list_public_posts(
    db: Session,
    paging: PageParams,
    *,
    category: str | None = None,
    tag: str | None = None,
    locale: str | None = None,
) -> schemas.PublicPostList:
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    stmt = select(Post).where(Post.publish_state == "published")
    if prod:
        stmt = stmt.where(Post.is_sample.is_(False))

    if category:
        stmt = stmt.where(Post.category == category)
    if tag:
        stmt = stmt.where(Post.tags.contains([tag]))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = db.scalar(count_stmt) or 0

    paged_stmt = (
        stmt.order_by(Post.published_at.desc().nulls_last(), Post.id.asc())
        .offset(paging.offset)
        .limit(paging.per_page)
    )
    posts = db.scalars(paged_stmt).all()

    covers = content_links.post_covers(db, [p.id for p in posts])
    author_ids = [p.author_id for p in posts if p.author_id]
    authors = user_refs(db, author_ids)

    # R2-S4: Batch-load share images across posts on the page to prevent N+1 queries
    og_ids: list[uuid.UUID] = []
    for p in posts:
        if p.seo and isinstance(p.seo, dict) and p.seo.get("og_image_id"):
            with contextlib.suppress(ValueError, TypeError):
                og_ids.append(uuid.UUID(str(p.seo["og_image_id"])))
    seo_media_map: dict[uuid.UUID, Media] = {}
    if og_ids:
        media_rows = db.scalars(select(Media).where(Media.id.in_(og_ids))).all()
        seo_media_map = {m.id: m for m in media_rows}

    items = [
        schemas.PublicPost(
            id=p.id,
            slug=p.slug,
            title=translate_text(p.translations, "title", p.title, is_hi=is_hi) or p.title,
            excerpt=translate_text(p.translations, "excerpt", p.excerpt, is_hi=is_hi) or p.excerpt,
            body=translate_text(p.translations, "body", p.body, is_hi=is_hi) or p.body,
            cover=_media_schema(covers.get(p.id), prod=prod) if p.id in covers else None,
            category=p.category,
            tags=list(p.tags or []),
            author=authors[p.author_id].name if (p.author_id and p.author_id in authors) else None,
            published_at=p.published_at,
            seo=_build_public_seo(db, p.seo or {}, prod=prod, media_map=seo_media_map),
        )
        for p in posts
    ]

    meta = PageMeta(**paging.meta(total))
    return schemas.PublicPostList(items=items, meta=meta)


def get_public_post(
    db: Session,
    slug: str,
    *,
    locale: str | None = None,
) -> schemas.PublicPost | None:
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    stmt = select(Post).where(Post.slug == slug, Post.publish_state == "published")
    if prod:
        stmt = stmt.where(Post.is_sample.is_(False))

    p = db.scalar(stmt)
    if not p:
        return None

    covers = content_links.post_covers(db, [p.id])
    authors = user_refs(db, [p.author_id] if p.author_id else [])

    return schemas.PublicPost(
        id=p.id,
        slug=p.slug,
        title=translate_text(p.translations, "title", p.title, is_hi=is_hi) or p.title,
        excerpt=translate_text(p.translations, "excerpt", p.excerpt, is_hi=is_hi) or p.excerpt,
        body=translate_text(p.translations, "body", p.body, is_hi=is_hi) or p.body,
        cover=_media_schema(covers.get(p.id), prod=prod) if p.id in covers else None,
        category=p.category,
        tags=list(p.tags or []),
        author=authors[p.author_id].name if (p.author_id and p.author_id in authors) else None,
        published_at=p.published_at,
        seo=_build_public_seo(db, p.seo or {}, prod=prod),
    )


# --- FAQs & Testimonials ---------------------------------------------------------------------


def list_public_faqs(
    db: Session,
    *,
    project_slug: str | None = None,
    locale: str | None = None,
) -> list[schemas.PublicFaq]:
    is_hi = is_hindi_active(db, locale)
    prod = is_production()

    stmt = select(Faq).where(Faq.is_visible.is_(True))
    if prod:
        stmt = stmt.where(Faq.is_sample.is_(False))

    if project_slug:
        proj_stmt = select(Project.id).where(
            Project.slug == project_slug,
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
        if prod:
            proj_stmt = proj_stmt.where(Project.is_sample.is_(False))
        pid = db.scalar(proj_stmt)
        if not pid:
            return []
        stmt = stmt.where(Faq.project_id == pid)
    else:
        stmt = stmt.where(Faq.project_id.is_(None))

    rows = db.scalars(stmt.order_by(Faq.sort_order.asc(), Faq.id.asc())).all()
    return [
        schemas.PublicFaq(
            id=f.id,
            question=translate_text(f.translations, "question", f.question, is_hi=is_hi)
            or f.question,
            answer=translate_text(f.translations, "answer", f.answer, is_hi=is_hi) or f.answer,
            sort_order=f.sort_order,
            is_visible=True,
        )
        for f in rows
    ]


def list_public_testimonials(
    db: Session,
    *,
    project_slug: str | None = None,
) -> list[schemas.PublicTestimonial]:
    prod = is_production()
    stmt = select(Testimonial).where(
        Testimonial.is_visible.is_(True),
        Testimonial.source.isnot(None),
        Testimonial.consent_date.isnot(None),
    )

    if project_slug:
        proj_stmt = select(Project.id).where(
            Project.slug == project_slug,
            Project.publish_state == "published",
            Project.sales_status != "off_market",
        )
        if prod:
            proj_stmt = proj_stmt.where(Project.is_sample.is_(False))
        pid = db.scalar(proj_stmt)
        if not pid:
            return []
        stmt = stmt.where(Testimonial.project_id == pid)

    rows = db.scalars(stmt.order_by(Testimonial.created_at.desc())).all()
    photo_ids = [t.photo_media_id for t in rows if t.photo_media_id]
    photos = content_links.library_items(db, photo_ids) if photo_ids else {}

    return [
        schemas.PublicTestimonial(
            id=t.id,
            person_name=t.person_name,
            person_detail=t.person_detail,
            quote=t.quote,
            rating=t.rating,
            photo=_media_schema(photos.get(t.photo_media_id), prod=prod)
            if t.photo_media_id
            else None,
        )
        for t in rows
    ]


# --- Redirects & Sitemap ---------------------------------------------------------------------


def list_public_redirects(db: Session) -> list[schemas.PublicRedirect]:
    stmt = select(Redirect).where(Redirect.is_active.is_(True)).order_by(Redirect.from_path.asc())
    rows = db.scalars(stmt).all()
    return [
        schemas.PublicRedirect(
            from_path=r.from_path,
            to_path=r.to_path,
            status_code=r.status_code,
        )
        for r in rows
    ]


def get_public_sitemap(db: Session) -> list[schemas.PublicSitemapEntry]:
    prod = is_production()
    hi_on = flags.is_enabled(db, "locale_hi")
    entries: list[schemas.PublicSitemapEntry] = []

    def _add_entry(p_path: str, lastmod: datetime) -> None:
        alts = {"hi": f"/hi{p_path}" if p_path != "/" else "/hi"} if hi_on else {}
        entries.append(
            schemas.PublicSitemapEntry(
                path=p_path,
                lastmod=lastmod,
                alternates=alts,
            )
        )

    # 1. Projects: published, not off-market, not sample in prod, and not noindex
    proj_stmt = select(Project).where(
        Project.publish_state == "published",
        Project.sales_status != "off_market",
    )
    if prod:
        proj_stmt = proj_stmt.where(Project.is_sample.is_(False))
    published_projects = db.scalars(proj_stmt).all()

    # 2. Pages: published, not sample in prod, not landing
    page_stmt = select(Page).where(
        Page.publish_state == "published",
        Page.kind != "landing",
    )
    if prod:
        page_stmt = page_stmt.where(Page.is_sample.is_(False))
    published_pages = db.scalars(page_stmt).all()

    # 3. Posts: published, not sample in prod
    post_stmt = select(Post).where(Post.publish_state == "published")
    if prod:
        post_stmt = post_stmt.where(Post.is_sample.is_(False))
    published_posts = db.scalars(post_stmt).all()

    # S4: Calculate stable home lastmod from maximum updated_at of underlying rows
    all_updated = [p.updated_at for p in published_projects if p.updated_at]
    all_updated.extend([pg.updated_at for pg in published_pages if pg.updated_at])
    all_updated.extend([po.updated_at for po in published_posts if po.updated_at])
    home_lastmod = max(all_updated) if all_updated else utcnow()

    # Add Home "/"
    _add_entry("/", home_lastmod)

    # Add Pages
    for pg in published_pages:
        if pg.slug == "home":
            continue
        seo = dict(pg.seo or {})
        if seo.get("noindex") or is_draft_text(pg):
            continue
        _add_entry(page_path(pg.slug), pg.updated_at or home_lastmod)

    # Calculate Blog index lastmod
    post_updated = [po.updated_at for po in published_posts if po.updated_at]
    blog_lastmod = max(post_updated) if post_updated else home_lastmod
    _add_entry("/blog", blog_lastmod)

    # Add Posts
    for po in published_posts:
        seo = dict(po.seo or {})
        if seo.get("noindex"):
            continue
        _add_entry(post_path(po.slug), po.updated_at or blog_lastmod)

    # Add Projects, then their configurations and the cities they are in (D-041). A noindex
    # project leaves out its configurations too; a city is listed when it has at least one
    # listed project, with that project's latest change as its lastmod.
    listed: dict[uuid.UUID, Project] = {}
    city_lastmod: dict[uuid.UUID, datetime] = {}
    for prj in published_projects:
        seo = dict(prj.seo or {})
        if seo.get("noindex"):
            continue
        lastmod = prj.updated_at or home_lastmod
        _add_entry(project_path(prj.slug), lastmod)
        listed[prj.id] = prj
        if prj.city_id is not None:
            city_lastmod[prj.city_id] = max(city_lastmod.get(prj.city_id, lastmod), lastmod)

    if listed:
        cfg_stmt = (
            select(Configuration)
            .where(
                Configuration.project_id.in_(list(listed)),
                Configuration.sales_status != "off_market",
            )
            .order_by(Configuration.project_id, Configuration.sort_order, Configuration.slug)
        )
        if prod:
            cfg_stmt = cfg_stmt.where(Configuration.is_sample.is_(False))
        for cfg in db.scalars(cfg_stmt).all():
            owner = listed[cfg.project_id]
            _add_entry(
                property_path(owner.slug, cfg.slug),
                max(cfg.updated_at, owner.updated_at or cfg.updated_at),
            )

    if city_lastmod:
        for city in db.scalars(
            select(City).where(City.id.in_(list(city_lastmod))).order_by(City.slug)
        ).all():
            _add_entry(city_path(city.slug), city_lastmod[city.id])

    return entries
