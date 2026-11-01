"""Page blocks: one strict `data` shape per block type (the `*Data` schemas). block_types.py
puts them together into the `Block` and `BlockInput` unions.

Collaborators: block_types.py, block_refs.py (checks the ids a block names against the library,
projects, FAQs, testimonials and offers), page_blocks.py (saves the ordered list).
Implements: the Phase 4 part 4 block list, ARCHITECTURE §6 (FormattedText), SECURITY.md §5.

Rules every shape follows:
  - Unknown fields are refused, every string has a length limit, and no text accepts HTML
    (content/fields.py). Links are a site path or https (no `javascript:`).
  - COMPLIANCE (AGENTS.md "Honest content"): every stat carries where the number comes from
    (`source`) and the date it was true (`as_of`, not in the future). There is no field for a
    countdown anywhere.
  - Media ids, projects, cities, FAQs, testimonials and offers are checked when the page is saved
    (block_refs.py), because that needs the database.
"""

from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Annotated, Final, Self
from urllib.parse import parse_qs, urlsplit

from pydantic import AfterValidator, Field, StringConstraints, model_validator
from pydantic_core import PydanticCustomError

from empire_api.content.fields import (
    Formatted5000,
    Formatted50000,
    Link,
    Para500,
    Plain20,
    Plain40,
    Plain60,
    Plain80,
    Plain120,
    Plain160,
    Plain250,
)
from empire_api.content.vocab import (
    MAX_GALLERY_IMAGES,
    MAX_GRID_CARDS,
    MAX_PICKED,
    MAX_STATS,
    MAX_STEPS,
    FormSource,
    OfferPlacement,
    VideoProvider,
)
from empire_api.projects.fields import BlankIsNone, SchemaExtra, StrictModel, no_duplicates
from empire_api.projects.vocab import ProjectStatus
from empire_api.timeutil import today_ist

READ_ONLY: Final = SchemaExtra({"readOnly": True})
Heading = Annotated[Plain120 | None, BlankIsNone]
Caption = Annotated[Plain250 | None, BlankIsNone]
UniqueIds = Annotated[list[uuid.UUID], AfterValidator(no_duplicates)]


def _one_of(model: object, *names: str, message: str) -> None:
    if sum(getattr(model, name) not in (None, []) for name in names) > 1:
        raise PydanticCustomError("choose_one", message)


class Cta(StrictModel):
    """A button: what it says and where it goes (a site path or an https address)."""

    label: Plain40
    href: Link


class HeroData(StrictModel):
    eyebrow: Annotated[Plain60 | None, BlankIsNone] = None
    heading: Plain120
    subheading: Annotated[Para500 | None, BlankIsNone] = None
    image_id: uuid.UUID | None = Field(
        default=None, description="An image from the library, with an honest label"
    )
    cta: Cta | None = None
    secondary_cta: Cta | None = None


class RichTextData(StrictModel):
    heading: Heading = None
    body: Formatted50000 = Field(description="FormattedText: *bold*, _italic_, - bullets")


class ImageData(StrictModel):
    image_id: uuid.UUID = Field(description="An image from the library, with an honest label")
    caption: Caption = None


class GalleryData(StrictModel):
    heading: Heading = None
    image_ids: Annotated[UniqueIds, Field(min_length=1, max_length=MAX_GALLERY_IMAGES)]


# --- Video: a library video, or a YouTube/Vimeo link stored as its id -------------------------

# SECURITY: only these hosts; the page embeds the provider's player, never an arbitrary URL.
_YOUTUBE_HOSTS: Final = frozenset(
    {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}
)
_VIMEO_HOSTS: Final = frozenset({"vimeo.com", "www.vimeo.com", "player.vimeo.com"})
_YOUTUBE_ID: Final = re.compile(r"^[A-Za-z0-9_-]{11}$")
_VIMEO_ID: Final = re.compile(r"^[0-9]{5,12}$")
VIDEO_LINK_MESSAGE: Final = "Paste a YouTube or Vimeo link starting with https://."


