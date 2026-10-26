"""Feature-flag service: defaults, lookup and switching (with audit + outbox).

Implements: CODE_STYLE §6, D-004/D-005 (listings and flat inventory not built: locked),
D-014 (`locale_hi`), SECURITY §1 and D-027 (`admin_2fa`: super-admin only, and only with their
own two-factor on), ARCHITECTURE §8 (`captcha`), §18 (`chat_widget`).

To add a flag: append it to DEFAULT_FLAGS, run `empire-api seed`, list it in ARCHITECTURE and
DECISIONS, and remove it again once the feature has been on in production for a month.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

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
    title: str = ""


DEFAULT_FLAGS: tuple[FlagDefault, ...] = (
    FlagDefault(
        "listings",
        "Resale and rental listings. Reserved in the design, not built in version 1 (D-004).",
        is_locked=True,
        title="Resale and rental listings",
    ),
    FlagDefault(
        "unit_inventory",
        "Sold or available per flat. Not built in version 1: availability is tracked per "
        "configuration for now (D-005).",
        is_locked=True,
        title="Flat-by-flat inventory",
    ),
    FlagDefault(
        "chat_widget",
        "The website's chat assistant. Off until Phase 7 is built and reviewed.",
        is_public=True,
        title="Website chat assistant",
    ),
    FlagDefault(
        "locale_hi",
        "Hindi version of the site under /hi/. Switch on once Hindi content exists (D-014).",
        is_public=True,
        title="Hindi pages",
    ),
    FlagDefault(
        "admin_2fa",
        "Asks super-admin and admin accounts for an authenticator-app code at sign-in; anyone "
        "without two-factor sets it up at their next sign-in (SECURITY.md §1). Only a "
        "super-admin who has two-factor on can switch it on.",
        title="Two-factor sign-in for admins",
    ),
    FlagDefault(
        "captcha",
        "A captcha on lead forms, only if spam gets past the hidden honeypot field and the "
        "rate limits.",
        is_public=True,
        title="Captcha on lead forms",
    ),
)
TITLES: dict[str, str] = {flag.key: flag.title for flag in DEFAULT_FLAGS}
# SECURITY (D-027): admins hold flags.manage, but two-factor protects super-admins too, so only a
# super-admin may switch it.
SUPER_ADMIN_ONLY_FLAGS = frozenset({"admin_2fa"})
OWN_TWO_FACTOR_FIRST = (
    "Turn on two-factor sign-in for your own account first (My account), so switching this on "
    "can't lock you out."
)
SUPER_ADMIN_ONLY = "Only a super-admin can change this setting."
NOT_BUILT = "This feature is not built yet, so it can't be switched on."


def who_can_switch(key: str) -> str:
    if key in SUPER_ADMIN_ONLY_FLAGS:
        return "Super-admins only (with their own two-factor on to switch it on)"
    return "Admins and super-admins (flags.manage)"


def refusal(
    row: FeatureFlag, enabled: bool, *, role: str, has_two_factor: bool
) -> tuple[int, str] | None:
    """Why this person can't switch this flag to `enabled`, as (status, message); None = allowed.

    The one place the rules live: the CMS's `can_switch` and the PATCH both ask it.
    SECURITY: switching admin_2fa on is refused unless the super-admin making the change has
    two-factor on themselves; otherwise their next sign-in would demand a set-up they may not be
    able to finish, and with one super-admin nobody could unlock the CMS.
    """
    if row.key in SUPER_ADMIN_ONLY_FLAGS and role != "super_admin":
        return 403, SUPER_ADMIN_ONLY
    if row.is_locked and enabled:
        return 409, NOT_BUILT
    if row.key == "admin_2fa" and enabled and not row.enabled and not has_two_factor:
        return 409, OWN_TWO_FACTOR_FIRST
    return None


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
    db: Session,
    key: str,
    enabled: bool,
    *,
    actor_id: uuid.UUID,
    ip: str | None,
    actor_role: str,
    actor_has_two_factor: bool,
    on_switch: Callable[[FeatureFlag], dict[str, Any]] | None = None,
) -> FeatureFlag:
    """Switch a flag, audited and announced, in one commit.

    `on_switch` runs in the same transaction when the flag really changes, and returns extra
    audit fields (site_settings/routes.py signs admins out when `admin_2fa` goes on).
    """
    row = db.get(FeatureFlag, key, with_for_update=True)
    if row is None:
        raise ApiProblem(404, f"There is no feature flag called '{key}'.")
    refused = refusal(row, enabled, role=actor_role, has_two_factor=actor_has_two_factor)
    if refused is not None:
        raise ApiProblem(refused[0], refused[1])
    if row.enabled == enabled:
        return row
    before = row.enabled
    row.enabled = enabled
    row.updated_by = actor_id
    extra = on_switch(row) if on_switch is not None else {}
    audit.record(
        db,
        action="flag.changed",
        entity_type="feature_flag",
        entity_id=key,
        actor_id=actor_id,
        ip=ip,
        changes={"enabled": [before, enabled], **extra},
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
