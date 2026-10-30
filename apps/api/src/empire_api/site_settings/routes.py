"""Settings and feature-flag endpoints: /api/v1/admin/settings, /settings/{group}, /flags
(design contract tag "Settings").

Collaborators: site_settings/service.py (groups), site_settings/flags.py (flags), mail/status.py
(the email status), leads/routing.py and leads/queries.py (the round-robin table).

Permissions (ARCHITECTURE §11): reading needs `settings.read`. Changing a group needs that
group's permission, checked inside (site_settings/groups.py GROUPS): `settings.write` for most,
`marketing.tracking` for tracking, `seo.manage` for SEO defaults, and for privacy also the
super-admin role. WHY the route marker says `settings.read` (the contract said settings.write):
marketing holds marketing.tracking and seo.manage but not settings.write, and must be able to
save those two groups. `x-permission-by-group` in the spec lists the map. Every group also
needs settings.read (the route's own check), so content editors, who hold seo.manage but not
settings.read, can't save SEO defaults (part 5 review L9: recorded, not changed).
Public site details are served by /api/v1/public/site (Task 5.1).
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Body, Depends, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.db import get_db
from empire_api.errors import problem_responses
from empire_api.leads import queries as lead_queries
from empire_api.leads.routing import rotation_preview
from empire_api.mail.status import transport_status
from empire_api.platform.crypto import client_ip
from empire_api.site_settings import flags
from empire_api.site_settings import groups as g
from empire_api.site_settings.defaults import read_group
from empire_api.site_settings.models import FeatureFlag as FlagRow
from empire_api.site_settings.models import Setting
from empire_api.site_settings.service import can_edit, read_typed, read_values, update_group
from empire_api.users import directory
from empire_api.users import service as user_service
from empire_api.users.deps import require, staff
from empire_api.users.roles import RoleKey, has_permission
from empire_api.users.schemas import UserRef
from empire_api.users.sessions import SessionInfo

router = APIRouter(
    prefix="/api/v1/admin", tags=["Settings"], responses=problem_responses(401, 403, 404, 409, 422)
)
Db = Annotated[Session, Depends(get_db)]
Reader = Annotated[SessionInfo, Depends(require("settings.read"))]


# --- Shapes ----------------------------------------------------------------------------------


class RegulatorView(g.RegulatorSettings):
    """The regulator group as the RERA section shows it (names spelled out, fixed fields)."""

    model_config = ConfigDict(extra="ignore", json_schema_serialization_defaults_required=True)

    state_name: str = "Uttar Pradesh"
    authority_name: str = "Uttar Pradesh Real Estate Regulatory Authority"
    locked_fields: list[str] = Field(
        default=["state", "authority", "website", "show_rera_everywhere"],
        description="Shown locked; a PATCH that changes them is refused (COMPLIANCE)",
    )


class SettingsGroupMeta(BaseModel):
    key: g.GroupKey
    label: str
    permission: str = Field(description="What changing this group needs")
    super_admin_only: bool
    can_edit: bool = Field(description="Whether you can change it")
    updated_at: datetime | None
    updated_by: UserRef | None


class EmailIntegration(BaseModel):
    transport: Literal["resend", "dev"]
    status: Literal["connected", "not_configured", "dev"] = Field(
        description="connected: the key and sender are set (sending problems show in "
        "failed_last_7_days); not_configured: something is missing; dev: development "
        "mailbox, nothing is sent"
    )
    from_address: str | None = Field(description="EMAIL_FROM; the key itself is never shown")
    failed_last_7_days: int


class PlannedIntegration(BaseModel):
    status: Literal["none", "phase_6"]
    note: str


class IntegrationsStatus(BaseModel):
    email: EmailIntegration
    crm: PlannedIntegration
    webhooks: PlannedIntegration
    whatsapp_alerts: PlannedIntegration


class RotationRow(BaseModel):
    position: int = Field(description="1 = first in the rotation")
    user: UserRef
    role: RoleKey | None
    open_leads: int
    in_rotation: bool = Field(description="False: paused, or can't be given leads now")
    can_own: bool = Field(description="Active, own password set, role can open leads")
    gets_next: bool


class SettingsOverview(BaseModel):
    """Every group (typed), plus read-only blocks: per-group meta, the round-robin table and
    the integrations status. Contract change: the contract's free-form map, typed."""

    company: g.CompanySettings
    contacts: g.ContactSettings
    social: g.SocialSettings
    tracking: g.TrackingSettings
    lead_routing: g.LeadRoutingSettings
    seo_defaults: g.SeoDefaultsSettings
    regulator: RegulatorView
    email: g.EmailSettings
    privacy: g.PrivacySettings
    groups: list[SettingsGroupMeta]
    lead_rotation: list[RotationRow]
    integrations: IntegrationsStatus


