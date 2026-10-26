"""Staff-side shapes of the leads module (design contract schemas Lead, LeadUpdate,
LeadManualCreate, LeadNote, LeadNoteInput, LeadActivity, SiteVisit, SiteVisitUpdate and
UtmReportRow).

Contract changes after the part 3 review: `lost_reason` is a code (LostReason) instead of free
text, with the free text in `lost_reason_note`; Lead gains `same_phone_count`; duplicate links
show only leads the viewer may see.

Contract additions (Phase 4 part 3 report; no renames except `is_test`):
  - Lead: `updated_at`, `last_activity_at`, `language`, `erased_at`, `marketing_consent`,
    `duplicate_of_reference`, `duplicates` (later leads linked to this one), and on `consent`:
    `consent_text_id`, `checkbox_label`, `consent_note`. `is_test` is published as `is_sample`,
    the name every other module uses for seeded rows (D-015). `page_url` is nullable (manual
    leads have no page).
  - The list answers `status_counts` (leads per stage under the same filters, for the board).
  - LeadActivity kinds: `unread`, `details_changed`, `spam_marked`, `duplicate_linked`, `erased`.
  - SiteVisit: `lead_reference`, `lead_phone_e164`, `lead_status`, `lead_owner`, `project.slug`,
    `is_sample`, `created_at`, `updated_at`. SiteVisitUpdate.status is the visit enum.
  - UtmReportRow: `project_id`. The report also groups by `medium`.
  - LeadOwner (GET /admin/lead-owners): the people a lead can be assigned to.

SECURITY (SECURITY.md §5): staff bodies reject unknown fields and every string is bounded.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any

from pydantic import AwareDatetime, Field

from empire_api.leads.fields import (
    Bhk,
    ConsentNote,
    Email,
    Line200,
    Message,
    NoteBody,
    PersonName,
    PhoneInput,
    Text1000,
)
from empire_api.leads.vocab import (
    ActivityKind,
    LeadSource,
    LeadStatus,
    LostReason,
    VisitSlot,
    VisitStatus,
)
from empire_api.projects.fields import BlankIsNone, Inr, OutModel, StrictModel
from empire_api.users.roles import RoleKey
from empire_api.users.schemas import PageMeta, UserRef

# --- Lead (responses) ------------------------------------------------------------------------


class LeadProjectRef(OutModel):
    id: uuid.UUID
    slug: str
    name: str


class LeadConfigurationRef(OutModel):
    id: uuid.UUID
    name: str


class Utm(OutModel):
    source: str | None
    medium: str | None
    campaign: str | None
    term: str | None
    content: str | None


class ClickIds(OutModel):
    gclid: str | None
    gbraid: str | None
    wbraid: str | None
    fbclid: str | None
    msclkid: str | None


class LeadConsentRecord(OutModel):
    """What the person agreed to. Public forms: the text version and label shown. Manual leads:
    staff's note on how consent was given (no text version)."""

    consent_text_id: uuid.UUID | None
    text_version: int | None
    consented_at: datetime
    page_url: str | None
    checkbox_label: str | None
    consent_note: str | None


class LeadRef(OutModel):
    id: uuid.UUID
    reference: str
    source: LeadSource
    created_at: datetime


class SiteVisitProject(OutModel):
    id: uuid.UUID
    slug: str
    name: str


