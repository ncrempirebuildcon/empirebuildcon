"""The settings groups: one strict model per group (what may be stored and how it is checked),
and who may change each group.

Collaborators: site_settings/fields.py (field rules), site_settings/service.py (read, update,
audit), site_settings/defaults.py (seeded values). Implements: the Settings board; ARCHITECTURE
§11 (settings.write, marketing.tracking, seo.manage); D-016 (lead routing); D-002 (UP-RERA);
SECURITY.md §8 (retention).

Rules worth knowing:
  - Every model refuses unknown fields, and every string has a length limit (SECURITY.md §5).
    No settings value is a secret: keys live in the server environment (SECURITY.md §7).
  - COMPLIANCE (D-002, AGENTS.md "Show the UP-RERA number, QR code and up-rera.in on every
    project"): the regulator's state, authority and portal are fixed, and
    `show_rera_everywhere` can't be switched off.
  - COMPLIANCE (SECURITY.md §8): `privacy.lead_retention_years` is 1–10 and only a super-admin
    may change it (it is on the owner-approval list).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated, Final, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from empire_api.leads.fields import Email
from empire_api.projects.fields import (
    BlankIsNone,
    Line70,
    Line80,
    Line120,
    Line170,
    Line300,
    NoHtml,
    no_duplicates,
)
from empire_api.site_settings import fields as f


class GroupModel(BaseModel):
    """A settings group's stored values. Unknown fields are refused (SECURITY.md §5)."""

    # WHY defaults-required: in the spec (responses) every key is listed as present.
    model_config = ConfigDict(extra="forbid", json_schema_serialization_defaults_required=True)


Plain120 = Annotated[Annotated[Line120, NoHtml] | None, BlankIsNone]
Plain80 = Annotated[Annotated[Line80, NoHtml] | None, BlankIsNone]
Plain300 = Annotated[Annotated[Line300, NoHtml] | None, BlankIsNone]
OptionalEmail = Annotated[Email | None, BlankIsNone]
OptionalPhone = Annotated[f.IndianPhone | None, BlankIsNone]


class CompanySettings(GroupModel):
    legal_name: Plain120 = Field(default=None, description="As registered, e.g. on the GST record")
    brand_name: Plain80 = Field(default=None, description="The name visitors know")
    gstin: Annotated[f.Gstin | None, BlankIsNone] = Field(
        default=None, description="15 characters; the last one is a check character"
    )
    tagline: Plain120 = None
    registered_address: Plain300 = None
    corporate_address: Plain300 = Field(
        default=None, description="Shown in the footer and on the Contact page"
    )


class ContactSettings(GroupModel):
    sales_phone: OptionalPhone = Field(default=None, description="Stored as +91XXXXXXXXXX")
    whatsapp_number: OptionalPhone = Field(
        default=None, description="Every WhatsApp button and the mobile bar"
    )
    customer_care_phone: OptionalPhone = None
    office_hours: Plain120 = Field(default=None, description="E.g. Mon–Sat, 10:00–19:00")
    sales_email: OptionalEmail = None
    customer_care_email: OptionalEmail = None
    grievance_officer_name: Plain80 = Field(
        default=None, description="Named in the privacy notice (DPDP Act)"
    )
    privacy_email: OptionalEmail = Field(
        default=None, description="Where buyers ask to see, correct or erase their data"
    )
    whatsapp_message: Annotated[f.WhatsappMessage | None, BlankIsNone] = Field(
        default=None,
        description="The opening message; {page} becomes the page the visitor is on",
    )


class SocialSettings(GroupModel):
    facebook: Annotated[Annotated[f.SocialUrl, f.social_link("facebook")] | None, BlankIsNone] = (
        None
    )
    instagram: Annotated[Annotated[f.SocialUrl, f.social_link("instagram")] | None, BlankIsNone] = (
        None
    )
    youtube: Annotated[Annotated[f.SocialUrl, f.social_link("youtube")] | None, BlankIsNone] = None
    linkedin: Annotated[Annotated[f.SocialUrl, f.social_link("linkedin")] | None, BlankIsNone] = (
        None
    )


class TrackingSettings(GroupModel):
    """Stored only. Nothing loads on the website until the consent banner (Phase 6), and then
    each tag only after the visitor accepts the matching cookie choice."""

    gtm_id: Annotated[f.GtmId | None, BlankIsNone] = None
    ga4_id: Annotated[f.Ga4Id | None, BlankIsNone] = None
    meta_pixel_id: Annotated[f.PixelId | None, BlankIsNone] = None
    google_ads_id: Annotated[f.AdsId | None, BlankIsNone] = None


