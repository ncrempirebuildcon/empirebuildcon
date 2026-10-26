"""Who gets a new lead: the `lead_routing` setting (D-016), applied in the same transaction as the
insert (ARCHITECTURE §8).

Collaborators: intake.py (public leads), service.py (owner checks), site_settings/defaults.py.
Implements: D-016, ARCHITECTURE §8 (assignment).

Who can be given a lead (`owner_refusal`, the one rule for routing, manual assignment, the
owner list and the Settings checks): an active account whose role can open leads AND that has
set its own password. WHY the password: an invited account can't sign in yet, so a lead given to
it would sit unseen (Phase 4 part 5 fix).

Modes:
  - `single`: the person named in `single_owner_user_id`, if that account is active and may own
    leads; otherwise unassigned, i.e. the sales inbox (the default).
  - `round_robin`: the next person in `round_robin_user_ids` after the last one who got a lead,
    skipping accounts that are inactive or can't own leads, and anyone in
    `round_robin_paused_user_ids` (in the list, out of rotation for now; part 5). An empty list
    means every active sales user, oldest account first.
  - `manual`: unassigned; an admin assigns from the inbox.
A duplicate (same phone and project within 24 h) goes to the original lead's owner when that
owner can still take it, without moving the round-robin turn: one person keeps one buyer.

How round robin stays fair under concurrency:
  1. The turn lives in its own settings row (`system.lead_round_robin`), not in `lead_routing`,
     so a staff edit to the settings never races the turn.
  2. That row is locked FOR UPDATE for the rest of the transaction; a second enquiry arriving at
     the same moment waits, then sees the advanced turn. The lock is held only from the
     assignment to the commit (a few milliseconds).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from empire_api.leads.models import Lead
from empire_api.site_settings.defaults import read_group
from empire_api.site_settings.models import Setting
from empire_api.users import directory
from empire_api.users.roles import has_permission

OWNER_PERMISSION: Final = "leads.read"  # who can own a lead: someone who can open it
ROUND_ROBIN_TURN: Final = "system.lead_round_robin"
DEFAULT_ROUND_ROBIN_ROLE: Final = "sales"


OWNER_INVALID: Final = "Choose an active team member who can open leads."
OWNER_NOT_SET_UP: Final = (
    "This person hasn't set their password yet, so they can't be given leads. Send their "
    "invite again from Users and roles, or choose someone else."
)


def owner_refusal(db: Session, user_id: uuid.UUID) -> str | None:
    """Why this account can't be given a lead (a message for staff), or None when it can."""
    found = directory.standing(db, user_id)
    if found is None or not found.is_active or not has_permission(found.role, OWNER_PERMISSION):
        return OWNER_INVALID
    if not found.has_password:
        return OWNER_NOT_SET_UP
    return None


def can_own(db: Session, user_id: uuid.UUID) -> bool:
    return owner_refusal(db, user_id) is None


def _as_uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def rotation_list(db: Session, config: dict[str, Any]) -> list[uuid.UUID]:
    """The people listed for round robin, in order (empty setting: every sales user who can
    sign in)."""
    listed = [_as_uuid(v) for v in config.get("round_robin_user_ids") or []]
    configured = [user_id for user_id in listed if user_id is not None]
    return configured or directory.ready_users_in_role(db, DEFAULT_ROUND_ROBIN_ROLE)


def _paused(config: dict[str, Any]) -> set[uuid.UUID]:
    found = {_as_uuid(v) for v in config.get("round_robin_paused_user_ids") or []}
    return {user_id for user_id in found if user_id is not None}


def _round_robin_candidates(db: Session, config: dict[str, Any]) -> list[uuid.UUID]:
    paused = _paused(config)
    seen: set[uuid.UUID] = set()
    candidates: list[uuid.UUID] = []
    for user_id in rotation_list(db, config):
        if user_id not in seen and user_id not in paused and can_own(db, user_id):
            seen.add(user_id)
            candidates.append(user_id)
    return candidates


def _after(candidates: list[uuid.UUID], last: uuid.UUID | None) -> uuid.UUID:
    position = candidates.index(last) + 1 if last in candidates else 0
    return candidates[position % len(candidates)]


def _lock_turn(db: Session) -> Setting:
    """The round-robin turn row, created if missing, locked until commit (module header)."""
    db.execute(insert(Setting).values(key=ROUND_ROBIN_TURN, value={}).on_conflict_do_nothing())
    row = db.get(Setting, ROUND_ROBIN_TURN, with_for_update=True, populate_existing=True)
    assert row is not None  # noqa: S101 — inserted just above
    return row


def next_in_turn(db: Session, config: dict[str, Any]) -> uuid.UUID | None:
    turn = _lock_turn(db)
    candidates = _round_robin_candidates(db, config)  # read after the lock: see module header
    if not candidates:
        return None
    chosen = _after(candidates, _as_uuid(turn.value.get("last_user_id")))
    turn.value = {"last_user_id": str(chosen)}  # WHY a new dict: JSONB changes aren't tracked
    return chosen


@dataclass(frozen=True)
class RotationEntry:
    user_id: uuid.UUID
    in_rotation: bool
    can_own: bool
    gets_next: bool


def rotation_preview(db: Session, config: dict[str, Any]) -> list[RotationEntry]:
    """The round-robin table in Settings: who is listed, who is in rotation, who gets the next
    lead. Read only: it doesn't lock or move the turn (the next lead may still go to someone
    else if an enquiry arrives first)."""
    candidates = _round_robin_candidates(db, config)
    turn = db.get(Setting, ROUND_ROBIN_TURN)
    last = _as_uuid(turn.value.get("last_user_id")) if turn is not None else None
    next_user = _after(candidates, last) if candidates else None
    paused = _paused(config)
    entries = []
    for user_id in dict.fromkeys(rotation_list(db, config)):
        owner_ok = can_own(db, user_id)
        entries.append(
            RotationEntry(
                user_id=user_id,
                in_rotation=user_id not in paused and owner_ok,
                can_own=owner_ok,
                gets_next=user_id == next_user,
            )
        )
    return entries


def owner_for_new_lead(db: Session, duplicate_of: Lead | None) -> uuid.UUID | None:
    """The owner a new public lead gets (module header), or None for the sales inbox."""
    original_owner = duplicate_of.owner_user_id if duplicate_of is not None else None
    if original_owner is not None and can_own(db, original_owner):
        return original_owner
    config = read_group(db, "lead_routing")
    mode = config.get("mode")
    if mode == "round_robin":
        return next_in_turn(db, config)
    if mode == "single":
        single = _as_uuid(config.get("single_owner_user_id"))
        return single if single is not None and can_own(db, single) else None
    return None
