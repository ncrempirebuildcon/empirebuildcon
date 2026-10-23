"""Bounded field types for the leads module's request bodies (public and staff).

SECURITY (SECURITY.md §5): every string has a length limit and refuses control characters
(PostgreSQL rejects NUL bytes, and single-line fields must stay on one line). Addresses shown as
links in the CMS must be http(s) or a site path, never `javascript:` or `data:`.
Messages are written for the visitor or staff member who sees them in `errors[]`.
"""

from __future__ import annotations

import unicodedata
from typing import Annotated, Final
from urllib.parse import urlsplit

from pydantic import AfterValidator, EmailStr, Field, StringConstraints
from pydantic_core import PydanticCustomError

from empire_api.projects.fields import SchemaExtra


def one_line(value: str) -> str:
    if any(unicodedata.category(ch) == "Cc" for ch in value):
        raise PydanticCustomError("single_line", "Use one line of plain text.")
    return value


def plain_text(value: str) -> str:
    value = value.replace("\r\n", "\n")
    if any(unicodedata.category(ch) == "Cc" and ch not in "\n\t" for ch in value):
        raise PydanticCustomError("plain_text", "Remove the special characters from this text.")
    return value


def _person_name(value: str) -> str:
    one_line(value)
    if not any(ch.isalpha() for ch in value):
        raise PydanticCustomError("name", "Enter the person's name.")
    return value


def _is_web_address(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.hostname) and " " not in value


def _page_address(value: str) -> str:
    """A full http(s) address, or a path on our site."""
    is_path = value.startswith("/") and not value.startswith("//") and "\\" not in value
    if not is_path and not _is_web_address(value):
        raise PydanticCustomError("url", "Send the page's web address, starting with https://.")
    return one_line(value)


def _web_address(value: str) -> str:
    if not _is_web_address(value):
        raise PydanticCustomError("url", "Send a web address starting with https://.")
    return one_line(value)


PersonName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=2, max_length=80),
    AfterValidator(_person_name),
]
PhoneInput = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20),
    Field(description="Any Indian format; stored as +91XXXXXXXXXX (leads/phone.py)"),
]
Email = Annotated[EmailStr, Field(max_length=200)]
PageUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=1000), AfterValidator(_page_address)
]
WebAddress = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=1000), AfterValidator(_web_address)
]
Tag200 = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=200), AfterValidator(one_line)
]
ClickId = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(one_line)
]
Line60 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    AfterValidator(one_line),
]
Line200 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=200),
    AfterValidator(one_line),
]
ConsentNote = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=3, max_length=500),
    AfterValidator(plain_text),
    Field(description="How consent was obtained, e.g. 'Verbal on phone call'"),
]
Message = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=2000),
    AfterValidator(plain_text),
]
Text1000 = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=1000),
    AfterValidator(plain_text),
]
NoteBody = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
    AfterValidator(plain_text),
]
BHK_MIN: Final = 0.5
BHK_MAX: Final = 20.0
BHK_STEP: Final = 0.5


def _half_steps(value: float) -> float:
    """WHY: the column keeps one decimal, so 0.04 would round to 0.0 and break the CHECK (a 500,
    which also made the honeypot answer differently). Whole or half BHK only, 0.5 to 20."""
    if not BHK_MIN <= value <= BHK_MAX or not (value / BHK_STEP).is_integer():
        raise PydanticCustomError("bhk", "Use whole or half BHK from 0.5 to 20, like 2 or 2.5.")
    return value


Bhk = Annotated[
    float,
    AfterValidator(_half_steps),
    SchemaExtra({"minimum": BHK_MIN, "maximum": BHK_MAX, "multipleOf": BHK_STEP}),
    Field(description="Bedrooms in whole or half steps, 0.5 to 20; 1.5 for 1.5 BHK"),
]
