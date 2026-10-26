"""Settings groups: read them typed, and update one group with its permission, checks, audit row
and `settings.updated` event.

Collaborators: site_settings/groups.py (models, permissions), site_settings/defaults.py (seeded
values), users/directory.py and leads/routing.py (lead-routing checks), platform/audit.py,
platform/outbox.py; site_settings/routes.py (HTTP), mail/brand.py (company lines in emails).
Implements: the Settings board, ARCHITECTURE §9 (`settings.updated`), §11 (permissions).

How an update works:
  1. Who: the group's permission (settings.write, marketing.tracking or seo.manage), and for
     `privacy` also the super-admin role (COMPLIANCE, groups.py).
  2. Lock the group's row FOR UPDATE, so two saves of one group can't lose each other's change.
  3. Merge the body into the stored values (send only what changes; null clears a field) and
     check the result with the group's strict model; regulator's fixed fields and
     `show_rera_everywhere` get plain-English refusals.
  4. Checks that need the database (lead routing: every person newly named must be active and
     able to own leads; people already listed who left don't block saving).
  5. Save, audit with the before/after diff, emit `settings.updated`; one commit.
INVARIANT: no settings value is a secret, so audit diffs hold the values as they are.
"""

from __future__ import annotations

import uuid
from typing import Any, Final

from pydantic import ValidationError
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from empire_api.errors import ApiProblem
from empire_api.leads.routing import OWNER_INVALID, owner_refusal
from empire_api.logs import get_logger
from empire_api.platform import audit, outbox
from empire_api.projects.common import jsonable
from empire_api.site_settings.defaults import DEFAULT_SETTINGS, read_group
from empire_api.site_settings.groups import (
    GROUPS,
    REGULATOR_FIXED,
    GroupModel,
    GroupSpec,
    LeadRoutingSettings,
)
from empire_api.site_settings.models import Setting
from empire_api.users import directory
from empire_api.users.roles import has_permission

INVALID: Final = "Some fields need attention."
FIXED: Final = (
    "UP-RERA is the authority for every Empire project, so the state, authority and portal "
    "are fixed. Another state's authority can be added when Empire launches a project there."
)
RERA_ALWAYS: Final = (
    "The RERA number, QR code and up-rera.in link show on every project page and card. UP-RERA's "
    "advertising directions need them, so this can't be switched off."
)
RETENTION_SUPER_ADMIN: Final = (
    "Only a super-admin can change how long leads are kept (it is on the owner-approval list)."
)
NOT_OWNER: Final = (
    "Choose someone active who can be given leads (a sales user, admin or super-admin)."
)

log = get_logger(__name__)


def spec_for(key: str) -> GroupSpec:
    spec = GROUPS.get(key)
    if spec is None:
        raise ApiProblem(404, f"There is no settings group called '{key}'.")
    return spec


def _known(spec: GroupSpec, stored: dict[str, Any]) -> dict[str, Any]:
    """Only the group's own keys: older rows can hold keys a later part renamed."""
    return {k: v for k, v in stored.items() if k in spec.model.model_fields}


def read_values(db: Session, key: str) -> GroupModel:
    """A group's values, typed. A stored value that no longer passes the checks (e.g. written
    before a rule existed) falls back to its default, with a log line naming the field."""
    spec = spec_for(key)
    values = _known(spec, read_group(db, key))
    try:
        return spec.model.model_validate(values)
    except ValidationError as exc:
        bad = {str(error["loc"][0]) for error in exc.errors() if error["loc"]}
        log.warning("settings_value_ignored", group=key, fields=sorted(bad))
        kept = {k: v for k, v in values.items() if k not in bad}
        try:
            return spec.model.model_validate(kept)
        except ValidationError:
            return spec.model.model_validate(_known(spec, DEFAULT_SETTINGS.get(key, {})))


def read_typed[M: GroupModel](db: Session, key: str, model: type[M]) -> M:
    """`read_values` for callers that know the group's model (mail/brand.py, routes.py)."""
    values = read_values(db, key)
    if not isinstance(values, model):  # pragma: no cover - GROUPS pairs each key with its model
        raise TypeError(f"settings group {key} is not {model.__name__}")
    return values


def can_edit(role: str, spec: GroupSpec) -> bool:
    return has_permission(role, spec.permission) and (
        not spec.super_admin_only or role == "super_admin"
    )


def _errors(exc: ValidationError) -> list[dict[str, str]]:
    found = []
    for error in exc.errors():
        field = ".".join(str(part) for part in error["loc"]) or "request"
        message = error["msg"]
        if error["type"] == "extra_forbidden":
            message = "This field isn't part of this settings group."
        found.append({"field": field, "message": message})
    return found


