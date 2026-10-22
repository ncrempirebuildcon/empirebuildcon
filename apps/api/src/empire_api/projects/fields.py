"""Field types and base models for the projects module's request and response shapes.

SECURITY (SECURITY.md §5): staff bodies reject unknown fields (`StrictModel`), every string has
a length limit and every number has bounds. Strings also refuse control characters: PostgreSQL
rejects a NUL byte with an error (a 500 for us), and single-line fields must stay on one line.

Messages are written for staff ("Use lowercase letters…"), so validators raise
`PydanticCustomError`, whose text reaches the problem+json `errors[]` unchanged.
"""

from __future__ import annotations

import re
import unicodedata
import uuid
from dataclasses import dataclass
from typing import Annotated, Any, Final
from urllib.parse import urlsplit

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    StringConstraints,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema, PydanticCustomError

SLUG_PATTERN: Final = r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
PINCODE_PATTERN: Final = r"^[1-9][0-9]{5}$"
MAX_INR: Final = 10**12  # ₹ 1 lakh crore: far above any project, well inside bigint
MAX_SQM: Final = 10_000_000.0  # 1,000 hectares


@dataclass(frozen=True)
class SchemaExtra:
    """Adds keys to a field's JSON schema (e.g. `pattern`) while a validator gives the message.

    WHY not `Field(json_schema_extra=...)`: Field metadata is ignored inside `X | None` unions.
    """

    extra: dict[str, Any]

    def __hash__(self) -> int:
        return hash(tuple(sorted(self.extra.items())))

    def __get_pydantic_json_schema__(
        self, schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        result = handler(schema)
        result.update(self.extra)
        return result


class StrictModel(BaseModel):
    """Request bodies: unknown fields are an error (SECURITY.md §5)."""

    model_config = ConfigDict(extra="forbid")


class OutModel(BaseModel):
    """Response bodies. Every field is listed as required in the spec, so the generated web
    client never has to guess whether a key is present."""

    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


def _single_line(value: str) -> str:
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise PydanticCustomError("single_line", "Use one line of plain text.")
    return value


def _multi_line(value: str) -> str:
    value = value.replace("\r\n", "\n")
    if any(unicodedata.category(ch) == "Cc" and ch not in "\n\t" for ch in value):
        raise PydanticCustomError("plain_text", "Remove the special characters from this text.")
    return value


def blank_to_none(value: Any) -> Any:
    """ "" or "   " in an optional text field means "clear it"."""
    return None if isinstance(value, str) and not value.strip() else value


def _slug(value: str) -> str:
    if not re.fullmatch(SLUG_PATTERN, value):
        raise PydanticCustomError(
            "slug",
            "Use lowercase letters, numbers and single hyphens, like aurum-heights.",
        )
    return value


def _pincode(value: str) -> str:
    if not re.fullmatch(PINCODE_PATTERN, value):
        raise PydanticCustomError("pincode", "Enter the 6-digit PIN code, like 201306.")
    return value


def _icon_key(value: str) -> str:
    if not re.fullmatch(SLUG_PATTERN, value):
        raise PydanticCustomError(
            "icon_key", "Use an icon key of lowercase letters and hyphens, like swimming-pool."
        )
    return value


def _web_url(value: str) -> str:
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname or " " in value:
        raise PydanticCustomError("url", "Enter a full web address starting with https://.")
    return value


def _site_path(value: str) -> str:
    if not value.startswith("/") or value.startswith("//") or "\\" in value or " " in value:
        raise PydanticCustomError(
            "site_path", "Enter a path on empirebuildcon.com, starting with /, like /projects/x."
        )
    return value


BlankIsNone = BeforeValidator(blank_to_none)


# WHY spelled out one by one: mypy needs real type aliases, not function calls.
Line40 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    AfterValidator(_single_line),
]
Line60 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    AfterValidator(_single_line),
]
Line70 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=70),
    AfterValidator(_single_line),
]
Line80 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=80),
    AfterValidator(_single_line),
]
Line100 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=100),
    AfterValidator(_single_line),
]
Line120 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_single_line),
]
Line160 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=160),
    AfterValidator(_single_line),
]
Line170 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=170),
    AfterValidator(_single_line),
]
Line250 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=250),
    AfterValidator(_single_line),
]
Line300 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(_single_line),
]
Text500 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(_multi_line),
]
Text2000 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    AfterValidator(_multi_line),
]
Text5000 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=5000),
    AfterValidator(_multi_line),
]
Text20000 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20000),
    AfterValidator(_multi_line),
]
Slug = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=120),
    AfterValidator(_slug),
    SchemaExtra({"pattern": SLUG_PATTERN}),
]
WebUrl = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=500),
    AfterValidator(_web_url),
    SchemaExtra({"format": "uri"}),
]
SitePath = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=200), AfterValidator(_site_path)
]
Pincode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=6),
    AfterValidator(_pincode),
    SchemaExtra({"pattern": PINCODE_PATTERN}),
]
IconKey = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=40),
    AfterValidator(_icon_key),
    SchemaExtra({"pattern": SLUG_PATTERN}),
]
Inr = Annotated[int, Field(ge=0, le=MAX_INR, description="Whole rupees")]
SquareMetres = Annotated[float, Field(ge=0, le=MAX_SQM)]
SortOrder = Annotated[int, Field(ge=0, le=100_000)]
Count = Annotated[int, Field(ge=0, le=1_000_000)]
IdList = Annotated[list[uuid.UUID], Field(max_length=500)]


def no_duplicates(values: list[uuid.UUID]) -> list[uuid.UUID]:
    if len(set(values)) != len(values):
        raise PydanticCustomError("duplicates", "Each item can appear only once.")
    return values
