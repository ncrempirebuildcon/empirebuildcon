"""Normalise and hash contact details the way each ad platform matches them (task 6.2).

Sources (read 7 Nov 2026):
  - Google Data Manager API, "Format user data"
    (developers.google.com/data-manager/api/devguides/concepts/formatting): email lowercased
    and trimmed, with dots and anything after "+" removed before the "@" for gmail.com and
    googlemail.com only; phone in E.164 with the "+"; SHA-256, hex encoded.
  - Meta Conversions API, customer information parameters
    (developers.facebook.com/docs/marketing-api/conversions-api/parameters/
    customer-information-parameters):
    email lowercased and trimmed; phone with symbols, letters and leading zeros removed and the
    country code included; SHA-256.

COMPLIANCE: these helpers are the only way contact details leave for an ad platform, and they
return hashes only.
"""

from __future__ import annotations

import hashlib

_GMAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def google_email(email: str | None) -> str | None:
    if not email:
        return None
    cleaned = "".join(email.split()).lower()
    local, sep, domain = cleaned.rpartition("@")
    if not sep or not local or not domain:
        return None
    if domain in _GMAIL_DOMAINS:
        local = local.split("+", 1)[0].replace(".", "")
    return sha256_hex(f"{local}@{domain}")


def google_phone(phone_e164: str | None) -> str | None:
    """`phone_e164` is already E.164 (leads/phone.py), e.g. "+919876543210"."""
    if not phone_e164 or not phone_e164.startswith("+") or not phone_e164[1:].isdigit():
        return None
    return sha256_hex(phone_e164)


def meta_email(email: str | None) -> str | None:
    if not email:
        return None
    cleaned = email.strip().lower()
    return sha256_hex(cleaned) if "@" in cleaned else None


def meta_phone(phone_e164: str | None) -> str | None:
    if not phone_e164:
        return None
    digits = "".join(ch for ch in phone_e164 if ch.isdigit())
    return sha256_hex(digits) if digits else None
