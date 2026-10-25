"""Request and response shapes of the media module (design contract schemas Media, LinkedMedia,
MediaUpdate, MediaLinkInput, MediaLinkUpdate, ImageUpload, UploadSignatureRequest,
UploadSignature, UploadConfirm and ReorderRequest, the last shared with projects).

Additions to the contract (recorded in D-033):
  - Media: `label` and `label_month` (the honest label), `is_sample`, and `attached_count` (how
    many owners use the file; the library allows delete only at 0).
  - MediaUpdate: `label` and `label_month`. ImageUpload: `label` and `label_month` too.
  - UploadSignature: `resource_type` may also be `image` (PDFs are images at Cloudinary),
    `fields` (every form field to send with the file, already signed) and `expires_at`.
  - GET /admin/media: the `unattached=true` filter.

SECURITY (SECURITY.md §5): staff bodies reject unknown fields and every string is bounded.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final, Literal, get_args

from pydantic import AfterValidator, Field, ValidationInfo, field_validator
from pydantic_core import PydanticCustomError

from empire_api.media.vocab import DirectKind, MediaKind, MediaLabel, MediaRole, ResourceType
from empire_api.projects.fields import (
    BlankIsNone,
    Line160,
    Line250,
    OutModel,
    SchemaExtra,
    StrictModel,
)
from empire_api.users.schemas import PageMeta

ATTACH_TO_PATTERN: Final = (
    r"^(project|configuration|construction_update):"
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
READ_ONLY: Final = SchemaExtra({"readOnly": True})


def check_attach_to(value: str) -> str:
    if not re.fullmatch(ATTACH_TO_PATTERN, value):
        raise PydanticCustomError(
            "attach_to",
            "Use owner_type:owner_id, like project:<id>, configuration:<id> or "
            "construction_update:<id>.",
        )
    return value.lower()


AttachTo = Annotated[
    str,
    Field(max_length=80, description="owner_type:owner_id, e.g. project:<uuid>"),
    AfterValidator(check_attach_to),
    SchemaExtra({"pattern": ATTACH_TO_PATTERN}),
]


class Media(OutModel):
    """A file in the media library, with delivery URLs built by the store (media/store.py)."""

    id: uuid.UUID
    kind: MediaKind
    url: str = Field(
        description="Images: width-limited f_auto,q_auto copy. PDFs open in the browser; "
        "other documents download. Videos: the original file."
    )
    thumbnail_url: str | None = Field(description="Small image; a poster for videos and PDFs")
    title: str
    alt_text: str | None
    format: str = Field(examples=["jpg", "mp4", "pdf"])
    bytes: int
    width: int | None
    height: int | None
    duration_s: float | None
    created_at: datetime
    label: MediaLabel | None = Field(
        description="Honest label: artist's impression, actual photo or progress photo"
    )
    label_month: date | None = Field(
        description="First day of the month the photo shows (required for progress photos)"
    )
    is_sample: bool = Field(description="Sample placeholder from the seed — never shown live")
    attached_count: Annotated[int, READ_ONLY] = Field(
        description="How many places use it: project media, share images, page blocks, post "
        "covers, offer images and testimonial photos (delete needs 0; see /usage for where)"
    )


class LinkedMedia(Media):
    """A media item as attached to an owner (project, configuration, construction update)."""

    link_id: uuid.UUID
    role: MediaRole
    sort_order: int
    is_cover: bool
    is_visible: bool


class MediaUse(OutModel):
    """One place a library item is used (GET /admin/media/{id}/usage, an addition in part 4)."""

    owner_type: Literal[
        "project", "configuration", "construction_update", "page", "post", "offer", "testimonial"
    ]
    owner_id: uuid.UUID
    project_id: uuid.UUID | None = Field(
        description="For project, configuration and update owners: the project to open"
    )
    name: str = Field(description="The project, page, post or offer title; a buyer's name")
    role: str = Field(
        examples=["gallery", "floor_plan", "block", "cover", "share_image", "image", "photo"]
    )


class MediaList(OutModel):
    items: list[Media]
    meta: PageMeta


def label_problem(label: str | None, month: date | None) -> str | None:
    """COMPLIANCE: a progress photo always names its month; an impression has none.

    Returns the message for staff, or None when the pair is fine. Also used by
    library.update_media on the merged (stored + sent) values.
    """
    if label == "progress_photo" and month is None:
        return "Add the month this progress photo shows (label_month)."
    if month is not None and label not in ("actual_photo", "progress_photo"):
        return "Only actual photos and progress photos carry a month."
    return None


class MediaUpdate(StrictModel):
    """PATCH a library item: send only what changes. Labels are checked together with the
    stored values (library.update_media)."""

    title: Line160 | None = None
    alt_text: Annotated[Line250 | None, BlankIsNone] = None
    label: MediaLabel | None = None
    label_month: date | None = Field(
        default=None, description="Any day of the month; stored as the first day"
    )

    @field_validator("title")
    @classmethod
    def _title_not_null(cls, value: str | None) -> str | None:
        if value is None:
            raise PydanticCustomError("not_null", "This can't be empty.")
        return value


class MediaLinkInput(StrictModel):
    media_id: uuid.UUID
    attach_to: AttachTo
    role: MediaRole
    is_visible: bool = True


class MediaLinkUpdate(StrictModel):
    is_visible: bool | None = None
    is_cover: bool | None = None

    @field_validator("is_visible", "is_cover")
    @classmethod
    def _not_null(cls, value: bool | None) -> bool | None:
        if value is None:
            raise PydanticCustomError("not_null", "Send true or false.")
        return value


# --- Uploads ---------------------------------------------------------------------------------

Filename = Annotated[str, Field(min_length=1, max_length=200)]
MimeType = Annotated[str, Field(max_length=200)]


class UploadSignatureRequest(StrictModel):
    kind: DirectKind
    filename: Filename = Field(description="Only its extension is used; never stored")
    bytes: Annotated[int, Field(ge=1)]
    mime_type: MimeType = Field(description="The browser's type for the file ('' if unknown)")


class UploadSignature(OutModel):
    """Everything the browser needs to POST the file straight to the store."""

    upload_url: str
    api_key: str
    timestamp: int
    signature: str
    folder: str
    public_id: str = Field(description="Signed public id (inside `folder`)")
    resource_type: ResourceType
    max_bytes: int
    fields: dict[str, str] = Field(
        description="Send every one of these form fields with `file`, unchanged"
    )
    expires_at: datetime = Field(description="Confirm before this time")


def role_with_attach_to(role: str | None, info: ValidationInfo) -> str | None:
    """`role` goes with `attach_to`: both or neither (runs even when role is left out)."""
    if (info.data.get("attach_to") is None) != (role is None):
        raise PydanticCustomError("role", "Send attach_to and role together, or neither of them.")
    return role


class UploadConfirm(StrictModel):
    cloudinary_response: dict[str, Any] = Field(
        description="The JSON the store returned to the browser, unmodified"
    )
    title: Line160 | None = None
    attach_to: AttachTo | None = None
    role: MediaRole | None = Field(default=None, validate_default=True)

    _role = field_validator("role")(role_with_attach_to)


class ImageUploadFields(StrictModel):
    """The text fields of the multipart photo upload (ImageUpload without `file`)."""

    title: Line160 | None = None
    alt_text: Annotated[Line250 | None, BlankIsNone] = None
    attach_to: Annotated[AttachTo | None, BlankIsNone] = None
    role: Annotated[MediaRole | None, BlankIsNone] = Field(default=None, validate_default=True)
    label: Annotated[MediaLabel | None, BlankIsNone] = None
    label_month: Annotated[date | None, BlankIsNone] = Field(default=None, validate_default=True)

    _role = field_validator("role")(role_with_attach_to)

    @field_validator("label_month")
    @classmethod
    def _label_month(cls, value: date | None, info: ValidationInfo) -> date | None:
        problem = label_problem(info.data.get("label"), value)
        if problem:
            raise PydanticCustomError("label_month", problem)
        return value


# WHY written out: the photo endpoint reads its multipart body itself, with a hard size cap
# (media/multipart.py), so FastAPI can't derive the schema from parameters. main.py adds this
# to components.schemas under the contract's name.
IMAGE_UPLOAD_SCHEMA: Final[dict[str, Any]] = {
    "type": "object",
    "properties": {
        "file": {
            "type": "string",
            "format": "binary",
            "description": (
                "JPEG, PNG, WebP or AVIF, at most 10 MB and 25 megapixels. Embedded metadata "
                "(EXIF with GPS, XMP, IPTC, comments) is removed on the server and the EXIF "
                "orientation applied, so width/height are as displayed."
            ),
        },
        "title": {"type": "string", "maxLength": 160},
        "alt_text": {"type": "string", "maxLength": 250},
        "attach_to": {
            "type": "string",
            "pattern": ATTACH_TO_PATTERN,
            "description": "owner_type:owner_id, e.g. project:<uuid>",
        },
        "role": {"type": "string", "enum": list(get_args(MediaRole))},
        "label": {"type": "string", "enum": list(get_args(MediaLabel))},
        "label_month": {"type": "string", "format": "date"},
    },
    "required": ["file"],
}
