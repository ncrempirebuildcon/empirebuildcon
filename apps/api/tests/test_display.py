"""Money and area display strings (projects/display.py), the Python twin of packages/ui/src/format.

The first half repeats packages/ui/test/format.test.ts vector for vector, so the CMS, the API
and the public site can't drift apart. Change both files together.
"""

from __future__ import annotations

import math
from decimal import Decimal

import pytest

from empire_api.projects.display import (
    area_display,
    format_area,
    format_area_range,
    format_inr,
    format_inr_full,
    format_inr_range,
    price_display,
    sqft_to_sqm,
    sqm_to_sqft,
    sqm_to_sqyd,
)

# --- Same vectors as packages/ui/test/format.test.ts -----------------------------------------


@pytest.mark.parametrize(
    ("amount", "expected"),
    [
        (0, "₹ 0"),
        (99_999, "₹ 99,999"),
        (1_00_000, "₹ 1 L"),
        (78_00_000, "₹ 78 L"),
        (86_00_000, "₹ 86 L"),
        (12_34_567, "₹ 12.35 L"),
        (1_08_00_000, "₹ 1.08 Cr"),
        (1_25_00_000, "₹ 1.25 Cr"),
        (2_40_00_000, "₹ 2.4 Cr"),
        (99_99_999, "₹ 1 Cr"),
    ],
)
def test_format_inr(amount: int, expected: str) -> None:
    assert format_inr(amount) == expected


def test_format_inr_rejects_negative_and_non_finite() -> None:
    with pytest.raises(ValueError, match="non-negative"):
        format_inr(-1)
    with pytest.raises(ValueError, match="non-negative"):
        format_inr(math.nan)


def test_format_inr_full_uses_indian_grouping() -> None:
    assert format_inr_full(12_34_567) == "₹ 12,34,567"


def test_format_inr_range_collapses_equal_ends() -> None:
    assert format_inr_range(78_00_000, 1_25_00_000) == "₹ 78 L – ₹ 1.25 Cr"
    assert format_inr_range(2_10_00_000, 2_10_00_000) == "₹ 2.1 Cr"
    with pytest.raises(ValueError, match="max is below min"):
        format_inr_range(2, 1)


@pytest.mark.parametrize(("sqft", "sqm"), [(720, 66.9), (780, 72.5), (980, 91.0), (1120, 104.1)])
def test_sqft_to_sqm(sqft: int, sqm: float) -> None:
    assert sqft_to_sqm(sqft) == sqm


def test_sqm_back_to_whole_sqft() -> None:
    assert sqm_to_sqft(91.04) == 980


def test_format_area_in_both_units() -> None:
    assert format_area(980) == "980 sq ft · 91.0 sq m"
    assert format_area(1120) == "1,120 sq ft · 104.1 sq m"
    assert format_area(91.04, "sqm") == "980 sq ft · 91.0 sq m"


def test_format_area_range() -> None:
    assert format_area_range(720, 1120) == "720 – 1,120 sq ft · 66.9 – 104.1 sq m"
    assert format_area_range(980, 980) == "980 sq ft · 91.0 sq m"


# --- Python-only details ---------------------------------------------------------------------


def test_rounding_copies_javascript_not_bankers_rounding() -> None:
    # Python's round(0.5) is 0 and round(2.5) is 2; Math.round gives 1 and 3.
    assert format_inr(0.5) == "₹ 1"
    assert format_inr(2.5) == "₹ 3"
    assert format_inr(12_50_000) == "₹ 12.5 L"


def test_large_amounts_group_the_indian_way() -> None:
    assert format_inr_full(1_23_45_67_890) == "₹ 1,23,45,67,890"
    assert format_inr(25_00_00_00_000) == "₹ 2500 Cr"


def test_square_yards() -> None:
    assert sqm_to_sqyd(100.34) == 120


# --- The `display` strings the API returns ---------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected"),
    [
        ({"min_inr": 78_00_000, "max_inr": 1_25_00_000}, "₹ 78 L – ₹ 1.25 Cr"),
        ({"min_inr": 85_00_000, "max_inr": None}, "From ₹ 85 L"),
        ({"min_inr": None, "max_inr": 1_25_00_000}, "Up to ₹ 1.25 Cr"),
        (
            {"min_inr": None, "max_inr": None, "rate_inr": 5400, "rate_unit": "sqft"},
            "₹ 5,400 per sq ft",
        ),
        (
            {"min_inr": 78_00_000, "max_inr": 78_00_000, "rate_inr": 5400, "rate_unit": "sqyd"},
            "₹ 78 L · ₹ 5,400 per sq yd",
        ),
        ({"min_inr": None, "max_inr": None}, ""),
    ],
)
def test_price_display(kwargs: dict[str, object], expected: str) -> None:
    assert price_display(on_request=False, **kwargs) == expected  # type: ignore[arg-type]


def test_price_on_request_hides_every_number() -> None:
    """COMPLIANCE: on_request hides numbers in `display` (ARCHITECTURE §6)."""
    text = price_display(
        on_request=True, min_inr=78_00_000, max_inr=1_25_00_000, rate_inr=5400, rate_unit="sqft"
    )
    assert text == "Price on request"
    assert not any(ch.isdigit() for ch in text)


def test_area_display_from_square_metres_with_basis() -> None:
    assert (
        area_display(
            min_sqm=Decimal("66.89"), max_sqm=Decimal("104.05"), basis="carpet", display_unit="sqft"
        )
        == "720 – 1,120 sq ft · 66.9 – 104.1 sq m (carpet)"
    )
    assert (
        area_display(min_sqm=91.04, max_sqm=None, basis="super_builtup", display_unit="sqft")
        == "980 sq ft · 91.0 sq m (super built-up)"
    )


def test_area_display_leads_with_the_display_unit() -> None:
    assert (
        area_display(min_sqm=91.04, max_sqm=91.04, basis="carpet", display_unit="sqm")
        == "91.0 sq m · 980 sq ft (carpet)"
    )
    assert (
        area_display(
            min_sqm=Decimal("125.42"), max_sqm=Decimal("167.23"), basis="plot", display_unit="sqyd"
        )
        == "150 – 200 sq yd · 125.4 – 167.2 sq m (plot)"
    )


def test_area_display_empty_without_numbers() -> None:
    assert area_display(min_sqm=None, max_sqm=None, basis="carpet", display_unit="sqft") == ""
