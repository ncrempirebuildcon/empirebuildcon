"""Display strings for money and area: the Python twin of packages/ui/src/format.

The API fills the read-only `display` fields of `Price` and `Area` with these, so the CMS, the
public site and structured data show the same text. tests/test_display.py runs the same test
vectors as packages/ui/test/format.test.ts; when you change one side, change both.

How the twin stays exact:
  - JavaScript's `Math.round` rounds halves up (towards +∞); Python's `round` rounds halves to
    even. `_js_round` copies JavaScript.
  - `Intl.NumberFormat("en-IN")` groups as 12,34,567; `_group_in` copies that.
  - The arithmetic is done in the same order on IEEE doubles, so results match bit for bit.

Formats (handbook/ARCHITECTURE.md §6):
  - Money: below ₹ 1 lakh the full figure (₹ 99,999); then lakhs (₹ 85 L, ₹ 12.35 L); from
    ₹ 1 crore, crores (₹ 1.25 Cr). Ranges use a spaced en dash; equal ends show once.
  - Area: carpet area in sq ft AND sq m (AGENTS.md "carpet area comes first, in sq ft and sq m"),
    with the basis in brackets: "720 – 1,120 sq ft · 66.9 – 104.1 sq m (carpet)". The display
    unit decides which figure leads: sq m first for `sqm`, sq yd and sq m for `sqyd` (plots).

COMPLIANCE: `price_display` returns "Price on request" whenever `on_request` is set, so numbers
can't leak into the display string (ARCHITECTURE §6, "price_on_request hides numbers").
"""

from __future__ import annotations

import math
import re
from decimal import Decimal

LAKH = 1_00_000
CRORE = 1_00_00_000

# 1 sq ft = 0.092903 sq m, the factor packages/ui/src/format/area.ts uses.
SQM_PER_SQFT = 0.092903
# 1 sq yd = 9 sq ft, so the same rounded factor × 9 (keeps sq yd consistent with sq ft).
SQM_PER_SQYD = 0.836127

PRICE_ON_REQUEST = "Price on request"
BASIS_LABELS = {
    "carpet": "carpet",
    "builtup": "built-up",
    "super_builtup": "super built-up",
    "plot": "plot",
}
UNIT_LABELS = {"sqft": "sq ft", "sqyd": "sq yd", "sqm": "sq m"}

_TRAILING_ZEROS = re.compile(r"\.?0+$")


def _js_round(value: float) -> int:
    """JavaScript `Math.round`: halves round up (2.5 → 3, -2.5 → -2)."""
    return math.floor(value + 0.5)


def _group_in(value: int) -> str:
    """Indian digit grouping like `Intl.NumberFormat("en-IN")`: 1234567 → "12,34,567"."""
    digits = str(abs(value))
    if len(digits) > 3:
        head, tail = digits[:-3], digits[-3:]
        pairs: list[str] = []
        while len(head) > 2:
            pairs.insert(0, head[-2:])
            head = head[:-2]
        digits = ",".join([head, *pairs, tail])
    return f"-{digits}" if value < 0 else digits


def _short(value: float) -> str:
    """At most two decimals, trailing zeros dropped: 1.2 → "1.2", 1.25 → "1.25", 78 → "78"."""
    return _TRAILING_ZEROS.sub("", f"{_js_round(value * 100) / 100:.2f}", count=1)


def _check_amount(amount_inr: float, name: str) -> None:
    if not math.isfinite(amount_inr) or amount_inr < 0:
        raise ValueError(f"{name}: expected a non-negative amount, got {amount_inr}")


def format_inr(amount_inr: float) -> str:
    """₹ 99,999 · ₹ 85 L · ₹ 12.35 L · ₹ 1.25 Cr (twin of `formatInr`)."""
    _check_amount(amount_inr, "format_inr")
    if amount_inr < LAKH:
        return f"₹ {_group_in(_js_round(amount_inr))}"
    lakhs = _js_round((amount_inr / LAKH) * 100) / 100
    # WHY: ₹ 99,99,999 rounds to "100 L"; Indian usage switches to crores at that point.
    if amount_inr >= CRORE or lakhs >= 100:
        return f"₹ {_short(amount_inr / CRORE)} Cr"
    return f"₹ {_short(lakhs)} L"


def format_inr_full(amount_inr: float) -> str:
    """Full figure with Indian grouping: ₹ 12,34,567 (twin of `formatInrFull`)."""
    _check_amount(amount_inr, "format_inr_full")
    return f"₹ {_group_in(_js_round(amount_inr))}"


def format_inr_range(min_inr: float, max_inr: float) -> str:
    """₹ 78 L – ₹ 1.25 Cr; equal ends show once (twin of `formatInrRange`)."""
    if max_inr < min_inr:
        raise ValueError("format_inr_range: max is below min")
    low, high = format_inr(min_inr), format_inr(max_inr)
    return low if low == high else f"{low} – {high}"


