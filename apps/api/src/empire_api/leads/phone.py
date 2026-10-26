"""Indian phone numbers → E.164 (`+91` + the 10-digit national number), with a helpful message
for anything we can't accept.

Collaborators: intake.py (public forms), service.py (manual leads), logs.mask_phone (logs).
Implements: ARCHITECTURE §8 (phone), the Phase 4 part 3 rule for landlines.

The numbering plan, from the regulator's own documents (read 23 Oct 2026):
  - DoT, National Numbering Plan 2003 (dotws.cdot.in/sites/default/files/nnp2003_0_0.pdf):
    §1.9 "N(S)N is 10-digit for both the basic as well as cellular mobile services"; §2.1.5 the
    prefix '0' is the national trunk prefix; §2.1.6 and Annex I §1.7.1 a fixed-line number is a
    2–4 digit trunk (STD) code plus a 6–8 digit subscriber number, 10 digits together; Annex I
    §1.3 the code's first digit is 1–8; Annex I §1.7.1.4 a subscriber number never starts with
    0, 1, 7, 8 or 9.
  - TRAI, Recommendations on Ensuring Adequate Numbering Resources for Fixed Line and Mobile
    Services, 29 May 2020 (trai.gov.in), paras 2.9, 2.24–2.25 and 3.2: fixed and mobile numbers
    are both 10 digits; mobiles use level 9 and sub-levels of 8, 7 and 6.
  - TRAI press release 09/2025 (6 Feb 2025), Revision of the National Numbering Plan: still a
    recommendation; existing subscriber numbers stay unchanged and 10 digits long.

The rule (strict on purpose: a lead with a wrong number is a lost lead):
  1. Spaces, hyphens, dots and brackets are ignored, and other scripts' digits (Devanagari ९)
     count as digits. Anything else except one leading "+" is refused.
  2. A country code is removed: "+91…", "0091…", or "91…" when 12 digits are left. Any other
     "+" or "00" country code is refused (Indian numbers only for now; NRI leads with foreign
     numbers are a TODO below).
  3. One trunk prefix "0" is removed from an 11-digit number ("09876543210", "+91 0120 …").
  4. Exactly 10 digits must remain: the national significant number (NSN).
  5. First digit 6–9 → a mobile number. (A landline whose STD code starts 6–8, like Bengaluru's
     080, has the same shape and is stored the same way, so it needs no special case.)
  6. First digit 1–5 → a landline written with its STD code. Accepted only when some split into
     a 2–4 digit code leaves a subscriber number starting 2–6 (NNP Annex I §1.7.1.4).
  7. First digit 0 → refused: no national number starts with the trunk prefix. The sample seed
     uses exactly this range (`+9100000000NN`), so sample numbers can never be anyone's and the
     public forms refuse them.
  Local landline numbers without the STD code (6–8 digits) get "add the STD code".

COMPLIANCE / WHY "fancy" numbers are accepted: Indian operators sell VIP numbers on purpose
(repeated digits like 99999 99999, runs like 98765 43210), so such a number can belong to a real
buyer. Refusing them would turn that buyer away, which costs more than the little junk they let
through; junk is handled by the rate limits, the honeypot, duplicate linking and "mark spam".
DO NOT add a repeated-digit or run rule back (decided in the Phase 4 part 3 review).

Known limit: a landline whose STD code starts with 6, 7 or 8 (Bengaluru 080, Patna 0612, Nagpur
0712) has the same 10-digit shape as a mobile, and nothing in the national format tells them
apart, so `kind` says "mobile" and the CMS may offer a WhatsApp link that won't work for it.

TODO(phase-6): NRI enquiries with foreign mobile numbers (the NRI page on the design board),
once the owner decides how sales should handle them.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Final, Literal

COUNTRY_CODE: Final = "91"
NSN_LENGTH: Final = 10
# DO NOT CHANGE: the seed's sample numbers live in this range because no real number can
# (rule 7). Public intake refuses it; erasure and tests rely on it being fake.
SAMPLE_PREFIX: Final = "+9100000"

_SEPARATORS: Final = re.compile(r"[\s\-.()]")
# "00" + country code + at least 8 digits: shorter strings of zeros are not a dialled prefix.
_INTERNATIONAL_MIN: Final = 12
# Subscriber numbers never start with 0, 1, 7, 8 or 9 (NNP 2003 Annex I §1.7.1.4).
_SUBSCRIBER_FIRST: Final = frozenset("23456")

ENTER_NUMBER: Final = (
    "Enter a 10-digit mobile number, like 98765 43210, or a landline with its STD code, "
    "like 0120 456 7890."
)
DIGITS_ONLY: Final = "Use digits only (spaces and hyphens are fine), like 98765 43210."
INDIA_ONLY: Final = "Enter an Indian number (+91). Numbers from other countries can't be used yet."
ADD_STD_CODE: Final = "Add the STD code to this landline number, like 0120 456 7890."
NOT_A_NUMBER: Final = "This doesn't look like an Indian phone number. " + ENTER_NUMBER


class PhoneError(ValueError):
    """The number can't be used; `str(error)` is the message for the visitor or staff."""