def parse_video_url(url: str) -> tuple[VideoProvider, str]:
    """A YouTube or Vimeo link → (provider, video id), or a staff-readable error."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    segments = [s for s in parts.path.split("/") if s]
    if parts.scheme == "https" and host in _YOUTUBE_HOSTS:
        candidates = parse_qs(parts.query).get("v", [])
        if host == "youtu.be":
            candidates = segments[:1]
        elif len(segments) >= 2 and segments[0] in ("embed", "shorts", "live", "v"):
            candidates = [segments[1]]
        for candidate in candidates:
            if _YOUTUBE_ID.match(candidate):
                return "youtube", candidate
    if parts.scheme == "https" and host in _VIMEO_HOSTS:
        for segment in segments:
            if _VIMEO_ID.match(segment):
                return "vimeo", segment
    raise PydanticCustomError("video_url", VIDEO_LINK_MESSAGE)


def video_watch_url(provider: str, video_id: str) -> str:
    if provider == "youtube":
        return f"https://www.youtube.com/watch?v={video_id}"
    return f"https://vimeo.com/{video_id}"


class VideoData(StrictModel):
    """Send `media_id` (a library video) or `url` (YouTube or Vimeo), not both. A link is stored
    as `provider` + `video_id` and returned as the standard watch link."""

    heading: Heading = None
    caption: Caption = None
    media_id: uuid.UUID | None = None
    url: Annotated[
        Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None,
        BlankIsNone,
    ] = Field(default=None, examples=["https://www.youtube.com/watch?v=XXXXXXXXXXX"])
    provider: Annotated[VideoProvider | None, READ_ONLY] = None
    video_id: Annotated[Annotated[str, StringConstraints(max_length=20)] | None, READ_ONLY] = None

    @model_validator(mode="after")
    def _one_source(self) -> Self:
        if (self.media_id is None) == (self.url is None):
            raise PydanticCustomError(
                "video_source", "Choose a video from the library or paste a YouTube/Vimeo link."
            )
        if self.url is not None:
            self.provider, self.video_id = parse_video_url(self.url)
            self.url = video_watch_url(self.provider, self.video_id)
        else:
            self.provider = self.video_id = None
        return self

    def stored(self) -> dict[str, object]:
        """What the database keeps: the id, never the pasted link (it may carry tracking)."""
        return self.model_dump(mode="json", exclude={"url"})


# --- Listings, forms and references ----------------------------------------------------------


class GridData(StrictModel):
    """Cards of projects (project_grid) or properties (property_grid), filtered."""

    heading: Heading = None
    status: ProjectStatus | None = None
    city_id: uuid.UUID | None = None
    featured_only: bool = False
    limit: Annotated[int, Field(ge=1, le=MAX_GRID_CARDS)] = 6
    show_status_tabs: bool = False


class CtaData(StrictModel):
    heading: Heading = None
    text: Annotated[Para500 | None, BlankIsNone] = None
    label: Plain40
    href: Link


class LeadFormData(StrictModel):
    """Where an enquiry form appears. Submitting it arrives in Phase 5/6 (public intake)."""

    heading: Heading = None
    intro: Annotated[Para500 | None, BlankIsNone] = None
    source: FormSource = "contact_form"
    project_id: uuid.UUID | None = None


class FaqListData(StrictModel):
    """`faq_ids` (chosen FAQs, in this order), or `project_id` (that project's FAQs), or neither
    (the site-wide FAQs)."""

    heading: Heading = None
    project_id: uuid.UUID | None = None
    faq_ids: Annotated[UniqueIds, Field(max_length=MAX_PICKED)] = Field(default_factory=list)

    @model_validator(mode="after")
    def _choose(self) -> Self:
        _one_of(self, "project_id", "faq_ids", message="Choose a project or pick FAQs, not both.")
        return self


def _not_future(value: date) -> date:
    if value > today_ist():
        raise PydanticCustomError("as_of", "The date a number was true can't be in the future.")
    return value


class StatItem(StrictModel):
    """COMPLIANCE: a number on the website must say where it comes from and when it was true."""

    value: Plain20 = Field(examples=["1,200"])
    label: Plain60 = Field(examples=["homes handed over"])
    source: Plain160 = Field(examples=["Possession letters register, Sept 2026"])
    as_of: Annotated[date, AfterValidator(_not_future)]


class StatsData(StrictModel):
    heading: Heading = None
    items: Annotated[list[StatItem], Field(min_length=1, max_length=MAX_STATS)]
    note: Caption = None


class TestimonialsData(StrictModel):
    """`testimonial_ids` (chosen, in this order) or `project_id` (that project's newest), or
    neither (the newest overall). Only real, consented testimonials can ever be shown."""

    heading: Heading = None
    testimonial_ids: Annotated[UniqueIds, Field(max_length=MAX_PICKED)] = Field(
        default_factory=list
    )
    project_id: uuid.UUID | None = None
    limit: Annotated[int, Field(ge=1, le=12)] = 3

    @model_validator(mode="after")
    def _choose(self) -> Self:
        _one_of(
            self,
            "project_id",
            "testimonial_ids",
            message="Choose a project or pick testimonials, not both.",
        )
        return self


class OfferBannerData(StrictModel):
    """One chosen offer, or the highest-priority live offer of a placement."""

    offer_id: uuid.UUID | None = None
    placement: OfferPlacement | None = None

    @model_validator(mode="after")
    def _exactly_one(self) -> Self:
        if (self.offer_id is None) == (self.placement is None):
            raise PydanticCustomError("offer_source", "Choose one offer or a placement.")
        return self


class MapData(StrictModel):
    heading: Heading = None
    project_id: uuid.UUID


class StepItem(StrictModel):
    title: Plain80
    text: Annotated[Para500 | None, BlankIsNone] = None


class StepsData(StrictModel):
    heading: Heading = None
    items: Annotated[list[StepItem], Field(min_length=1, max_length=MAX_STEPS)]


class ColumnItem(StrictModel):
    heading: Annotated[Plain80 | None, BlankIsNone] = None
    body: Formatted5000


class ColumnsData(StrictModel):
    heading: Heading = None
    columns: Annotated[list[ColumnItem], Field(min_length=2, max_length=3)]


class DividerData(StrictModel):
    """A plain line between blocks. No settings."""
