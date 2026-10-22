"""Default settings groups created by `empire-api seed` (never overwrites staff edits).

Values are placeholders until the owner sends company details (tracker o-03). Nothing here is
shown to visitors as fact: the web app renders `[placeholders]` as visibly unfinished.
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
    "lead_routing": {"mode": "single", "inbox_email": None, "round_robin_user_ids": []},
    "regulator": {"state": "UP", "authority": "UP-RERA", "website": "https://www.up-rera.in"},
    "tracking": {"gtm_id": None, "ga4_id": None, "meta_pixel_id": None},
    "seo_defaults": {"title_suffix": " · Empire", "description": None},
}


def seed_settings(db: Session) -> int:
    """Insert missing groups. Returns how many were added."""
    added = 0
    for key, value in DEFAULT_SETTINGS.items():
        if db.get(Setting, key) is None:
            db.add(Setting(key=key, value=value))
            added += 1
    return added
