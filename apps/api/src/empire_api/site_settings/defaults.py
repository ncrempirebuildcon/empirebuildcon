"""Default settings groups created by `empire-api seed` (never overwrites staff edits).

Values are placeholders until the owner sends company details (tracker o-03). Nothing here is
shown to visitors as fact: the web app renders `[placeholders]` as visibly unfinished.

Phase 4 part 3 adds `lead_routing.single_owner_user_id` (mode `single`: one person instead of
the sales inbox) and the `privacy` group with `lead_retention_years` (SECURITY.md §8). Groups
seeded before a key existed don't have it; `read_group` fills it from these defaults.
TODO(phase-4): part 5 adds `privacy` to the settings PATCH enum and the Settings screen.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from empire_api.site_settings.models import Setting

DEFAULT_SETTINGS: dict[str, dict[str, Any]] = {
    "company": {
        "legal_name": "[Company legal name]",
        "gstin": None,
        "address": "[Office address, city, PIN]",
    },
    "contacts": {"sales_phone": None, "whatsapp": None, "sales_email": None, "hours": None},
    # D-016: everything to one inbox until the owner chooses round robin in Settings.
    "lead_routing": {
        "mode": "single",
        "inbox_email": None,
        "single_owner_user_id": None,
        "round_robin_user_ids": [],
    },
    "regulator": {"state": "UP", "authority": "UP-RERA", "website": "https://www.up-rera.in"},
    "tracking": {"gtm_id": None, "ga4_id": None, "meta_pixel_id": None},
    "seo_defaults": {"title_suffix": " · Empire", "description": None},
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