class FeatureFlag(BaseModel):
    key: str
    title: str
    enabled: bool
    description: str
    who_can_switch: str
    can_switch: bool = Field(description="Whether you can switch it now")
    cannot_switch_reason: str | None
    is_public: bool
    is_locked: bool
    updated_at: datetime | None
    updated_by: UserRef | None


class FlagSwitch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


# --- Settings --------------------------------------------------------------------------------


def _groups_meta(db: Session, role: str) -> list[SettingsGroupMeta]:
    rows = {row.key: row for row in db.scalars(select(Setting).where(Setting.key.in_(g.GROUPS)))}
    refs = directory.user_refs(db, [row.updated_by for row in rows.values()])
    found = []
    for key, spec in g.GROUPS.items():
        row = rows.get(key)
        found.append(
            SettingsGroupMeta(
                key=cast(g.GroupKey, key),
                label=spec.label,
                permission=spec.permission,
                super_admin_only=spec.super_admin_only,
                can_edit=can_edit(role, spec),
                updated_at=row.updated_at if row else None,
                updated_by=refs.get(row.updated_by) if row and row.updated_by else None,
            )
        )
    return found


def _rotation(db: Session) -> list[RotationRow]:
    entries = rotation_preview(db, read_group(db, "lead_routing"))
    ids = [entry.user_id for entry in entries]
    people = directory.names_and_roles(db, ids)
    open_counts = lead_queries.open_leads_by_owner(db, ids)
    rows = []
    for position, entry in enumerate(entries, start=1):
        name, role, _active = people.get(entry.user_id, (directory.UNKNOWN_NAME, None, False))
        rows.append(
            RotationRow(
                position=position,
                user=UserRef(id=entry.user_id, name=name),
                role=cast(RoleKey | None, role),
                open_leads=open_counts.get(entry.user_id, 0),
                in_rotation=entry.in_rotation,
                can_own=entry.can_own,
                gets_next=entry.gets_next,
            )
        )
    return rows


def _integrations(db: Session) -> IntegrationsStatus:
    email = transport_status(db)
    return IntegrationsStatus(
        email=EmailIntegration(
            transport=email.transport,
            status=email.status,
            from_address=email.from_address,
            failed_last_7_days=email.failed_last_7_days,
        ),
        crm=PlannedIntegration(
            status="none",
            note="The CMS leads pipeline is the CRM at launch. Zoho, LeadSquared or another "
            "CRM can be connected later with a webhook.",
        ),
        webhooks=PlannedIntegration(status="phase_6", note="Signed webhooks come in Phase 6."),
        whatsapp_alerts=PlannedIntegration(
            status="phase_6", note="WhatsApp lead alerts need the WhatsApp Business API (Phase 6)."
        ),
    )


def overview(db: Session, role: str) -> SettingsOverview:
    regulator = read_values(db, "regulator")
    return SettingsOverview(
        company=read_typed(db, "company", g.CompanySettings),
        contacts=read_typed(db, "contacts", g.ContactSettings),
        social=read_typed(db, "social", g.SocialSettings),
        tracking=read_typed(db, "tracking", g.TrackingSettings),
        lead_routing=read_typed(db, "lead_routing", g.LeadRoutingSettings),
        seo_defaults=read_typed(db, "seo_defaults", g.SeoDefaultsSettings),
        regulator=RegulatorView.model_validate(regulator.model_dump()),
        email=read_typed(db, "email", g.EmailSettings),
        privacy=read_typed(db, "privacy", g.PrivacySettings),
        groups=_groups_meta(db, role),
        lead_rotation=_rotation(db),
        integrations=_integrations(db),
    )


@router.get(
    "/settings",
    response_model=SettingsOverview,
    operation_id="get_settings",
    summary="All settings groups, who can change each, the round-robin table and the "
    "integrations status (never a key)",
    **staff("settings.read"),
)
def get_settings_overview(actor: Reader, db: Db) -> SettingsOverview:
    return overview(db, actor.user.role)


