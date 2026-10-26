"""Request and response shapes for FAQs, offers and testimonials (design contract schemas Faq,
FaqInput, Offer, OfferInput, Testimonial and TestimonialInput).

`Faq` moved here from projects/schemas.py (part 1's TODO) under the same name; ProjectAdmin
lists the project's FAQs with it.

Additions to the contract (D-035):
  - PATCH bodies `FaqUpdate`, `OfferUpdate` and `TestimonialUpdate`: every field optional.
  - Faq: `project_name`, `is_sample`, `updated_at`.
  - Offer: `terms` and `terms_url` (needed when the text mentions a price or discount),
    `state` (scheduled, live, ended or inactive, computed), `has_been_live`, `project_name`,
    `is_sample`, `created_at`, `updated_at`.
  - Testimonial: `can_show` (source and consent date are present), `project_name`,
    `created_at`, `updated_at`. `rating` is 1–5 on input too.
Tightened: offer and testimonial times must carry a time zone; a consent date can't be in the
future; offer `placement` is the contract's enum on input too.

SECURITY (SECURITY.md §5): unknown fields are refused, every string is bounded, and no text
accepts HTML (content/fields.py). Links are a site path or https.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final

from pydantic import AfterValidator, AwareDatetime, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from empire_api.content.fields import (
    Formatted4000,
    Link,
    Para500,
    Para1500,
    Plain40,
    Plain80,
    Plain120,
    Plain160,
    Plain200,
    Plain250,
)
from empire_api.content.vocab import OfferPlacement, OfferState
from empire_api.media.schemas import Media
from empire_api.projects.fields import BlankIsNone, OutModel, SortOrder, StrictModel, WebUrl
from empire_api.projects.schemas_shared import Translations, check_translation_fields
from empire_api.timeutil import today_ist
from empire_api.users.schemas import PageMeta

# Translatable fields and their English lengths; translations refuse HTML too (review L1).
FAQ_TRANSLATABLE: Final = {"question": 200, "answer": 4000}
Priority = Annotated[int, Field(ge=0, le=1000, description="Higher shows first")]
Rating = Annotated[int, Field(ge=1, le=5)]


def _faq_translations(value: Translations) -> Translations:
    return check_translation_fields(value, FAQ_TRANSLATABLE, plain_text=True)


def _not_null(value: Any) -> Any:
    if value is None:
        raise PydanticCustomError("not_null", "This can't be empty.")
    return value


def _consent_not_future(value: date | None) -> date | None:
    if value is not None and value > today_ist():
        raise PydanticCustomError("consent_date", "The consent date can't be in the future.")
    return value


FaqTranslations = Annotated[Translations, AfterValidator(_faq_translations)]
ConsentDate = Annotated[date | None, AfterValidator(_consent_not_future)]


# --- FAQs ------------------------------------------------------------------------------------


class Faq(OutModel):
    id: uuid.UUID
    project_id: uuid.UUID | None
    project_name: str | None
    question: str
    answer: str = Field(description="FormattedText")
    sort_order: int
    is_visible: bool
    translations: Translations
    is_sample: bool
    updated_at: datetime


class FaqList(OutModel):
    items: list[Faq]
    meta: PageMeta


class FaqInput(StrictModel):
    """A new FAQ: site-wide (no project) or for one project; added at the end of its list
    unless `sort_order` is given. Showing it on the website needs `content.publish`."""

    project_id: uuid.UUID | None = None
    question: Plain200
    answer: Formatted4000
    sort_order: SortOrder | None = None
    is_visible: bool = True
    translations: FaqTranslations = Field(default_factory=Translations)


class FaqUpdate(StrictModel):
    """PATCH: send only what changes. Moving to another project puts it at the end there."""

    project_id: uuid.UUID | None = None
    question: Plain200 | None = None
    answer: Formatted4000 | None = None
    sort_order: SortOrder | None = None
    is_visible: bool | None = None
    translations: FaqTranslations | None = None

    _required = field_validator("question", "answer", "sort_order", "is_visible", "translations")(
        _not_null
    )


# --- Offers ----------------------------------------------------------------------------------


class Offer(OutModel):
    """Shown only between starts_at and ends_at while active. No countdowns: the website shows
    the end date as plain text, next to the terms."""

    id: uuid.UUID
    title: str
    body: str | None
    image: Media | None
    cta_label: str | None
    cta_url: str | None
    terms: str | None
    terms_url: str | None
    project_id: uuid.UUID | None
    project_name: str | None
    placement: OfferPlacement
    starts_at: datetime | None
    ends_at: datetime | None
    is_active: bool
    priority: int
    state: OfferState = Field(description="Computed now: scheduled, live, ended or inactive")
    has_been_live: bool = Field(description="Once shown, an offer is kept for the record")
    is_sample: bool
    created_at: datetime
    updated_at: datetime


class OfferList(OutModel):
    items: list[Offer]
    meta: PageMeta


def _ends_after_starts(starts: datetime | None, ends: datetime | None) -> None:
    if starts is not None and ends is not None and ends <= starts:
        raise PydanticCustomError("ends_at", "The end must be after the start.")


class OfferInput(StrictModel):
    title: Plain120
    body: Annotated[Para500 | None, BlankIsNone] = None
    image_media_id: uuid.UUID | None = None
    cta_label: Annotated[Plain40 | None, BlankIsNone] = None
    cta_url: Annotated[Link | None, BlankIsNone] = None
    terms: Annotated[Plain250 | None, BlankIsNone] = Field(
        default=None, description="Short terms line, e.g. what the offer includes and until when"
    )
    terms_url: Annotated[Link | None, BlankIsNone] = Field(
        default=None, description="Terms & conditions page"
    )
    project_id: uuid.UUID | None = None
    placement: OfferPlacement
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    is_active: bool = Field(default=False, description="false = saved as a draft")
    priority: Priority = 0

    @field_validator("ends_at")
    @classmethod
    def _dates(cls, value: datetime | None, info: ValidationInfo) -> datetime | None:
        _ends_after_starts(info.data.get("starts_at"), value)
        return value


class OfferUpdate(StrictModel):
    """PATCH: send only what changes. The rules are checked on the merged values."""

    title: Plain120 | None = None
    body: Annotated[Para500 | None, BlankIsNone] = None
    image_media_id: uuid.UUID | None = None
    cta_label: Annotated[Plain40 | None, BlankIsNone] = None
    cta_url: Annotated[Link | None, BlankIsNone] = None
    terms: Annotated[Plain250 | None, BlankIsNone] = None
    terms_url: Annotated[Link | None, BlankIsNone] = None
    project_id: uuid.UUID | None = None
    placement: OfferPlacement | None = None
    starts_at: AwareDatetime | None = None
    ends_at: AwareDatetime | None = None
    is_active: bool | None = None
    priority: Priority | None = None

    _required = field_validator("title", "placement", "is_active", "priority")(_not_null)


# --- Testimonials ----------------------------------------------------------------------------


class Testimonial(OutModel):
    """Real testimonials only. Showing one requires a source and the consent date."""

    id: uuid.UUID
    person_name: str
    person_detail: str | None = Field(examples=["Bought in 2025, Tower B"])
    quote: str
    project_id: uuid.UUID | None
    project_name: str | None
    source: str = Field(examples=["Written feedback form, 2 Mar 2026"])
    source_url: str | None
    consent_date: date | None
    rating: Rating | None
    photo: Media | None
    is_visible: bool
    can_show: bool = Field(description="Source and consent date are recorded")
    created_at: datetime
    updated_at: datetime


class TestimonialList(OutModel):
    items: list[Testimonial]
    meta: PageMeta


class TestimonialInput(StrictModel):
    person_name: Plain80 = Field(description="As the person agreed to be shown")
    person_detail: Annotated[Plain120 | None, BlankIsNone] = None
    quote: Para1500 = Field(description="Their words, unedited")
    project_id: uuid.UUID | None = None
    source: Annotated[Plain160, Field(min_length=3)] = Field(
        description="Where it came from", examples=["Written feedback form, 2 Mar 2026"]
    )
    source_url: Annotated[WebUrl | None, BlankIsNone] = None
    consent_date: ConsentDate = Field(default=None, description="When they agreed to publishing")
    rating: Rating | None = None
    photo_media_id: uuid.UUID | None = None
    is_visible: bool = False


class TestimonialUpdate(StrictModel):
    """PATCH: send only what changes."""

    person_name: Plain80 | None = None
    person_detail: Annotated[Plain120 | None, BlankIsNone] = None
    quote: Para1500 | None = None
    project_id: uuid.UUID | None = None
    source: Annotated[Plain160, Field(min_length=3)] | None = None
    source_url: Annotated[WebUrl | None, BlankIsNone] = None
    consent_date: ConsentDate = None
    rating: Rating | None = None
    photo_media_id: uuid.UUID | None = None
    is_visible: bool | None = None

    _required = field_validator("person_name", "quote", "source", "is_visible")(_not_null)
