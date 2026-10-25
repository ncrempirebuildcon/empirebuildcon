"""Field types for the content and SEO modules: text that refuses raw HTML, FormattedText, and
links that may only be a path on our site or an https address.

Collaborators: blocks.py, schemas_pages.py, schemas_marketing.py, seo/schemas.py; the base types
come from projects/fields.py (length limits, single-line, control characters, and `no_html` and
`is_site_path` themselves, so the shared Seo and Translations shapes use the same checks).
Implements: SECURITY.md §5 ("raw HTML is never rendered"; "no open redirects"), ARCHITECTURE §6
(FormattedText: *bold*, _italic_, `-` bullets, stored as plain text).

SECURITY: our renderer shows text as text, so HTML would never run; we still refuse it on input,
so nobody pastes markup expecting it to work and no stored text can become dangerous if a
future renderer is careless. A `<` followed by a space or digit ("price < 50 L", "3<4") is
ordinary text and stays allowed.
SECURITY: a link is a site path ("/projects/x") or an https address. `javascript:`, `data:`,
`vbscript:`, `http:` and protocol-relative `//host` links are refused, because a link in a CTA
is clicked by visitors and staff alike.
"""

from __future__ import annotations

from typing import Annotated, Final
from urllib.parse import urlsplit

from pydantic import AfterValidator, StringConstraints
from pydantic_core import PydanticCustomError

from empire_api.projects.fields import (
    Line20,
    Line40,
    Line60,
    Line80,
    Line120,
    Line160,
    Line200,
    Line250,
    Line300,
    NoHtml,
    SchemaExtra,
    Text500,
    Text1500,
    Text2000,
    Text4000,
    Text5000,
    Text50000,
    is_site_path,
)

LINK_MESSAGE: Final = (
    "Use a path on our site, starting with / (like /projects/aurum-heights), or a full address "
    "starting with https://."
)
LINK_PATTERN: Final = r"^(/(?!/)\S*|https://\S+)$"


def link(value: str) -> str:
    """SECURITY: a site path or an https address with a real host (module header)."""
    if is_site_path(value):
        return value
    parts = urlsplit(value)
    has_space = any(ch.isspace() or ord(ch) < 32 for ch in value)
    if parts.scheme != "https" or not parts.hostname or has_space or "\\" in value:
        raise PydanticCustomError("link", LINK_MESSAGE)
    if parts.username or parts.password:
        # https://empirebuildcon.com@evil.example would really go to evil.example.
        raise PydanticCustomError("link", LINK_MESSAGE)
    return value


# Plain single-line text without HTML, by maximum length.
Plain20 = Annotated[Line20, NoHtml]
Plain40 = Annotated[Line40, NoHtml]
Plain60 = Annotated[Line60, NoHtml]
Plain80 = Annotated[Line80, NoHtml]
Plain120 = Annotated[Line120, NoHtml]
Plain160 = Annotated[Line160, NoHtml]
Plain200 = Annotated[Line200, NoHtml]
Plain250 = Annotated[Line250, NoHtml]
Plain300 = Annotated[Line300, NoHtml]
# Multi-line plain text and FormattedText (WhatsApp-style marks, rendered by our own parser).
Para500 = Annotated[Text500, NoHtml]
Para1500 = Annotated[Text1500, NoHtml]
Formatted2000 = Annotated[Text2000, NoHtml, SchemaExtra({"format": "formatted-text"})]
Formatted4000 = Annotated[Text4000, NoHtml, SchemaExtra({"format": "formatted-text"})]
Formatted5000 = Annotated[Text5000, NoHtml, SchemaExtra({"format": "formatted-text"})]
Formatted50000 = Annotated[Text50000, NoHtml, SchemaExtra({"format": "formatted-text"})]

Link = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
    AfterValidator(link),
    SchemaExtra({"pattern": LINK_PATTERN}),
]