def sqft_to_sqm(sqft: float) -> float:
    """Square feet → square metres, one decimal: 980 → 91.0 (twin of `sqftToSqm`)."""
    return _js_round(sqft * SQM_PER_SQFT * 10) / 10


def sqm_to_sqft(sqm: float) -> int:
    """Square metres → whole square feet: 91.04 → 980 (twin of `sqmToSqft`)."""
    return _js_round(sqm / SQM_PER_SQFT)


def sqm_to_sqyd(sqm: float) -> int:
    """Square metres → whole square yards: 100.34 → 120."""
    return _js_round(sqm / SQM_PER_SQYD)


def _sqft_of(value: float, unit: str) -> int:
    return _js_round(value) if unit == "sqft" else sqm_to_sqft(value)


def _sqm_of(value: float, unit: str) -> float:
    return _js_round(value * 10) / 10 if unit == "sqm" else sqft_to_sqm(value)


def format_area(value: float, unit: str = "sqft") -> str:
    """980 sq ft · 91.0 sq m (twin of `formatArea`; `unit` is "sqft" or "sqm")."""
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"format_area: expected a non-negative area, got {value}")
    return f"{_group_in(_sqft_of(value, unit))} sq ft · {_sqm_of(value, unit):.1f} sq m"


def format_area_range(min_value: float, max_value: float, unit: str = "sqft") -> str:
    """720 – 1,120 sq ft · 66.9 – 104.1 sq m (twin of `formatAreaRange`)."""
    if max_value < min_value:
        raise ValueError("format_area_range: max is below min")
    if min_value == max_value:
        return format_area(min_value, unit)
    return (
        f"{_group_in(_sqft_of(min_value, unit))} – {_group_in(_sqft_of(max_value, unit))} sq ft"
        f" · {_sqm_of(min_value, unit):.1f} – {_sqm_of(max_value, unit):.1f} sq m"
    )


# --- Display strings for the API's Price and Area shapes ------------------------------------


def _as_float(value: Decimal | float | None) -> float | None:
    return None if value is None else float(value)


def price_display(
    *,
    on_request: bool,
    min_inr: int | None,
    max_inr: int | None,
    rate_inr: int | None = None,
    rate_unit: str | None = None,
) -> str:
    """ "₹ 78 L – ₹ 1.25 Cr", "From ₹ 85 L", "₹ 5,400 per sq ft", or "" when nothing is set.

    Range and rate join with " · ". `on_request` always wins (COMPLIANCE, module header).
    """
    if on_request:
        return PRICE_ON_REQUEST
    parts: list[str] = []
    if min_inr is not None and max_inr is not None:
        parts.append(format_inr_range(min_inr, max_inr))
    elif min_inr is not None:
        parts.append(f"From {format_inr(min_inr)}")
    elif max_inr is not None:
        parts.append(f"Up to {format_inr(max_inr)}")
    if rate_inr is not None and rate_unit in UNIT_LABELS:
        parts.append(f"{format_inr_full(rate_inr)} per {UNIT_LABELS[rate_unit]}")
    return " · ".join(parts)


def area_display(
    *,
    min_sqm: Decimal | float | None,
    max_sqm: Decimal | float | None,
    basis: str,
    display_unit: str,
) -> str:
    """Area from square metres, in both units, with the basis: "980 sq ft · 91.0 sq m (carpet)".

    One end missing shows the other alone; nothing set gives "".
    """
    low, high = _as_float(min_sqm), _as_float(max_sqm)
    if low is None and high is None:
        return ""
    low = high if low is None else low
    high = low if high is None else high
    assert low is not None and high is not None  # noqa: S101 — narrowed above
    if display_unit == "sqm":
        text = f"{_sqm_text(low, high)} · {_sqft_text(low, high)}"
    elif display_unit == "sqyd":
        text = f"{_sqyd_text(low, high)} · {_sqm_text(low, high)}"
    else:
        # Exactly the twin's formatAreaRange(min, max, "sqm").
        text = format_area_range(low, high, "sqm")
    return f"{text} ({BASIS_LABELS.get(basis, basis)})"


def _span(low: str, high: str, same: bool) -> str:
    return low if same else f"{low} – {high}"


def _sqft_text(low_sqm: float, high_sqm: float) -> str:
    same = low_sqm == high_sqm
    return f"{_span(_group_in(sqm_to_sqft(low_sqm)), _group_in(sqm_to_sqft(high_sqm)), same)} sq ft"


def _sqm_text(low_sqm: float, high_sqm: float) -> str:
    low, high = _sqm_of(low_sqm, "sqm"), _sqm_of(high_sqm, "sqm")
    return f"{_span(f'{low:.1f}', f'{high:.1f}', low_sqm == high_sqm)} sq m"


def _sqyd_text(low_sqm: float, high_sqm: float) -> str:
    same = low_sqm == high_sqm
    return f"{_span(_group_in(sqm_to_sqyd(low_sqm)), _group_in(sqm_to_sqyd(high_sqm)), same)} sq yd"
