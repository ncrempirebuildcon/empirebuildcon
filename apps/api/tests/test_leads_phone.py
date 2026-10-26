"""Indian phone numbers → E.164 (leads/phone.py): a table of good and bad inputs, with the
message each bad one gets (the numbering-plan sources are in the module header)."""

from __future__ import annotations

import pytest

from empire_api.leads import phone
from empire_api.leads.phone import PhoneError, is_sample_number, normalise_phone
from empire_api.logs import mask_phone

GOOD = [
    # The four formats the spec names.
    ("98765 43210", "+919876543210", "mobile"),
    ("+91-98765-43210", "+919876543210", "mobile"),
    ("09876543210", "+919876543210", "mobile"),
    ("919876543210", "+919876543210", "mobile"),
    # Other ways people write the same number.
    ("9876543210", "+919876543210", "mobile"),
    ("+91 98765 43210", "+919876543210", "mobile"),
    ("+919876543210", "+919876543210", "mobile"),
    ("0091 98765 43210", "+919876543210", "mobile"),
    ("+91 (0) 98765 43210", "+919876543210", "mobile"),
    ("98765.43210", "+919876543210", "mobile"),
    ("(98765) 43210", "+919876543210", "mobile"),
    ("  98765 43210  ", "+919876543210", "mobile"),
    ("९८७६५ ४३२१०", "+919876543210", "mobile"),  # Devanagari digits
    # Every mobile level (TRAI 2020: 6, 7, 8 and 9).
    ("6012345678", "+916012345678", "mobile"),
    ("7012345678", "+917012345678", "mobile"),
    ("8012345678", "+918012345678", "mobile"),
    # A 10-digit number starting 91 is a mobile, not a country code.
    ("9198765432", "+919198765432", "mobile"),
    # Landlines with their STD code (NNP 2003: 2–4 digit code + 6–8 digit number = 10).
    ("011 2345 6789", "+911123456789", "landline"),  # Delhi, 2-digit code
    ("0120 456 7890", "+911204567890", "landline"),  # Noida/Ghaziabad, 3-digit code
    ("0522-2345678", "+915222345678", "landline"),  # Lucknow, 3-digit code
    ("05946 234567", "+915946234567", "landline"),  # Haldwani, 4-digit code
    ("+91 120 456 7890", "+911204567890", "landline"),
    ("+91 (0)120 4567890", "+911204567890", "landline"),
    # Bengaluru's code starts with 8: same shape as a mobile, stored the same way.
    ("080 2345 6789", "+918023456789", "mobile"),
]

BAD = [
    ("", phone.ENTER_NUMBER),
    ("+", phone.ENTER_NUMBER),
    ("98765", phone.ENTER_NUMBER),
    ("98765 432101", phone.ENTER_NUMBER),  # 11 digits, no trunk 0
    ("9876543210123", phone.ENTER_NUMBER),
    ("98765 43210 ext 2", phone.DIGITS_ONLY),
    ("phone me", phone.DIGITS_ONLY),
    ("98765/43210", phone.DIGITS_ONLY),
    ("+1 415 555 0100", phone.INDIA_ONLY),
    ("+971 50 123 4567", phone.INDIA_ONLY),
    ("0044 20 7946 0000", phone.INDIA_ONLY),
    ("2345678", phone.ADD_STD_CODE),  # a local landline number
    ("456 7890", phone.ADD_STD_CODE),
    ("23456789", phone.ADD_STD_CODE),
    ("0000000000", phone.NOT_A_NUMBER),  # no national number starts with the trunk 0
    ("0123456789", phone.NOT_A_NUMBER),
    ("+91 00000 00001", phone.NOT_A_NUMBER),  # the seed's sample range
    ("1111111111", phone.NOT_A_NUMBER),  # no valid subscriber number after any STD code
    ("1170000000", phone.NOT_A_NUMBER),  # no valid subscriber number after any STD code
    ("5011111111", phone.NOT_A_NUMBER),
    ("1800 123 4567", phone.ENTER_NUMBER),  # toll-free: 11 digits
]


@pytest.mark.parametrize(("raw", "e164", "kind"), GOOD)
def test_good_numbers_become_e164(raw: str, e164: str, kind: str) -> None:
    result = normalise_phone(raw)
    assert (result.e164, result.kind) == (e164, kind)


@pytest.mark.parametrize(("raw", "message"), BAD)
def test_bad_numbers_say_how_to_fix_them(raw: str, message: str) -> None:
    with pytest.raises(PhoneError) as caught:
        normalise_phone(raw)
    assert str(caught.value) == message


def test_sample_range_can_never_be_a_real_number() -> None:
    """The seed uses +91 00000 000NN (leads/seed.py): flagged, and refused by the normaliser."""
    assert is_sample_number("+910000000012")
    assert not is_sample_number("+919876543210")
    with pytest.raises(PhoneError):
        normalise_phone("+910000000012")


def test_masked_form_for_logs() -> None:
    assert mask_phone("+919876543210") == "+91 98xxxxxx10"