@dataclass(frozen=True)
class Phone:
    e164: str
    kind: Literal["mobile", "landline"]


def _ascii_digits(text: str) -> str:
    """WHY: Hindi forms may send Devanagari digits (९८७६…); they mean the same number."""
    return "".join(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch for ch in text)


def _national_digits(raw: str) -> str:
    """Steps 1–3: the digits left after separators, the country code and the trunk prefix."""
    text = _ascii_digits(_SEPARATORS.sub("", raw.strip()))
    plus = text.startswith("+")
    digits = text[1:] if plus else text
    if not digits.isascii() or not digits.isdigit():
        raise PhoneError(DIGITS_ONLY if digits else ENTER_NUMBER)
    if plus:
        if not digits.startswith(COUNTRY_CODE):
            raise PhoneError(INDIA_ONLY)
        digits = digits[len(COUNTRY_CODE) :]
    elif digits.startswith("00") and len(digits) >= _INTERNATIONAL_MIN:
        # "00" is India's international prefix: 00 + country code + number.
        if not digits.startswith("00" + COUNTRY_CODE):
            raise PhoneError(INDIA_ONLY)
        digits = digits[2 + len(COUNTRY_CODE) :]
    elif len(digits) == len(COUNTRY_CODE) + NSN_LENGTH and digits.startswith(COUNTRY_CODE):
        digits = digits[len(COUNTRY_CODE) :]
    if len(digits) == NSN_LENGTH + 1 and digits.startswith("0"):
        digits = digits[1:]
    return digits


def _landline_ok(nsn: str) -> bool:
    """Step 6: some 2–4 digit STD code leaves a subscriber number that may exist."""
    return any(nsn[code_length] in _SUBSCRIBER_FIRST for code_length in (2, 3, 4))


def normalise_phone(raw: str) -> Phone:
    """'98765 43210', '+91-98765-43210', '09876543210', '919876543210' → '+919876543210'.

    Raises:
        PhoneError: with a message that says how to fix the number.
    """
    nsn = _national_digits(raw)
    if 6 <= len(nsn) <= 8 and nsn[0] in _SUBSCRIBER_FIRST:
        raise PhoneError(ADD_STD_CODE)
    if len(nsn) != NSN_LENGTH:
        raise PhoneError(ENTER_NUMBER)
    first = nsn[0]
    if first in "6789":
        return Phone(e164=f"+{COUNTRY_CODE}{nsn}", kind="mobile")
    if first in "12345" and _landline_ok(nsn):
        return Phone(e164=f"+{COUNTRY_CODE}{nsn}", kind="landline")
    raise PhoneError(NOT_A_NUMBER)


def is_sample_number(e164: str) -> bool:
    """Whether a stored number is in the seed's fake range (rule 7)."""
    return e164.startswith(SAMPLE_PREFIX)
