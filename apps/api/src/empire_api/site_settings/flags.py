"""Feature-flag service: defaults, lookup and switching (with audit + outbox).

Implements: CODE_STYLE §6, D-004/D-005 (listings and flat inventory not built: locked),
D-014 (`locale_hi`), SECURITY §1 (`admin_2fa`), ARCHITECTURE §8 (`captcha`), §18 (`chat_widget`).

To add a flag: append it to DEFAULT_FLAGS, run `empire-api seed`, list it in ARCHITECTURE and
DECISIONS, and remove it again once the feature has been on in production for a month.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.platform import audit, outbox
from empire_api.site_settings.models import FeatureFlag


@dataclass(frozen=True)
class FlagDefault:
    key: str
    description: str
    enabled: bool = False
    is_public: bool = False
    is_locked: bool = False


DEFAULT_FLAGS: tuple[FlagDefault, ...] = (
    FlagDefault(
        "listings",
        "Resale and rental listings. Not built in version 1 (D-004).",
        is_locked=True,
    ),
    FlagDefault(
        "unit_inventory",
        "Track individual flats as available or sold. Not built in version 1 (D-005).",
        is_locked=True,
    ),
    FlagDefault(
        "chat_widget",
        "Show the chat assistant on the website (Phase 7).",
        is_public=True,
    ),
    FlagDefault(
        "locale_hi",
        "Hindi pages under /hi once Hindi content exists (D-014).",
        is_public=True,
    ),
    FlagDefault(
        "admin_2fa",
        "Ask admins and super-admins for an authenticator code at sign-in (SECURITY.md §1).",
    ),
    FlagDefault(
        "captcha",
        "Add a captcha to lead forms if spam gets through the honeypot and rate limits.",
        is_public=True,
    ),
)


def seed_flags(db: Session) -> int:
    """Insert missing flags; keep the enabled state of existing ones. Returns rows added."""
    existing = {f.key: f for f in db.scalars(select(FeatureFlag)).all()}
    added = 0
    for default in DEFAULT_FLAGS:
        row = existing.get(default.key)
        if row is None:
            db.add(
                FeatureFlag(
                    key=default.key,
                    enabled=default.enabled,
                    description=default.description,
                    is_public=default.is_public,
                    is_locked=default.is_locked,
                )
            )
            added += 1
        else:
            # Descriptions and lock state follow the code; the on/off choice stays with staff.
            row.description = default.description
            row.is_public = default.is_public
            row.is_locked = default.is_locked
            if default.is_locked:
                row.enabled = False
    return added


def is_enabled(db: Session, key: str) -> bool:
    """True when the flag exists and is on. Unknown flags are off (fail closed)."""
    row = db.get(FeatureFlag, key)
    return bool(row and row.enabled and not row.is_locked)


def set_flag(
    db: Session, key: str, enabled: bool, *, actor_id: uuid.UUID, ip: str | None
) -> FeatureFlag:
    row = db.get(FeatureFlag, key)
    if row is None:
        raise ApiProblem(404, f"There is no feature flag called '{key}'.")
    if row.is_locked and enabled:
        raise ApiProblem(409, "This feature is not built yet, so it can't be switched on.")
    if row.enabled == enabled:
        return row
    before = row.enabled
    row.enabled = enabled
    row.updated_by = actor_id
    audit.record(
        db,
        action="flag.changed",
        entity_type="feature_flag",
        entity_id=key,
        actor_id=actor_id,
        ip=ip,
        changes={"enabled": [before, enabled]},
    )
    outbox.emit(
        db,
        type_="flag.changed",
        aggregate_type="feature_flag",
        aggregate_id=key,
        actor_id=actor_id,
        data={"key": key, "enabled": enabled},
    )
    db.commit()
    db.refresh(row)
    return row
