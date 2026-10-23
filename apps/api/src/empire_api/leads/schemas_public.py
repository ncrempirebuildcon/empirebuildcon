"""Request and response shapes of public lead intake (design contract schemas ConsentGiven,
LeadCreate, SiteVisitRequest, BrochureRequest, LeadAccepted and BrochureLink).

Contract additions and deviations (Phase 4 part 3 report):
  - `marketing_consent: ConsentGiven | null` on every intake body: the optional "news and offers"
    box, recorded separately and never assumed (SECURITY.md §8).
  - `website` (the honeypot) accepts up to 200 characters instead of `maxLength: 0`. WHY: a
    validation error would tell a bot which field gave it away; intake answers it like a real
    submission and stores nothing instead (intake.py).
  - `source` excludes `phone` and `manual` on public routes: those are entered by staff.
  - `SiteVisitRequest.project_slug` is required: a visit is always to one project's site.
  - `BrochureLink.expires_at` is nullable and always null: the file's address doesn't expire,
    so any date there would be untrue. `BrochureLink.reference` names the lead created.
  - `page_url` must be a web address or a site path, and `referrer` a web address, because the
    CMS shows them as links (a `javascript:` URL would run in a staff browser).

WHY unknown fields are ignored here (staff bodies reject them): a stray field from a future form
must never cost us an enquiry. The web app uses the generated client, so typos are caught there.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from empire_api.leads.fields import (
    Bhk,
    ClickId,
    Email,
    Line60,
    Message,
    PageUrl,
    PersonName,
    PhoneInput,
    Tag200,
    WebAddress,
)
from empire_api.leads.vocab import Language, PublicSource, VisitSlot
from empire_api.projects.fields import BlankIsNone, Inr, OutModel, SchemaExtra, Slug


class PublicModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ConsentGiven(PublicModel):
    """The visitor ticked the box next to this exact text version."""

    accepted: Literal[True]
    consent_text_id: uuid.UUID
    version: Annotated[int, Field(ge=1)]


class UtmInput(PublicModel):
    source: Annotated[Tag200 | None, BlankIsNone] = None
    medium: Annotated[Tag200 | None, BlankIsNone] = None
    campaign: Annotated[Tag200 | None, BlankIsNone] = None
    term: Annotated[Tag200 | None, BlankIsNone] = None
    content: Annotated[Tag200 | None, BlankIsNone] = None


class ClickIdsInput(PublicModel):
    gclid: Annotated[ClickId | None, BlankIsNone] = None
    gbraid: Annotated[ClickId | None, BlankIsNone] = None
    wbraid: Annotated[ClickId | None, BlankIsNone] = None
    fbclid: Annotated[ClickId | None, BlankIsNone] = None
    msclkid: Annotated[ClickId | None, BlankIsNone] = None


class LeadCreate(PublicModel):
    """An enquiry from a public form. `consent` must name the CURRENT lead-form text."""

    name: PersonName
    phone: PhoneInput
    email: Annotated[Email | None, BlankIsNone] = None
    message: Annotated[Message | None, BlankIsNone] = None
    project_slug: Annotated[Slug | None, BlankIsNone] = None
    configuration_id: uuid.UUID | None = None
    source: PublicSource
    page_url: PageUrl
    referrer: Annotated[WebAddress | None, BlankIsNone] = None
    utm: UtmInput = Field(default_factory=UtmInput)
    click_ids: ClickIdsInput = Field(default_factory=ClickIdsInput)
    preferred_bhk: Bhk | None = None
    budget_max_inr: Inr | None = None
    preferred_contact_time: Annotated[Line60 | None, BlankIsNone] = None
    language: Language = "en"
    consent: ConsentGiven
    marketing_consent: ConsentGiven | None = Field(
        default=None,
        description="Optional box for news and offers. Send it only when the visitor ticked it; "
        "it must name the CURRENT marketing text.",
    )
    website: Annotated[str, StringConstraints(max_length=200), SchemaExtra({"writeOnly": True})] = (
        Field(default="", description="Honeypot. Leave empty; people never see this field.")
    )


class SiteVisitRequest(LeadCreate):
    """A lead plus a visit request for one project (preferred day and time of day)."""

    project_slug: Slug
    preferred_date: date
    preferred_slot: VisitSlot


class BrochureRequest(LeadCreate):
    """A lead for one project; the answer is the brochure's address."""

    project_slug: Slug


class LeadAccepted(OutModel):
    reference: str = Field(examples=["EMP-7K3Q9"])
    message: str


class BrochureLink(OutModel):
    url: str = Field(description="The brochure PDF. Public: anyone with the address can open it.")
    expires_at: datetime | None = Field(
        description="Always null: the address doesn't expire (gating collects a lead, it isn't "
        "access control)."
    )
    reference: str = Field(examples=["EMP-7K3Q9"])
