"""The emails the system sends: plain text plus simple, accessible HTML, in English.

Collaborators: mail/handlers.py (decides who gets what), mail/brand.py (company name and contact
lines from Settings). Pure functions: no database, no network, easy to test.

Rules (Phase 4 part 5 spec, SECURITY.md §8):
  - No tracking pixels, no remote images, no external fonts or styles: the HTML is text,
    headings, a table of facts and plain links, with inline styles and system fonts.
  - Company facts come from Settings and show as [placeholders] until the owner fills them in.
  - COMPLIANCE: lead emails carry the reference, project, source, time, name and a MASKED phone,
    and a link to the lead in the CMS. Never the full phone, the email address or the message:
    emails get forwarded and kept.
  - Subjects never carry a buyer's name (they show in phone notifications).
  - Every value is HTML-escaped; links are ours (SITE_URL) and shown as text too.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final

from empire_api.timeutil import IST

APP_NAME: Final = "Empire CMS"
SOURCE_LABELS: Final[dict[str, str]] = {
    "project_form": "Project page form",
    "contact_form": "Contact form",
    "brochure": "Brochure request",
    "site_visit": "Site-visit request",
    "campaign": "Campaign page",
    "chat": "Chat",
    "whatsapp": "WhatsApp",
    "phone": "Phone call",
    "manual": "Added by staff",
}
SLOT_LABELS: Final[dict[str, str]] = {
    "morning": "Morning",
    "afternoon": "Afternoon",
    "evening": "Evening",
}
NOT_YOU: Final = "If this wasn't you, contact the super-admin straight away."


@dataclass(frozen=True)
class Brand:
    """Company lines for the footer (mail/brand.py fills it from Settings)."""

    company_name: str = "[Company name]"
    contact_line: str | None = None


@dataclass(frozen=True)
class Rendered:
    subject: str
    text: str
    html: str
    links: tuple[str, ...] = ()


@dataclass
class _Body:
    """Paragraphs, fact rows and links, rendered once as text and once as HTML."""

    heading: str
    parts: list[tuple[str, object]] = field(default_factory=list)

    def para(self, text: str) -> _Body:
        self.parts.append(("p", text))
        return self

    def facts(self, rows: list[tuple[str, str]]) -> _Body:
        self.parts.append(("facts", rows))
        return self

    def link(self, label: str, url: str) -> _Body:
        self.parts.append(("link", (label, url)))
        return self


def ist(moment: datetime) -> str:
    """'25 Oct 2026, 14:05 IST' (stored in UTC, shown in India time)."""
    local = moment.astimezone(IST)
    return f"{local.day} {local:%b %Y, %H:%M} IST"


def _footer_text(brand: Brand) -> str:
    lines = ["--", brand.company_name]
    if brand.contact_line:
        lines.append(brand.contact_line)
    lines.append(f"This is an automatic message from {APP_NAME}.")
    return "\n".join(lines)


def _text(body: _Body, brand: Brand) -> str:
    out = [body.heading, ""]
    for kind, value in body.parts:
        if kind == "p":
            out += [str(value), ""]
        elif kind == "facts":
            rows = value if isinstance(value, list) else []
            out += [f"{label}: {text}" for label, text in rows] + [""]
        elif kind == "link" and isinstance(value, tuple):
            label, url = value
            out += [f"{label}: {url}", ""]
    return "\n".join(out) + _footer_text(brand) + "\n"


_STYLE_BODY: Final = (
    "margin:0;padding:24px;background:#ffffff;color:#1a1a1a;"
    "font-family:-apple-system,'Segoe UI',Roboto,Arial,sans-serif;font-size:16px;line-height:1.5"
)
_STYLE_LINK: Final = "color:#7a4b00;text-decoration:underline"


def _html(subject: str, body: _Body, brand: Brand) -> str:
    e = html.escape
    chunks = [f'<h1 style="font-size:20px;margin:0 0 16px">{e(body.heading)}</h1>']
    for kind, value in body.parts:
        if kind == "p":
            chunks.append(f'<p style="margin:0 0 16px">{e(str(value))}</p>')
        elif kind == "facts":
            rows = value if isinstance(value, list) else []
            cells = "".join(
                f'<tr><th scope="row" style="text-align:left;padding:4px 16px 4px 0;'
                f'font-weight:600;vertical-align:top">{e(label)}</th>'
                f'<td style="padding:4px 0">{e(text)}</td></tr>'
                for label, text in rows
            )
            chunks.append(f'<table role="presentation" style="margin:0 0 16px">{cells}</table>')
        elif kind == "link" and isinstance(value, tuple):
            label, url = value
            chunks.append(
                f'<p style="margin:0 0 16px"><a href="{e(url, quote=True)}" '
                f'style="{_STYLE_LINK}">{e(label)}</a><br>'
                f'<span style="font-size:14px;color:#555555">{e(url)}</span></p>'
            )
    footer = [e(brand.company_name)]
    if brand.contact_line:
        footer.append(e(brand.contact_line))
    footer.append(f"This is an automatic message from {e(APP_NAME)}.")
    chunks.append(
        '<hr style="border:0;border-top:1px solid #dddddd;margin:24px 0 16px">'
        f'<p style="margin:0;font-size:14px;color:#555555">{"<br>".join(footer)}</p>'
    )
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<title>{e(subject)}</title></head>"
        f'<body style="{_STYLE_BODY}"><main>{"".join(chunks)}</main></body></html>'
    )


def _render(subject: str, body: _Body, brand: Brand) -> Rendered:
    links = tuple(
        value[1] for kind, value in body.parts if kind == "link" and isinstance(value, tuple)
    )
    return Rendered(
        subject=subject, text=_text(body, brand), html=_html(subject, body, brand), links=links
    )


# --- Password links ------------------------------------------------------------------------


def setup_link(name: str, link: str, expires_in_minutes: int, brand: Brand) -> Rendered:
    """A new account's first password (also the 'an account was created for you' notice)."""
    hours = max(1, expires_in_minutes // 60)
    body = (
        _Body(f"Hello {name},")
        .para(f"An {APP_NAME} account was made for you. Choose your password with this link.")
        .link("Set your password", link)
        .para(
            f"The link works once and expires in {hours} hours. Nobody at Empire will ever ask "
            "you for your password."
        )
        .para(
            "If you didn't expect this email, you can ignore it; no account is usable "
            "without the password you choose."
        )
    )
    return _render(f"Set up your {APP_NAME} account", body, brand)


def reset_link(name: str, link: str, expires_in_minutes: int, brand: Brand) -> Rendered:
    body = (
        _Body(f"Hello {name},")
        .para("Someone asked to reset the password of your account. Choose a new one here.")
        .link("Choose a new password", link)
        .para(f"The link works once and expires in {expires_in_minutes} minutes.")
        .para("If you didn't ask for this, ignore this email: your password stays the same.")
    )
    return _render(f"Reset your {APP_NAME} password", body, brand)


# --- Security notices ----------------------------------------------------------------------


def account_locked(name: str, until: datetime, brand: Brand) -> Rendered:
    body = (
        _Body(f"Hello {name},")
        .para(
            "Someone tried to sign in to your account 5 times with a wrong password or code. "
            f"Signing in from that network is paused until {ist(until)}. Other networks are "
            "not affected."
        )
        .para(f"{NOT_YOU} Changing your password is a good idea too.")
    )
    return _render("Sign-in to your account was paused", body, brand)


def password_changed(name: str, how: str, when: datetime, brand: Brand) -> Rendered:
    word = "reset" if how == "reset" else "changed"
    verb = "reset with an emailed link" if how == "reset" else "changed"
    body = (
        _Body(f"Hello {name},")
        .para(
            f"The password of your account was {verb} on {ist(when)}. You were signed out "
            "everywhere else."
        )
        .para(NOT_YOU)
    )
    return _render(f"Your {APP_NAME} password was {word}", body, brand)


def two_factor_notice(
    name: str, what: str, when: datetime, brand: Brand, *, remaining: int = 0
) -> Rendered:
    """`what`: enabled, disabled, reset or recovery_code_used."""
    texts = {
        "enabled": (
            "Two-factor sign-in is now on",
            "Two-factor sign-in was turned on for your account. From now on, signing in also "
            "needs a code from your authenticator app. Keep your recovery codes somewhere safe.",
        ),
        "disabled": (
            "Two-factor sign-in was turned off",
            "Two-factor sign-in was turned off for your account. Signing in now needs only "
            "your password.",
        ),
        "reset": (
            "Your two-factor sign-in was reset",
            "The super-admin reset two-factor sign-in for your account (for example after a "
            "lost phone), and you were signed out everywhere. You may be asked to set it up "
            "again when you next sign in.",
        ),
        "recovery_code_used": (
            "A recovery code was used to sign in",
            f"One of your recovery codes was used to sign in to your account. Each code works "
            f"once; {remaining} {'is' if remaining == 1 else 'are'} left. You can make new ones "
            "in My account.",
        ),
    }
    subject, sentence = texts[what]
    body = _Body(f"Hello {name},").para(sentence).facts([("When", ist(when))]).para(NOT_YOU)
    return _render(subject, body, brand)


# --- Lead alerts ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LeadLines:
    """COMPLIANCE (module header): the only lead facts an email may carry."""

    reference: str
    project_name: str | None
    source: str
    received_at: datetime
    name: str
    phone_masked: str
    link: str


def _lead_rows(lead: LeadLines) -> list[tuple[str, str]]:
    return [
        ("Reference", lead.reference),
        ("Project", lead.project_name or "General enquiry (no project)"),
        ("Source", SOURCE_LABELS.get(lead.source, lead.source)),
        ("Received", ist(lead.received_at)),
        ("Name", lead.name),
        ("Phone", lead.phone_masked),
    ]


_MASKED_NOTE: Final = (
    "The phone number is masked on purpose: emails get forwarded and kept. The full details are "
    "in the CMS."
)


def lead_alert(lead: LeadLines, brand: Brand) -> Rendered:
    body = (
        _Body("New lead")
        .facts(_lead_rows(lead))
        .link("Open the lead in the CMS (sign-in needed)", lead.link)
        .para(_MASKED_NOTE)
    )
    return _render(f"New lead {lead.reference}", body, brand)


def lead_assigned(owner_name: str, lead: LeadLines, brand: Brand) -> Rendered:
    body = (
        _Body(f"Hello {owner_name},")
        .para("This lead is now yours.")
        .facts(_lead_rows(lead))
        .link("Open the lead in the CMS (sign-in needed)", lead.link)
        .para(_MASKED_NOTE)
    )
    return _render(f"Lead {lead.reference} is now yours", body, brand)


def visit_requested(lead: LeadLines, preferred_date: str, slot: str, brand: Brand) -> Rendered:
    rows = [
        *_lead_rows(lead)[:2],
        ("Preferred day", preferred_date),
        ("Time of day", SLOT_LABELS.get(slot, slot)),
        *_lead_rows(lead)[3:],
    ]
    body = (
        _Body("New site-visit request")
        .facts(rows)
        .para("Call to confirm a time, then record it in the visit calendar.")
        .link("Open the lead in the CMS (sign-in needed)", lead.link)
        .para(_MASKED_NOTE)
    )
    return _render(f"Site-visit request {lead.reference}", body, brand)