_BY_GROUP = {key: spec.permission for key, spec in g.GROUPS.items()}
_PATCH_MARKER = staff("settings.read", write=True)
_PATCH_MARKER["openapi_extra"] = {
    **_PATCH_MARKER["openapi_extra"],
    "x-permission-by-group": {
        **_BY_GROUP,
        "seo_defaults": "seo.manage (with settings.read, which the route needs)",
        "privacy": "settings.write + super_admin",
    },
}


@router.patch(
    "/settings/{group}",
    response_model=dict[str, Any],
    operation_id="update_settings_group",
    summary="Update one group (send only what changes; null clears a field)",
    **_PATCH_MARKER,
)
def update_settings_group(
    group: g.GroupKey,
    body: Annotated[dict[str, Any], Body(description="Fields of this group's model")],
    actor: Reader,
    request: Request,
    db: Db,
) -> dict[str, Any]:
    """Each group checks its own permission (module header): 403 without it. Tracking needs
    marketing.tracking; SEO defaults need seo.manage, and the route itself needs settings.read,
    so content editors (seo.manage without settings.read) can't save them; retention (privacy)
    needs the super-admin. Every change is audited with before and after, and announced as
    `settings.updated`."""
    values = update_group(
        db,
        group,
        body,
        actor_id=actor.user.id,
        actor_role=actor.user.role,
        ip=client_ip(request),
    )
    if group == "regulator":
        return RegulatorView.model_validate(values.model_dump()).model_dump(mode="json")
    return values.model_dump(mode="json")


# --- Feature flags ---------------------------------------------------------------------------


def _out(db: Session, row: FlagRow, info: SessionInfo) -> FeatureFlag:
    by = directory.user_refs(db, [row.updated_by]).get(row.updated_by) if row.updated_by else None
    if not has_permission(info.user.role, "flags.manage"):
        reason: str | None = "Switching features needs flags.manage (admins and super-admins)."
    else:
        refused = flags.refusal(
            row,
            not row.enabled,
            role=info.user.role,
            has_two_factor=info.user.two_factor_enabled,
        )
        reason = refused[1] if refused else None
    return FeatureFlag(
        key=row.key,
        title=flags.TITLES.get(row.key) or row.key,
        enabled=row.enabled,
        description=row.description,
        who_can_switch=flags.who_can_switch(row.key),
        can_switch=reason is None,
        cannot_switch_reason=reason,
        is_public=row.is_public,
        is_locked=row.is_locked,
        updated_at=row.updated_at,
        updated_by=by,
    )


@router.get(
    "/flags", response_model=list[FeatureFlag], operation_id="list_flags", **staff("settings.read")
)
def list_flags(actor: Reader, db: Db) -> list[FeatureFlag]:
    """Every flag with what it does, who may switch it, and whether you can now."""
    rows = db.scalars(select(FlagRow).order_by(FlagRow.key)).all()
    return [_out(db, r, actor) for r in rows]


@router.patch(
    "/flags/{key}",
    response_model=FeatureFlag,
    operation_id="set_flag",
    **staff("flags.manage", write=True),
)
def set_flag(
    key: str,
    body: FlagSwitch,
    actor: Annotated[SessionInfo, Depends(require("flags.manage"))],
    request: Request,
    db: Db,
) -> FeatureFlag:
    """Switch a feature on or off. Locked features (not built yet) answer 409. `admin_2fa`:
    super-admins only (403), and switching it on needs your own two-factor on (409); switching
    it on signs out every admin and super-admin without two-factor (audited), so they set it up
    at their next sign-in."""
    ip = client_ip(request)

    def sign_out_without_two_factor(flag: FlagRow) -> dict[str, Any]:
        # SECURITY (part 5 review L1): password-only sessions of admins end when admin_2fa goes on.
        if flag.key != "admin_2fa" or not flag.enabled:
            return {}
        count = user_service.sign_out_admins_without_two_factor(db, actor.user.id, ip)
        return {"accounts_signed_out": [None, count]}

    row = flags.set_flag(
        db,
        key,
        body.enabled,
        actor_id=actor.user.id,
        ip=ip,
        actor_role=actor.user.role,
        actor_has_two_factor=actor.user.two_factor_enabled,
        on_switch=sign_out_without_two_factor,
    )
    return _out(db, row, actor)
