"""Company lines for emails, from Settings (`company`, `contacts`, `email` groups).

Collaborators: mail/handlers.py, site_settings/service.py (typed values), leads/phone display.
Honest placeholders: until the owner fills the company details in, emails say "[Company name]"
rather than inventing one (AGENTS.md "Don't invent facts").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from sqlalchemy.orm import Session

from empire_api.mail.templates import APP_NAME, Brand
from empire_api.site_settings.groups import CompanySettings, ContactSettings, EmailSettings
from empire_api.site_settings.service import read_typed

PLACEHOLDER: Final = "[Company name]"


@dataclass(frozen=True)
class Sender:
    name: str
    reply_to: str | None


def _shown(value: str | None) -> str | None:
    """A value that is set and isn't a seeded [placeholder]."""
    return value if value and not value.startswith("[") else None


def display_phone(e164: str) -> str:
    """'+919876543210' → '+91 98765 43210' (as the website shows numbers)."""
    if e164.startswith("+91") and len(e164) == 13:
        return f"+91 {e164[3:8]} {e164[8:]}"
    return e164


def brand(db: Session) -> Brand:
    company = read_typed(db, "company", CompanySettings)
    contacts = read_typed(db, "contacts", ContactSettings)
    name = _shown(company.brand_name) or _shown(company.legal_name) or PLACEHOLDER
    parts = []
    if contacts.sales_phone:
        parts.append(f"Sales {display_phone(contacts.sales_phone)}")
    if contacts.sales_email:
        parts.append(contacts.sales_email)
    return Brand(company_name=name, contact_line=" · ".join(parts) or None)


def sender(db: Session) -> Sender:
    settings = read_typed(db, "email", EmailSettings)
    return Sender(name=settings.sender_name or APP_NAME, reply_to=settings.reply_to)
