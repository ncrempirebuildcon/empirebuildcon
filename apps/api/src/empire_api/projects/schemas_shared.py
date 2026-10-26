"""Value shapes shared by projects and their children (design contract schemas Area, Price,
Seo, Translations, Rera, Location, LocationInput, CityRef, LocalityRef, ReorderRequest), plus
`ReraAccount` (the RERA designated account on the approved design).

WHY Area, Price, Seo, ReraAccount and Translations serve as both request and response shapes:
the contract uses one schema for both, so the web client can send back what it received. Their
read-only `display` fields are computed by the API and ignored on input. They must produce the
same JSON schema in both directions, or FastAPI would split them into `Area-Input` and
`Area-Output`; tests/test_projects_contract.py guards that.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Annotated, Any, Final, Self

from pydantic import (
    AfterValidator,
    Field,
    RootModel,
    StringConstraints,
    model_validator,
)
from pydantic_core import PydanticCustomError

from empire_api.media.schemas import Media
from empire_api.projects import pluscode
from empire_api.projects.fields import (
    BlankIsNone,
    IdList,
    Inr,
    Line40,
    Line60,
    Line70,
    Line100,
    Line120,
    Line160,
    Line170,
    Line300,
    NoHtml,
    OutModel,
    Pincode,
    SchemaExtra,
    SitePath,
    SquareMetres,
    StrictModel,
    no_duplicates,
    no_html,
)
from empire_api.projects.maps import is_google_maps_url
from empire_api.projects.vocab import DEFAULT_STATE, AreaBasis, AreaUnit, PinSource

MAX_LOCALES: Final = 5
# The longest English field that can be translated (a post body, 50,000 characters); each field's
# own limit is checked by `check_translation_fields` (review L1).
MAX_TRANSLATION: Final = 50_000
READ_ONLY: Final = SchemaExtra({"readOnly": True})


class Area(StrictModel):
    """Stored in square metres; shown in `display_unit`. `display` is computed (display.py)."""

    min_sqm: SquareMetres | None = None
    max_sqm: SquareMetres | None = None
    basis: AreaBasis = "carpet"
    display_unit: AreaUnit = "sqft"
    display: Annotated[str, StringConstraints(max_length=200), READ_ONLY] = Field(
        default="", examples=["720 – 1,120 sq ft · 66.9 – 104.1 sq m (carpet)"]
    )


class Price(StrictModel):
    """Total price range and/or rate per unit area, in whole rupees. `on_request` hides the
    numbers in `display` (and, from Phase 5, everywhere on the public site)."""

    on_request: bool = False
    min_inr: Inr | None = None
    max_inr: Inr | None = None
    rate_inr: Inr | None = None
    rate_unit: AreaUnit | None = None
    note: Annotated[Line160 | None, BlankIsNone] = Field(
        default=None, examples=["+ GST and registration"]
    )
    display: Annotated[str, StringConstraints(max_length=200), READ_ONLY] = Field(
        default="", examples=["₹ 85 L – ₹ 1.25 Cr"]
    )


# SECURITY (SECURITY.md §5): the title and description refuse HTML, like every other text
# (review L1); the canonical path is a site path (fields.is_site_path, review M5). A comment, not
# a docstring, so it stays out of the published contract.
class Seo(StrictModel):
    title: Annotated[Annotated[Line70, NoHtml] | None, BlankIsNone] = None
    description: Annotated[Annotated[Line170, NoHtml] | None, BlankIsNone] = None
    # Must be an image in the media library (project_input.validate; 422 otherwise).
    og_image_id: uuid.UUID | None = None
    noindex: bool = False
    canonical_path: Annotated[SitePath | None, BlankIsNone] = None


TranslationText = Annotated[str, StringConstraints(max_length=MAX_TRANSLATION)]
LocaleKey = Annotated[str, StringConstraints(pattern=r"^[a-z]{2}$")]
FieldKey = Annotated[str, StringConstraints(pattern=r"^[a-z_]{1,40}$")]


class Translations(RootModel[dict[LocaleKey, dict[FieldKey, TranslationText]]]):
    """Per-locale overlay of translatable fields, e.g. {"hi": {"name": "…"}}. English lives in
    the base fields and missing translations fall back to it (D-014)."""

    root: dict[LocaleKey, dict[FieldKey, TranslationText]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _limits(self) -> Self:
        if "en" in self.root:
            raise PydanticCustomError(
                "translations_en", "English lives in the normal fields, not in translations."
            )
        if len(self.root) > MAX_LOCALES:
            raise PydanticCustomError("translations_count", "Too many languages.")
        for fields in self.root.values():
            for text in fields.values():
                if "\x00" in text:
                    raise PydanticCustomError("plain_text", "Remove the special characters.")
        return self


def check_translation_fields(
    value: Translations, limits: Mapping[str, int], *, plain_text: bool = False
) -> Translations:
    """Only fields that have an English column may be translated (e.g. name, tagline), each
    within the English field's length (`limits`: field → maximum characters).

    `plain_text`: also refuse HTML, as the English fields of pages, posts and FAQs do
    (SECURITY.md §5, review L1).
    """
    for fields in value.root.values():
        unknown = sorted(set(fields) - set(limits))
        if unknown:
            raise PydanticCustomError(
                "translation_field",
                "These fields can't be translated: {fields}. Allowed: {allowed}.",
                {"fields": ", ".join(unknown), "allowed": ", ".join(sorted(limits))},
            )
        for key, text in fields.items():
            if len(text) > limits[key]:
                raise PydanticCustomError(
                    "translation_length",
                    "The {field} translation can be at most {limit} characters.",
                    {"field": key, "limit": f"{limits[key]:,}"},
                )
            if plain_text:
                no_html(text)
    return value


class ReraAccount(StrictModel):
    """The RERA designated bank account. It is public on the regulator's site, so it is not
    personal data; shown on the project page when filled in."""

    bank_name: Annotated[Line100 | None, BlankIsNone] = None
    account_name: Annotated[Line120 | None, BlankIsNone] = None
    account_number: Annotated[Line40 | None, BlankIsNone] = None


class Rera(OutModel):
    """Shown on every project page and ad block (D-002)."""

    authority: str = Field(examples=["UP-RERA"])
    number: str | None
    url: str | None
    # The project's visible `rera_qr` media link (media/queries.py); null until one is uploaded.
    qr: Media | None


class CityRef(OutModel):
    id: uuid.UUID
    name: str
    slug: str
    state: str


class LocalityRef(OutModel):
    id: uuid.UUID
    name: str
    slug: str


def _google_maps_link(value: str) -> str:
    from urllib.parse import urlsplit  # noqa: PLC0415 — only this validator parses URLs

    if not is_google_maps_url(urlsplit(value)):
        raise PydanticCustomError(
            "google_maps_url",
            "Use a Google Maps link (google.com/maps, maps.google.com or maps.app.goo.gl).",
        )
    return value


def _full_plus_code(value: str) -> str:
    """Keep only the full code from pasted text ("7JWV8XX8+XX Sector 150, Noida" → the code)."""
    code = pluscode.leading_code(value)
    if not pluscode.is_full(code):
        raise PydanticCustomError(
            "plus_code",
            "Enter the full plus code, like 7JWV8XX8+XX. A short code with a town name can't be "
            "placed; use a Google Maps link instead.",
        )
    return code.upper()


# Accepts what staff paste (code + place name, up to 300 characters); stores the code alone.
PlusCodeText = Annotated[Line300, AfterValidator(_full_plus_code)]

GoogleMapsUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=2048),
    AfterValidator(_google_maps_link),
    SchemaExtra({"format": "uri"}),
]


class LocationInput(StrictModel):
    """Where the project is. `pin_source` (an addition to the contract) records how the pin was
    set; when lat/lng are sent without it, the pin counts as typed by hand ("manual")."""

    address_line: Annotated[Line300 | None, BlankIsNone] = None
    city_id: uuid.UUID | None = None
    locality_id: uuid.UUID | None = None
    state: Line60 = Field(default=DEFAULT_STATE, examples=["Uttar Pradesh"])
    pincode: Annotated[Pincode | None, BlankIsNone] = None
    lat: Annotated[float, Field(ge=-90, le=90)] | None = None
    lng: Annotated[float, Field(ge=-180, le=180)] | None = None
    google_maps_url: Annotated[GoogleMapsUrl | None, BlankIsNone] = None
    plus_code: Annotated[PlusCodeText | None, BlankIsNone] = Field(
        default=None,
        description="Full plus code; a place name pasted after it is dropped. Stored uppercase.",
    )
    pin_source: PinSource | None = None


class Location(OutModel):
    address_line: str | None
    city: CityRef | None
    locality: LocalityRef | None
    state: str
    pincode: str | None
    lat: float | None
    lng: float | None
    google_maps_url: str | None
    plus_code: str | None
    pin_source: PinSource | None
    directions_url: Annotated[str | None, READ_ONLY] = Field(
        description="Google Maps directions to the pin; null until a pin is set."
    )


class ReorderRequest(StrictModel):
    ids: Annotated[IdList, AfterValidator(no_duplicates), Field(min_length=1)] = Field(
        description="Full new order: every item of the list, each once."
    )


def model_fields_sent(model: StrictModel) -> dict[str, Any]:
    """The fields the client sent (recursively), for PATCH-style updates."""
    return model.model_dump(exclude_unset=True)