class SiteVisit(OutModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_reference: str
    lead_name: str
    lead_phone_e164: str
    lead_status: LeadStatus
    lead_owner: UserRef | None
    project: SiteVisitProject
    preferred_date: date
    preferred_slot: VisitSlot
    confirmed_for: datetime | None
    status: VisitStatus
    handled_by: UserRef | None
    notes: str | None
    is_sample: bool
    created_at: datetime
    updated_at: datetime


class Lead(OutModel):
    id: uuid.UUID
    reference: str
    created_at: datetime
    updated_at: datetime
    last_activity_at: datetime
    name: str
    phone_e164: str
    email: str | None
    message: str | None
    project: LeadProjectRef | None
    configuration: LeadConfigurationRef | None
    source: LeadSource
    status: LeadStatus
    lost_reason: LostReason | None = Field(
        description="Why the lead was lost (a code; the CMS shows its label). Null unless lost."
    )
    lost_reason_note: str | None = Field(description="Staff's own words; required for `other`")
    owner: UserRef | None
    assigned_at: datetime | None
    read_at: datetime | None
    page_url: str | None
    referrer: str | None
    utm: Utm
    click_ids: ClickIds
    preferred_bhk: float | None
    budget_max_inr: int | None
    preferred_contact_time: str | None
    language: str
    consent: LeadConsentRecord
    marketing_consent: LeadConsentRecord | None = Field(
        description="Null: the optional marketing box was not ticked. Don't add to marketing lists."
    )
    is_spam: bool
    is_sample: bool
    erased_at: datetime | None
    duplicate_of: uuid.UUID | None = Field(
        description="The earlier lead this one repeats (24 h rule), when you may see it; else null"
    )
    duplicate_of_reference: str | None
    duplicates: list[LeadRef] = Field(
        description="Later leads linked to this one that you may see (24 h rule)"
    )
    same_phone_count: int | None = Field(
        description="Leads with this phone number, this one included. Only for leads.erase "
        "(the erase dialog's 'all leads from this person'); null otherwise and once erased."
    )
    next_visit: SiteVisit | None


class LeadStatusCounts(OutModel):
    new: int
    contacted: int
    site_visit: int
    negotiation: int
    booked: int
    lost: int


class LeadList(OutModel):
    items: list[Lead]
    meta: PageMeta
    status_counts: LeadStatusCounts = Field(
        description="Leads per stage under the same filters, ignoring `status` (board columns)"
    )


class LeadOwner(OutModel):
    id: uuid.UUID
    name: str
    role: RoleKey


# --- Lead (requests) -------------------------------------------------------------------------


class LeadUpdate(StrictModel):
    """PATCH body: send only what changes. `owner_user_id` needs leads.assign; `lost` needs a
    `lost_reason` code, and the code `other` needs a `lost_reason_note`."""

    status: LeadStatus | None = None
    lost_reason: LostReason | None = None
    lost_reason_note: Annotated[Line200 | None, BlankIsNone] = None
    owner_user_id: uuid.UUID | None = None
    email: Annotated[Email | None, BlankIsNone] = None
    preferred_bhk: Bhk | None = None
    budget_max_inr: Inr | None = None
    is_spam: bool | None = None
    project_id: uuid.UUID | None = None


class LeadManualCreate(StrictModel):
    """A walk-in or phone enquiry typed in by staff. `consent_note` says how consent was given."""

    name: PersonName
    phone: PhoneInput
    email: Annotated[Email | None, BlankIsNone] = None
    project_id: uuid.UUID | None = None
    source: LeadSource
    message: Annotated[Message | None, BlankIsNone] = None
    owner_user_id: uuid.UUID | None = Field(
        default=None,
        description="Left out: you. Someone else, or null for the sales inbox, needs leads.assign.",
    )
    consent_note: ConsentNote


class LeadNote(OutModel):
    id: uuid.UUID
    author: UserRef
    body: str
    created_at: datetime


class LeadNoteInput(StrictModel):
    body: NoteBody


class LeadActivity(OutModel):
    id: uuid.UUID
    kind: ActivityKind
    actor: UserRef | None
    data: dict[str, Any] = Field(description="Ids, stages and times only; never personal data")
    created_at: datetime


# --- Site visits, report ---------------------------------------------------------------------


class SiteVisitUpdate(StrictModel):
    """Confirm (status `confirmed` + `confirmed_for`), reschedule (a new `confirmed_for`),
    complete, no-show or cancel; plus who handles it and notes."""

    confirmed_for: AwareDatetime | None = None
    status: VisitStatus | None = None
    handled_by_user_id: uuid.UUID | None = None
    notes: Annotated[Text1000 | None, BlankIsNone] = None


class UtmReportRow(OutModel):
    source: str | None
    medium: str | None
    campaign: str | None
    project: str | None
    project_id: uuid.UUID | None
    leads: int
    site_visits: int = Field(description="Leads in this row with at least one visit request")
    booked: int