LeadRoutingMode = Literal["single", "round_robin", "manual"]
UserIds = Annotated[list[uuid.UUID], Field(max_length=50), AfterValidator(no_duplicates)]


class LeadRoutingSettings(GroupModel):
    """D-016 (leads/routing.py applies it): `single` → the person in `single_owner_user_id`, or
    the sales inbox when empty; `round_robin` → in turn through `round_robin_user_ids` (empty:
    every active sales user), skipping anyone in `round_robin_paused_user_ids`; `manual` →
    unassigned until an admin assigns."""

    mode: LeadRoutingMode = "single"
    inbox_email: OptionalEmail = Field(
        default=None,
        description="Every new lead is emailed here; when empty, to every active super-admin",
    )
    single_owner_user_id: uuid.UUID | None = None
    round_robin_user_ids: UserIds = Field(
        default_factory=list, description="The rotation, in order"
    )
    round_robin_paused_user_ids: UserIds = Field(
        default_factory=list, description="In the list but out of rotation for now"
    )


class SeoDefaultsSettings(GroupModel):
    default_title: Annotated[Annotated[Line70, NoHtml] | None, BlankIsNone] = Field(
        default=None, description="Used when a page has no title of its own"
    )
    title_suffix: f.TitleSuffix | None = Field(
        default=None, description="Added after every page title, e.g. ' · Empire'"
    )
    default_description: Annotated[Annotated[Line170, NoHtml] | None, BlankIsNone] = None
    # TODO(phase-5): a default share image (needs the media usage check, so a library delete
    # can't leave it dangling), with the generated images from the board.


REGULATOR_FIXED: Final[dict[str, str]] = {
    "state": "UP",
    "authority": "UP-RERA",
    "website": "https://www.up-rera.in",
}


class RegulatorSettings(GroupModel):
    """COMPLIANCE (module header): only the promoter number can change."""

    state: Literal["UP"] = "UP"
    authority: Literal["UP-RERA"] = "UP-RERA"
    website: Literal["https://www.up-rera.in"] = "https://www.up-rera.in"
    promoter_registration_number: Annotated[f.PromoterNumber | None, BlankIsNone] = Field(
        default=None, description="Only if Empire holds one"
    )
    show_rera_everywhere: Literal[True] = Field(
        default=True, description="Always on (UP-RERA's advertising directions); can't be off"
    )


class EmailSettings(GroupModel):
    """The From address itself is the EMAIL_FROM environment variable."""

    sender_name: Annotated[f.SenderName | None, BlankIsNone] = Field(
        default=None, description="Shown as the sender; empty = 'Empire CMS'"
    )
    reply_to: OptionalEmail = Field(default=None, description="Where replies to alerts go")


class PrivacySettings(GroupModel):
    """COMPLIANCE (module header): super-admin only, 1–10 years."""

    lead_retention_years: int = Field(default=3, ge=1, le=10)


@dataclass(frozen=True)
class GroupSpec:
    key: str
    label: str
    model: type[GroupModel]
    permission: str
    super_admin_only: bool = False


GROUPS: Final[dict[str, GroupSpec]] = {
    spec.key: spec
    for spec in (
        GroupSpec("company", "Company", CompanySettings, "settings.write"),
        GroupSpec("contacts", "Contacts", ContactSettings, "settings.write"),
        GroupSpec("social", "Social links", SocialSettings, "settings.write"),
        GroupSpec("tracking", "Tracking", TrackingSettings, "marketing.tracking"),
        GroupSpec("lead_routing", "Lead routing", LeadRoutingSettings, "settings.write"),
        GroupSpec("seo_defaults", "SEO defaults", SeoDefaultsSettings, "seo.manage"),
        GroupSpec("regulator", "RERA", RegulatorSettings, "settings.write"),
        GroupSpec("email", "Email", EmailSettings, "settings.write"),
        GroupSpec("privacy", "Privacy", PrivacySettings, "settings.write", super_admin_only=True),
    )
}
GroupKey = Literal[
    "company",
    "contacts",
    "social",
    "tracking",
    "lead_routing",
    "seo_defaults",
    "regulator",
    "email",
    "privacy",
]
