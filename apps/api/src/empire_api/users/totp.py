"""Time-based one-time passwords (TOTP, RFC 6238) for two-factor sign-in, written here on purpose.

Collaborators: users/two_factor.py (set-up, sign-in checks, replay protection).
Implements: RFC 4226 (HOTP: HMAC-SHA1 of an 8-byte counter, dynamic truncation, modulo 10^d)
and RFC 6238 (the counter is the number of 30-second steps since the Unix epoch). Parameters are
the ones every authenticator app uses by default: SHA-1, 30 seconds, 6 digits.

WHY no library: the algorithm is about 20 lines, the RFC's own test vectors (Appendix B) prove
it (tests/test_two_factor.py), and one less dependency is one less supply-chain risk on the
sign-in path.

SECURITY:
  - A code is accepted for the current step and one step either side (±30 s), to allow for a
    phone clock that is a little off (RFC 6238 §5.2 recommends at most one step back).
  - Codes are compared in constant time.
  - Replays are refused by the caller: `matching_step` returns WHICH step matched, and
    two_factor.py accepts it only if it is later than the last step accepted for that account.
DO NOT CHANGE the digits, period or algorithm: every enrolled phone would stop matching.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
from datetime import datetime
from typing import Final
from urllib.parse import quote, urlencode

PERIOD_SECONDS: Final = 30
DIGITS: Final = 6
# One step either side of now (RFC 6238 §5.2).
WINDOW_STEPS: Final = 1
# 160 bits, the HMAC-SHA1 block's natural key length (RFC 4226 §4 R6 asks for at least 128).
SECRET_BYTES: Final = 20
ISSUER: Final = "Empire CMS"


def new_secret() -> str:
    """A fresh random secret as base32 without padding (what authenticator apps expect)."""
    return base64.b32encode(secrets.token_bytes(SECRET_BYTES)).decode().rstrip("=")


def _key(secret_base32: str) -> bytes:
    cleaned = secret_base32.replace(" ", "").upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 §5.3: HMAC-SHA1(key, counter as 8 bytes big-endian), dynamic truncation."""
    # WHY SHA-1: RFC 4226/6238 and every authenticator app use it; HMAC-SHA1 is not broken by
    # SHA-1's collision attacks.
    mac = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = mac[-1] & 0x0F
    value = struct.unpack(">I", mac[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**digits).zfill(digits)


def step_at(when: datetime) -> int:
    """The RFC 6238 time step (T) for a moment: whole periods since the Unix epoch (T0 = 0)."""
    return int(when.timestamp()) // PERIOD_SECONDS


def code_at(secret_base32: str, when: datetime, digits: int = DIGITS) -> str:
    """The code an authenticator app shows at `when` (tests and the CMS's e2e helper use it)."""
    return hotp(_key(secret_base32), step_at(when), digits)


def matching_step(secret_base32: str, code: str, when: datetime) -> int | None:
    """The time step within ±WINDOW_STEPS of `when` whose code equals `code`, or None.

    Every step in the window is checked, whether or not an earlier one matched, so the time
    taken doesn't say which step matched.
    """
    cleaned = code.replace(" ", "").replace("-", "")
    if len(cleaned) != DIGITS or not cleaned.isascii() or not cleaned.isdigit():
        return None
    key = _key(secret_base32)
    now_step = step_at(when)
    found: int | None = None
    for step in range(now_step - WINDOW_STEPS, now_step + WINDOW_STEPS + 1):
        if hmac.compare_digest(hotp(key, step), cleaned) and found is None:
            found = step
    return found


def provisioning_uri(secret_base32: str, account_email: str) -> str:
    """The `otpauth://` link an authenticator app reads from the QR code (Key Uri Format).

    The label is "Empire CMS:<email>" so the app lists the account clearly; issuer, algorithm,
    digits and period are spelled out so no app guesses differently.
    """
    label = quote(f"{ISSUER}:{account_email}", safe="")
    query = urlencode(
        {
            "secret": secret_base32,
            "issuer": ISSUER,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": PERIOD_SECONDS,
        },
        quote_via=quote,
    )
    return f"otpauth://totp/{label}?{query}"


def grouped(secret_base32: str) -> str:
    """The secret in groups of four, easier to type into an app by hand ("ABCD EFGH …")."""
    return " ".join(secret_base32[i : i + 4] for i in range(0, len(secret_base32), 4))
