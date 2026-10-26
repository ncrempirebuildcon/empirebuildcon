"""Field rules for settings values: GSTIN, phones, social links, tracking ids, the WhatsApp
message and the email sender name.

Collaborators: site_settings/groups.py; leads/phone.py (the phone rule, D-034).
SECURITY (SECURITY.md §5): every value has a length limit and refuses control characters and
HTML; links are https on a short host list per network, so a settings value can never become a
`javascript:` link or point at a look-alike host.
Messages are written for the staff member who sees them next to the field.
"""

from __future__ import annotations

import re
import unicodedata
from typing import Annotated, Final
from urllib.parse import urlsplit

from pydantic import AfterValidator, BeforeValidator, StringConstraints
from pydantic_core import PydanticCustomError

from empire_api.leads.phone import PhoneError, normalise_phone
from empire_api.projects.fields import SchemaExtra, no_html

# --- GSTIN -----------------------------------------------------------------------------------

# 2-digit state code, the 10-character PAN (5 letters, 4 digits, 1 letter), the entity number
# (1–9 or A–Z), the letter Z, and a check character. Format from the GST rules (Rule 10, Form
# GST REG-06); the check character is the published mod-36 algorithm below.
GSTIN_PATTERN: Final = r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$"
_GSTIN_CHARS: Final = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
# The example in the error message; it passes its own check character (tests prove it).
GSTIN_EXAMPLE: Final = "09AAAAA0000A1Z0"
# State and UT codes 01–38, 97 (Other Territory) and 99 (Centre Jurisdiction).
_GSTIN_STATES: Final = frozenset({f"{n:02d}" for n in range(1, 39)} | {"97", "99"})


def gstin_check_character(first14: str) -> str:
    """The 15th character of a GSTIN: factors 1, 2, 1, 2 … over the first 14 characters, each
    product folded as (p // 36 + p % 36), then (36 − sum mod 36) mod 36."""
    total = 0
    for index, char in enumerate(first14):
        product = _GSTIN_CHARS.index(char) * (1 if index % 2 == 0 else 2)
        total += product // 36 + product % 36
    return _GSTIN_CHARS[(36 - total % 36) % 36]


def _gstin(value: str) -> str:
    cleaned = value.replace(" ", "").upper()
    if not re.fullmatch(GSTIN_PATTERN, cleaned) or cleaned[:2] not in _GSTIN_STATES:
        raise PydanticCustomError(
            "gstin", f"Enter the 15-character GSTIN, like {GSTIN_EXAMPLE} (UP starts with 09)."
        )
    if gstin_check_character(cleaned[:14]) != cleaned[14]:
        raise PydanticCustomError(
            "gstin_check", "This GSTIN's last character doesn't match. Check it for a typo."
        )
    return cleaned


Gstin = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=20),
    AfterValidator(_gstin),
    SchemaExtra({"pattern": GSTIN_PATTERN}),
]


# --- Phones ----------------------------------------------------------------------------------


def _phone(value: str) -> str:
    """The leads phone rule (D-034): any Indian format in, `+91XXXXXXXXXX` stored."""
    try:
        return normalise_phone(value).e164
    except PhoneError as exc:
        raise PydanticCustomError("phone", str(exc)) from None


IndianPhone = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=20),
    AfterValidator(_phone),
]


# --- Social links ----------------------------------------------------------------------------

SOCIAL_HOSTS: Final[dict[str, frozenset[str]]] = {
    "facebook": frozenset({"facebook.com", "www.facebook.com", "m.facebook.com"}),
    "instagram": frozenset({"instagram.com", "www.instagram.com"}),
    "youtube": frozenset({"youtube.com", "www.youtube.com", "m.youtube.com"}),
    "linkedin": frozenset({"linkedin.com", "www.linkedin.com", "in.linkedin.com"}),
}
_SOCIAL_NAMES: Final = {
    "facebook": "Facebook",
    "instagram": "Instagram",
    "youtube": "YouTube",
    "linkedin": "LinkedIn",
}


def social_link(network: str) -> AfterValidator:
    """https on this network's own hosts, with a page path; no login, port or odd characters."""

    def check(value: str) -> str:
        parts = urlsplit(value)
        host = (parts.hostname or "").lower()
        ok = (
            parts.scheme == "https"
            and host in SOCIAL_HOSTS[network]
            and parts.username is None
            and parts.port is None
            and parts.path not in ("", "/")
            and not any(ch.isspace() or ord(ch) < 32 for ch in value)
            and "\\" not in value
        )
        if not ok:
            name = _SOCIAL_NAMES[network]
            example = sorted(SOCIAL_HOSTS[network])[-1]
            raise PydanticCustomError(
                "social_link",
                f"Paste the full link to the {name} page, starting with https://{example}/.",
            )
        return value

    return AfterValidator(check)