def _special_refusals(key: str, body: dict[str, Any]) -> list[dict[str, str]]:
    """Step 3: the regulator's fixed values, in words staff understand."""
    if key != "regulator":
        return []
    errors = [
        {"field": name, "message": FIXED}
        for name, fixed in REGULATOR_FIXED.items()
        if name in body and body[name] != fixed
    ]
    if "show_rera_everywhere" in body and body["show_rera_everywhere"] is not True:
        errors.append({"field": "show_rera_everywhere", "message": RERA_ALWAYS})
    return errors


def _check_routing(
    db: Session, routing: LeadRoutingSettings, before: LeadRoutingSettings
) -> list[dict[str, str]]:
    """Step 4: everyone NEWLY named can be given leads (active, own password set, a role that
    opens leads; leads/routing.owner_refusal); paused people are in the list.

    WHY only the new ones (part 5 review M3): someone already in the rotation who later left,
    was demoted or deactivated must not freeze the whole group, or no other field (the inbox,
    the mode) could ever be saved again. Routing already skips them, the overview's
    `lead_rotation` shows them with `can_own: false`, and removing them is always allowed.
    """
    errors = []
    owner = routing.single_owner_user_id
    if owner and owner != before.single_owner_user_id:
        refusal = _owner_message(db, owner)
        if refusal:
            errors.append({"field": "single_owner_user_id", "message": refusal})
    already = set(before.round_robin_user_ids)
    for index, user_id in enumerate(routing.round_robin_user_ids):
        refusal = _owner_message(db, user_id) if user_id not in already else None
        if refusal:
            errors.append({"field": f"round_robin_user_ids.{index}", "message": refusal})
    listed = set(routing.round_robin_user_ids)
    for index, user_id in enumerate(routing.round_robin_paused_user_ids):
        if user_id not in listed:
            errors.append(
                {
                    "field": f"round_robin_paused_user_ids.{index}",
                    "message": "Only someone in the round-robin list can be paused.",
                }
            )
    return errors


def _owner_message(db: Session, user_id: uuid.UUID) -> str | None:
    """leads/routing.owner_refusal in Settings words (an invited account gets its own message)."""
    refusal = owner_refusal(db, user_id)
    return NOT_OWNER if refusal == OWNER_INVALID else refusal


def _lock_row(db: Session, key: str) -> Setting:
    db.execute(
        insert(Setting)
        .values(key=key, value=DEFAULT_SETTINGS.get(key, {}))
        .on_conflict_do_nothing()
    )
    row = db.get(Setting, key, with_for_update=True, populate_existing=True)
    assert row is not None  # noqa: S101 — inserted just above
    return row


def update_group(
    db: Session,
    key: str,
    body: dict[str, Any],
    *,
    actor_id: uuid.UUID,
    actor_role: str,
    ip: str | None,
) -> GroupModel:
    """Steps 1–5 of the module header. Returns the group's new values."""
    spec = spec_for(key)
    if not has_permission(actor_role, spec.permission):  # 1
        raise ApiProblem(403, f"Changing {spec.label} settings needs {spec.permission}.")
    if spec.super_admin_only and actor_role != "super_admin":
        raise ApiProblem(403, RETENTION_SUPER_ADMIN)
    special = _special_refusals(key, body)
    if special:
        raise ApiProblem(422, INVALID, errors=special)
    row = _lock_row(db, key)  # 2
    before = read_values(db, key)
    merged = {**before.model_dump(mode="json"), **body}  # 3
    try:
        after = spec.model.model_validate(merged)
    except ValidationError as exc:
        raise ApiProblem(422, INVALID, errors=_errors(exc)) from None
    if isinstance(after, LeadRoutingSettings):  # 4
        assert isinstance(before, LeadRoutingSettings)  # noqa: S101 — same group, same model
        routing_errors = _check_routing(db, after, before)
        if routing_errors:
            raise ApiProblem(422, INVALID, errors=routing_errors)
    old, new = jsonable(before.model_dump(mode="json")), jsonable(after.model_dump(mode="json"))
    delta = audit.diff(old, new)
    if not delta:
        return after
    row.value = {**_known(spec, row.value or {}), **new}  # 5 (WHY a new dict: JSONB tracking)
    row.updated_by = actor_id
    audit.record(
        db,
        action="settings.updated",
        entity_type="setting",
        entity_id=key,
        actor_id=actor_id,
        ip=ip,
        changes=delta,
    )
    outbox.emit(
        db,
        type_="settings.updated",
        aggregate_type="setting",
        aggregate_id=key,
        actor_id=actor_id,
        data={"group": key, "changed": sorted(delta)},
    )
    db.commit()
    return after


def updated_by_names(db: Session, rows: list[Setting]) -> dict[uuid.UUID, str]:
    refs = directory.user_refs(db, [row.updated_by for row in rows])
    return {user_id: ref.name for user_id, ref in refs.items()}
