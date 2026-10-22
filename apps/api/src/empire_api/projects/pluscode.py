"""Open Location Code ("plus code") validation and decoding, e.g. 7JWV8XX8+XX → a lat/lng box.

WHY our own code and not a package (checked on PyPI, 22 Oct 2026):
  - `openlocationcode` 1.0.1 (Google's reference) was last released on 20 Jul 2019, ships only
    an sdist, has no type hints, and its GitHub source has moved on since that release.
  - `pluscodes` 2022.1.3 (27 Aug 2022) is a third-party port with no release since.
Neither counts as maintained, so this is a small port of the reference algorithm
(github.com/google/open-location-code, Apache-2.0), limited to what the maps resolver needs:
`is_valid`, `is_short`, `is_full` and `decode`. tests/test_maps.py runs vectors copied from the
reference's test_data/decoding.csv and validityTests.csv.

Encoding and short-code recovery are not needed: staff paste full codes, and a short code
("8XX8+XX Noida") needs a geocoder to recover, which we don't call (maps.py answers 422).
"""

from __future__ import annotations

from dataclasses import dataclass

SEPARATOR = "+"
SEPARATOR_POSITION = 8
PADDING = "0"
ALPHABET = "23456789CFGHJMPQRVWX"
BASE = len(ALPHABET)  # 20
LATITUDE_MAX = 90
LONGITUDE_MAX = 180
MAX_DIGITS = 15
PAIR_CODE_LENGTH = 10
PAIR_FIRST_PLACE_VALUE = BASE ** (PAIR_CODE_LENGTH // 2 - 1)  # 8000
PAIR_PRECISION = BASE**3  # 8000
GRID_CODE_LENGTH = MAX_DIGITS - PAIR_CODE_LENGTH  # 5
GRID_COLUMNS = 4
GRID_ROWS = 5
GRID_LAT_FIRST_PLACE_VALUE = GRID_ROWS ** (GRID_CODE_LENGTH - 1)
GRID_LNG_FIRST_PLACE_VALUE = GRID_COLUMNS ** (GRID_CODE_LENGTH - 1)
FINAL_LAT_PRECISION = PAIR_PRECISION * GRID_ROWS**GRID_CODE_LENGTH
FINAL_LNG_PRECISION = PAIR_PRECISION * GRID_COLUMNS**GRID_CODE_LENGTH


@dataclass(frozen=True)
class CodeArea:
    """The box a code stands for. `code_length` counts digits, not the separator."""

    lat_lo: float
    lng_lo: float
    lat_hi: float
    lng_hi: float
    code_length: int

    @property
    def lat(self) -> float:
        return min(self.lat_lo + (self.lat_hi - self.lat_lo) / 2, LATITUDE_MAX)

    @property
    def lng(self) -> float:
        return min(self.lng_lo + (self.lng_hi - self.lng_lo) / 2, LONGITUDE_MAX)


def leading_code(text: str) -> str:
    """The first word of pasted text, without a trailing comma, as Google shows plus codes:
    "7JWV8XX8+XX Sector 150, Noida" → "7JWV8XX8+XX". Not validated."""
    words = text.split(maxsplit=1)
    return words[0].rstrip(",") if words else ""


def is_valid(code: str) -> bool:
    """Right characters, one separator in an even position up to 8, padding rules respected."""
    sep = code.find(SEPARATOR)
    if code.count(SEPARATOR) != 1 or len(code) == 1:
        return False
    if sep > SEPARATOR_POSITION or sep % 2 == 1:
        return False
    if not _padding_ok(code, sep):
        return False
    if len(code) - sep - 1 == 1:  # a single digit after the separator is not allowed
        return False
    return all(ch.upper() in ALPHABET or ch in (SEPARATOR, PADDING) for ch in code)


def _padding_ok(code: str, sep: int) -> bool:
    pad = code.find(PADDING)
    if pad == -1:
        return True
    if sep < SEPARATOR_POSITION or pad == 0:  # short codes can't be padded; no leading pad
        return False
    pads = code[pad : code.rfind(PADDING) + 1]
    if len(pads) % 2 == 1 or pads.count(PADDING) != len(pads):
        return False
    return code.endswith(SEPARATOR)  # a padded code ends at the separator


def is_short(code: str) -> bool:
    """A valid code with fewer than 8 digits before the separator (needs a reference place)."""
    return is_valid(code) and 0 <= code.find(SEPARATOR) < SEPARATOR_POSITION


def is_full(code: str) -> bool:
    """A valid, not-short code whose first two digits stay inside ±90° / ±180°."""
    if not is_valid(code) or is_short(code):
        return False
    if ALPHABET.find(code[0].upper()) * BASE >= LATITUDE_MAX * 2:
        return False
    return ALPHABET.find(code[1].upper()) * BASE < LONGITUDE_MAX * 2


def decode(code: str) -> CodeArea:
    """Decode a full code into its box (port of the reference `decode`).

    Raises:
        ValueError: the code is not a valid full code.
    """
    if not is_full(code):
        raise ValueError("Not a valid full plus code.")
    digits = code.replace(SEPARATOR, "").replace(PADDING, "").upper()[:MAX_DIGITS]
    normal_lat = -LATITUDE_MAX * PAIR_PRECISION
    normal_lng = -LONGITUDE_MAX * PAIR_PRECISION
    pair_digits = min(len(digits), PAIR_CODE_LENGTH)
    place = PAIR_FIRST_PLACE_VALUE
    for i in range(0, pair_digits, 2):
        normal_lat += ALPHABET.find(digits[i]) * place
        normal_lng += ALPHABET.find(digits[i + 1]) * place
        if i < pair_digits - 2:
            place //= BASE
    lat_precision = place / PAIR_PRECISION
    lng_precision = place / PAIR_PRECISION
    grid_lat = grid_lng = 0
    if len(digits) > PAIR_CODE_LENGTH:
        row_place, col_place = GRID_LAT_FIRST_PLACE_VALUE, GRID_LNG_FIRST_PLACE_VALUE
        for i in range(PAIR_CODE_LENGTH, len(digits)):
            value = ALPHABET.find(digits[i])
            grid_lat += (value // GRID_COLUMNS) * row_place
            grid_lng += (value % GRID_COLUMNS) * col_place
            if i < len(digits) - 1:
                row_place //= GRID_ROWS
                col_place //= GRID_COLUMNS
        lat_precision = row_place / FINAL_LAT_PRECISION
        lng_precision = col_place / FINAL_LNG_PRECISION
    lat = normal_lat / PAIR_PRECISION + grid_lat / FINAL_LAT_PRECISION
    lng = normal_lng / PAIR_PRECISION + grid_lng / FINAL_LNG_PRECISION
    # WHY round to 14 places: the reference does it to hide floating-point noise.
    return CodeArea(
        round(lat, 14),
        round(lng, 14),
        round(lat + lat_precision, 14),
        round(lng + lng_precision, 14),
        len(digits),
    )