SocialUrl = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


# --- Tracking ids (stored only; nothing loads until the consent banner, Phase 6) ------------


def _tracking(pattern: str, example: str) -> AfterValidator:
    def check(value: str) -> str:
        cleaned = value.strip().upper()
        if not re.fullmatch(pattern, cleaned):
            raise PydanticCustomError("tracking_id", f"Use the id's own format, like {example}.")
        return cleaned

    return AfterValidator(check)


GTM_PATTERN: Final = r"^GTM-[A-Z0-9]{4,10}$"
GA4_PATTERN: Final = r"^G-[A-Z0-9]{6,12}$"
PIXEL_PATTERN: Final = r"^[0-9]{15,16}$"
ADS_PATTERN: Final = r"^AW-[0-9]{6,12}$"
_TrackingText = Annotated[str, StringConstraints(strip_whitespace=True, max_length=20)]
GtmId = Annotated[
    _TrackingText, _tracking(GTM_PATTERN, "GTM-XXXXXXX"), SchemaExtra({"pattern": GTM_PATTERN})
]
Ga4Id = Annotated[
    _TrackingText, _tracking(GA4_PATTERN, "G-XXXXXXXXXX"), SchemaExtra({"pattern": GA4_PATTERN})
]
PixelId = Annotated[
    _TrackingText,
    _tracking(PIXEL_PATTERN, "a 15–16 digit number"),
    SchemaExtra({"pattern": PIXEL_PATTERN}),
]
AdsId = Annotated[
    _TrackingText, _tracking(ADS_PATTERN, "AW-123456789"), SchemaExtra({"pattern": ADS_PATTERN})
]


# --- Texts with special rules -----------------------------------------------------------------

PAGE_PLACEHOLDER: Final = "{page}"


def _whatsapp_message(value: str) -> str:
    """The only placeholder is {page}; other braces would reach the visitor as they are."""
    no_html(value)
    leftover = value.replace(PAGE_PLACEHOLDER, "")
    if "{" in leftover or "}" in leftover:
        raise PydanticCustomError(
            "whatsapp_token", "The only placeholder you can use is {page} (the page's name)."
        )
    return value


def _single_line_text(value: str) -> str:
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in value):
        raise PydanticCustomError("single_line", "Use one line of plain text.")
    return value


WhatsappMessage = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=300),
    AfterValidator(_single_line_text),
    AfterValidator(_whatsapp_message),
]


def _sender_name(value: str) -> str:
    """SECURITY (part 5 review L4): the name goes into the From header, where characters such
    as `:` (a group), `( )` (a comment), quotes, `<>`, `,` `;` and `@` change what the header
    means, or could start another address. Only letters (any script), digits, spaces and
    `. - & '` are allowed; mail/transport.py also builds the header with formataddr."""
    # Letters and their combining marks (Devanagari vowel signs and virama are marks, "M*").
    if not all(
        unicodedata.category(ch)[0] in "LM" or ch.isdigit() or ch in " .-&'" for ch in value
    ):
        raise PydanticCustomError(
            "sender_name",
            "Use letters, numbers, spaces and . - & ' only, like Empire Sales & Co.",
        )
    return value


SenderName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=60),
    AfterValidator(_sender_name),
]


def _keep_spaces_blank_is_none(value: object) -> object:
    return None if isinstance(value, str) and not value.strip() else value


def _title_suffix(value: str) -> str:
    _single_line_text(value)
    return no_html(value)


# WHY not stripped: a suffix like " · Empire" keeps its leading space on purpose.
TitleSuffix = Annotated[
    str,
    BeforeValidator(_keep_spaces_blank_is_none),
    StringConstraints(max_length=40),
    AfterValidator(_title_suffix),
]
PROMOTER_PATTERN: Final = r"^[A-Z0-9][A-Z0-9/-]{3,39}$"


def _promoter_number(value: str) -> str:
    cleaned = value.replace(" ", "").upper()
    if not re.fullmatch(PROMOTER_PATTERN, cleaned):
        raise PydanticCustomError(
            "promoter_number",
            "Use the number exactly as UP-RERA shows it (letters, digits, / and -).",
        )
    return cleaned


PromoterNumber = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=40), AfterValidator(_promoter_number)
]
