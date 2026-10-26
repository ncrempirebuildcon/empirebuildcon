"""Default settings groups created by `empire-api seed` (never overwrites staff edits).

Values are placeholders until the owner sends company details (tracker o-03). Nothing here is
shown to visitors as fact: the web app renders `[placeholders]` as visibly unfinished.

Phase 4 part 3 adds `lead_routing.single_owner_user_id` (mode `single`: one person instead of
the sales inbox) and the `privacy` group with `lead_retention_years` (SECURITY.md §8). Part 5
adds the Settings screen: every group's fields follow site_settings/groups.py (the `social` and
`email` groups are new; `company.address`, `contacts.whatsapp`/`hours` and
`seo_defaults.description` became `registered_address`, `whatsapp_number`/`office_hours` and
`default_description`; old keys in stored rows are ignored). Groups seeded before a key existed
don't have it; `read_group` fills it from these defaults.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from empire_api.site_settings.models import Setting

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "company": {
        "legal_name": "[Company legal name]",
        "brand_name": "[Brand name]",
        "gstin": None,
        "tagline": None,
        "registered_address": "[Registered office address, city, PIN]",
        "corporate_address": "[Corporate office address, city, PIN]",
    },
    "contacts": {
        "sales_phone": None,
        "whatsapp_number": None,
        "customer_care_phone": None,
        "office_hours": None,
        "sales_email": None,
        "customer_care_email": None,
        "grievance_officer_name": None,
        "privacy_email": None,
        "whatsapp_message": None,
    },
    "social": {"facebook": None, "instagram": None, "youtube": None, "linkedin": None},
    # D-016: everything to one inbox until the owner chooses round robin in Settings.
    "lead_routing": {
        "mode": "single",
        "inbox_email": None,
        "single_owner_user_id": None,
        "round_robin_user_ids": [],
        "round_robin_paused_user_ids": [],
    },
    "regulator": {
        "state": "UP",
        "authority": "UP-RERA",
        "website": "https://www.up-rera.in",
        "promoter_registration_number": None,
        "show_rera_everywhere": True,
    },
    "tracking": {"gtm_id": None, "ga4_id": None, "meta_pixel_id": None, "google_ads_id": None},
    "seo_defaults": {
        "default_title": None,
        "title_suffix": " · Empire",
        "default_description": None,
    },
    "email": {"sender_name": None, "reply_to": None},
    # COMPLIANCE (SECURITY.md §8): leads with no activity for this many years are anonymised by
    # the daily clean-up (leads/erasure.py). Changing the default needs owner approval.
    "privacy": {"lead_retention_years": 3},
}


def read_group(db: Session, key: str) -> dict[str, Any]:
    """A settings group as stored, with any key it lacks filled from the defaults."""
    row = db.get(Setting, key)
    stored = row.value if row is not None and isinstance(row.value, dict) else {}
    return {**DEFAULT_SETTINGS.get(key, {}), **stored}


def seed_settings(db: Session) -> int:
    """Insert missing groups. Returns how many were added."""
    added = 0
    for key, value in DEFAULT_SETTINGS.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=value))
            added += 1
    return added
