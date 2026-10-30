"""Tests for Hindi translations overlay and locale fallback rules (Task 5.1).

Covers:
- D-014: Hindi translations overlay from `translations` column with English fallback.
- `locale_hi` feature flag gating:
  - When `locale_hi` is off: requests with `locale=hi` return English text.
  - When `locale_hi` is on: requests with `locale=hi` return Hindi overlay.
  - If a specific field has no Hindi translation, it falls back to English.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.content.models import Page
from empire_api.projects.models import City, Locality, Project
from empire_api.site_settings.models import FeatureFlag


def _set_locale_hi_flag(db: Session, enabled: bool) -> None:
    flag = db.get(FeatureFlag, "locale_hi")
    if not flag:
        flag = FeatureFlag(
            key="locale_hi",
            enabled=enabled,
            description="Hindi pages",
            is_public=True,
            is_locked=False,
        )
        db.add(flag)
    else:
        flag.enabled = enabled
    db.commit()


def test_public_translations_and_gating(db: Session, client: TestClient) -> None:
    # 1. Seed City & Project with translations
    city = db.scalar(select(City).where(City.slug == "tr-lucknow"))
    if not city:
        city = City(name="Lucknow", slug="tr-lucknow", state="UP")
        db.add(city)
        db.flush()

    locality = db.scalar(select(Locality).where(Locality.slug == "tr-gomti"))
    if not locality:
        locality = Locality(name="Gomti Nagar", slug="tr-gomti", city_id=city.id)
        db.add(locality)
        db.flush()

    project = Project(
        slug="tr-project-1",
        name="Royal Palms",
        tagline="Finest Living in Lucknow",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERATR001",
        price_min_inr=5_000_000,
        price_max_inr=10_000_000,
        translations={
            "hi": {
                "name": "रॉयल पाल्म्स",
                "tagline": "लखनऊ में बेहतरीन जीवनशैली",
            }
        },
    )
    # Page with partial translation (title translated, but no tagline)
    page = Page(
        slug="tr-contact",
        title="Contact Us",
        kind="standard",
        publish_state="published",
        translations={
            "hi": {
                "title": "संपर्क करें",
            }
        },
    )
    db.add_all([project, page])
    db.commit()

    # --- Case 1: locale_hi flag is OFF ---
    _set_locale_hi_flag(db, False)

    # Request with locale=hi should fall back to English
    res_site_off = client.get("/api/v1/public/site?locale=hi").json()
    assert res_site_off["locales"] == ["en"]

    res_p_off = client.get("/api/v1/public/projects/tr-project-1?locale=hi").json()
    assert res_p_off["name"] == "Royal Palms"
    assert res_p_off["tagline"] == "Finest Living in Lucknow"

    res_page_off = client.get("/api/v1/public/pages/tr-contact?locale=hi").json()
    assert res_page_off["title"] == "Contact Us"

    # --- Case 2: locale_hi flag is ON ---
    _set_locale_hi_flag(db, True)

    # Request without locale parameter defaults to English
    res_p_default = client.get("/api/v1/public/projects/tr-project-1").json()
    assert res_p_default["name"] == "Royal Palms"

    # /public/site includes Hindi locale
    res_site_on = client.get("/api/v1/public/site?locale=hi").json()
    assert "hi" in res_site_on["locales"]

    # Request with locale=hi receives Hindi overlay
    res_p_hi = client.get("/api/v1/public/projects/tr-project-1?locale=hi").json()
    assert res_p_hi["name"] == "रॉयल पाल्म्स"
    assert res_p_hi["tagline"] == "लखनऊ में बेहतरीन जीवनशैली"
    # S3: raw translations dictionary must NEVER be exposed in public responses
    assert "translations" not in res_p_hi

    # Page with Hindi title
    res_page_hi = client.get("/api/v1/public/pages/tr-contact?locale=hi").json()
    assert res_page_hi["title"] == "संपर्क करें"
    assert "translations" not in res_page_hi

    # S16: Test partial translation fallback:
    # Seed a project where only name is translated in Hindi, but tagline is missing in hi
    p_partial = Project(
        slug="tr-partial-proj",
        name="Silver Oak",
        tagline="Affordable Comfort in Gomti",
        project_type="residential",
        status="ongoing",
        sales_status="available",
        publish_state="published",
        city_id=city.id,
        locality_id=locality.id,
        rera_number="UPRERATR002",
        translations={
            "hi": {
                "name": "सिल्वर ओक",
                # tagline omitted!
            }
        },
    )
    db.add(p_partial)
    db.commit()

    res_partial_hi = client.get("/api/v1/public/projects/tr-partial-proj?locale=hi").json()
    assert res_partial_hi["name"] == "सिल्वर ओक"  # Translated
    assert res_partial_hi["tagline"] == "Affordable Comfort in Gomti"  # Falls back to English!
    assert "translations" not in res_partial_hi
