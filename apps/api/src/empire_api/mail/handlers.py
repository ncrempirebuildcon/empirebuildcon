"""Outbox handlers that send email (ARCHITECTURE §9 consumers): password links, security notices,
lead and site-visit alerts.

Collaborators: integrations/handlers.py (`on`), mail/delivery.py (once per recipient),
mail/templates.py, mail/brand.py; users/directory.py and users/service.py (accounts, link
checks), leads/queries.py (what a lead email may say), projects/queries.py (project names),
site_settings/service.py (the sales inbox).
Implements: ARCHITECTURE §8 (alerts), §9; SECURITY.md §1 (security notices), §8 (no full phone).

Who gets what:
  - `user.setup_link_issued` / `user.password_reset_requested`: the link, decrypted only here,
    to that account. Skipped when the account is inactive or the link was used or burned
    meanwhile (a retry never emails a dead link). An undecryptable link (the data key changed)
    is a permanent failure.
  - `user.created`: no email to the new person. WHY: the setup-link email goes out at the same
    moment and says an account was made for them; two emails at once would look like phishing.
  - `user.created` with the super-admin role, and `user.updated` that makes someone a
    super-admin or changes a super-admin's email: a notice to every active super-admin, and to
    the old address when the email changed. SECURITY (L2 security review): with a stolen
    super-admin session, a new super-admin account or an email change would otherwise keep the
    attacker in quietly; the real owner now hears about it.
  - `user.locked`, `user.password_changed`, `user.two_factor_enabled` / `_disabled` / `_reset`,
    `user.recovery_code_used`: a short notice to that account ("if this wasn't you, contact the
    super-admin"). Lock notices go at most once an hour per person (delivery.py
    `recent_template_sent`): otherwise anyone could flood an inbox, or spend the plan's 100 a
    day, by locking an account from many networks.
  - `lead.created`, ONLY when `data.alert` is true (duplicates, manual and sample leads are
    false): to `lead_routing.inbox_email`, or, when that isn't set, to every active super-admin,
    so a lead is never silently unannounced. If routing gave the lead to someone, they get the
    "now yours" email too. A site-visit request is announced by `site_visit.requested` instead
    (one email per request, not two).
  - `lead.assigned`: the new owner (not when they took it themselves, and not when it went back
    to the inbox).
  - `site_visit.requested`: the same recipients as a lead alert, with the day and time of day,
    and the "now yours" email to the person routing gave the lead to.
  - Sample, spam and erased leads are never announced.

SECURITY: links, codes and personal data are never logged; log lines carry ids and the template.
INVARIANT: idempotent (delivery.py): a retried event reaches only the people it hasn't reached.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import date, datetime
from functools import partial
from typing import Any, Final

from cryptography.fernet import InvalidToken
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.integrations.handlers import on
from empire_api.leads import queries as lead_queries
from empire_api.mail import brand as brand_lines
from empire_api.mail import templates
from empire_api.mail.delivery import recent_template_sent, send_to_each
from empire_api.mail.events import (
    ADMIN_CHANGE_EVENTS,
    LEAD_EVENTS,
    PASSWORD_LINK_EVENTS,
    SECURITY_NOTICE_EVENTS,
)
from empire_api.mail.transport import PermanentEmailError
from empire_api.platform.models import OutboxEvent
from empire_api.projects import queries as project_queries
from empire_api.site_settings.groups import LeadRoutingSettings
from empire_api.site_settings.service import read_typed
from empire_api.users import directory
from empire_api.users import service as user_service
from empire_api.users.models import User

LOCK_NOTICE_EVERY_SECONDS: Final = 3600
Render = Callable[[], templates.Rendered]


def _uuid(value: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _send(
    db: Session, event: OutboxEvent, template: str, recipients: list[tuple[str, Render]]
) -> None:
    if not recipients:
        return
    sender = brand_lines.sender(db)
    send_to_each(event, template, recipients, sender_name=sender.name, reply_to=sender.reply_to)


# --- Password links ------------------------------------------------------------------------


def _link(event: OutboxEvent) -> str:
    try:
        encrypted = str(event.payload["link_encrypted"])
        return get_settings().fernet().decrypt(encrypted.encode()).decode()
    except KeyError, InvalidToken:
        raise PermanentEmailError("The link in this event can't be read") from None


def password_link(db: Session, event: OutboxEvent) -> None:
    account = directory.active_account(db, _uuid(event.payload.get("user_id")))
    if account is None:
        return
    link = _link(event)
    token = user_service.token_of_link(link)
    if not token or not user_service.password_link_open(db, token):
        return
    minutes = int(event.payload.get("expires_in_minutes") or 30)
    brand = brand_lines.brand(db)
    setup = event.type == "user.setup_link_issued"
    template = "setup_link" if setup else "reset_link"
    make = templates.setup_link if setup else templates.reset_link
    _send(db, event, template, [(account.email, partial(make, account.name, link, minutes, brand))])


# --- Security notices ----------------------------------------------------------------------

_TWO_FACTOR: Final = {
    "user.two_factor_enabled": "enabled",
    "user.two_factor_disabled": "disabled",
    "user.two_factor_reset": "reset",
    "user.recovery_code_used": "recovery_code_used",
}


def security_notice(db: Session, event: OutboxEvent) -> None:
    account = directory.active_account(db, _uuid(event.payload.get("user_id")))
    if account is None:
        return
    brand = brand_lines.brand(db)
    when = event.occurred_at
    render: Render
    if event.type == "user.locked":
        if recent_template_sent(account.email, "account_locked", LOCK_NOTICE_EVERY_SECONDS):
            return
        until = datetime.fromisoformat(str(event.payload.get("locked_until") or when.isoformat()))
        template = "account_locked"
        render = partial(templates.account_locked, account.name, until, brand)
    elif event.type == "user.password_changed":
        how = str(event.payload.get("how") or "changed")
        template = "password_changed"
        render = partial(templates.password_changed, account.name, how, when, brand)
    else:
        what = _TWO_FACTOR[event.type]
        remaining = int(event.payload.get("remaining") or 0)
        template = f"two_factor_{what}"
        render = partial(
            templates.two_factor_notice, account.name, what, when, brand, remaining=remaining
        )
    _send(db, event, template, [(account.email, render)])


# --- Super-admin changes --------------------------------------------------------------------


def admin_change_notice(db: Session, event: OutboxEvent) -> None:
    payload = event.payload
    if payload.get("role") != "super_admin":
        return
    changed = set(payload.get("changed") or [])
    if event.type == "user.created":
        what = "created"
    elif "role" in changed:
        what = "promoted"
    elif "email" in changed:
        what = "email_changed"
    else:
        return
    user = db.get(User, _uuid(payload.get("user_id")))
    if user is None:
        return
    brand = brand_lines.brand(db)
    # The account itself isn't told (WHY at the top: its own setup email or sign-out says what
    # happened, and a notice saying "deactivate that account" would only warn an intruder).
    recipients = [
        admin.email for admin in directory.active_super_admins(db) if admin.user_id != user.id
    ]
    previous = payload.get("previous_email")
    email_changed = "email" in changed and isinstance(previous, str) and bool(previous)
    if email_changed:
        # The old address hears even when the role changed in the same edit.
        recipients.append(str(previous))
    render = partial(
        templates.admin_change_notice,
        user.name,
        user.email,
        what,
        event.occurred_at,
        brand,
        email_changed=email_changed and what != "email_changed",
    )
    _send(db, event, "admin_change", [(to, render) for to in dict.fromkeys(recipients)])


# --- Lead alerts ---------------------------------------------------------------------------


def _lead_lines(db: Session, lead_id: uuid.UUID | None) -> templates.LeadLines | None:
    facts = lead_queries.alert_facts(db, lead_id) if lead_id else None
    if facts is None or facts.is_sample or facts.is_spam:
        return None
    projects = project_queries.project_refs(db, [facts.project_id])
    project = projects.get(facts.project_id) if facts.project_id else None
    return templates.LeadLines(
        reference=facts.reference,
        project_name=project.name if project else None,
        source=facts.source,
        received_at=facts.created_at,
        name=facts.name,
        phone_masked=facts.phone_masked,
        link=f"{get_settings().site_url.rstrip('/')}/admin/leads/{facts.lead_id}",
    )


def sales_inbox(db: Session) -> list[str]:
    """`lead_routing.inbox_email`, or every active super-admin when it isn't set."""
    routing = read_typed(db, "lead_routing", LeadRoutingSettings)
    if routing.inbox_email:
        return [routing.inbox_email]
    return [admin.email for admin in directory.active_super_admins(db)]


def lead_created(db: Session, event: OutboxEvent) -> None:
    if event.payload.get("alert") is not True or event.payload.get("intent") == "site_visit":
        return
    lines = _lead_lines(db, _uuid(event.payload.get("lead_id")))
    if lines is None:
        return
    brand = brand_lines.brand(db)
    alert = partial(templates.lead_alert, lines, brand)
    _send(db, event, "lead_alert", [(to, alert) for to in sales_inbox(db)])
    owner = directory.active_account(db, _uuid(event.payload.get("owner_user_id")))
    if owner is not None:
        yours = partial(templates.lead_assigned, owner.name, lines, brand)
        _send(db, event, "lead_assigned", [(owner.email, yours)])


def lead_assigned(db: Session, event: OutboxEvent) -> None:
    owner_id = _uuid(event.payload.get("to_user_id"))
    if owner_id is None or owner_id == event.actor_id:
        return
    owner = directory.active_account(db, owner_id)
    lines = _lead_lines(db, _uuid(event.payload.get("lead_id")))
    if owner is None or lines is None:
        return
    brand = brand_lines.brand(db)
    yours = partial(templates.lead_assigned, owner.name, lines, brand)
    _send(db, event, "lead_assigned", [(owner.email, yours)])


def _day(value: Any) -> str:
    try:
        day = date.fromisoformat(str(value))
    except ValueError:
        return str(value or "")
    return f"{day:%a} {day.day} {day:%b %Y}"


def visit_requested(db: Session, event: OutboxEvent) -> None:
    lines = _lead_lines(db, _uuid(event.payload.get("lead_id")))
    if lines is None:
        return
    brand = brand_lines.brand(db)
    day = _day(event.payload.get("preferred_date"))
    slot = str(event.payload.get("preferred_slot") or "")
    request = partial(templates.visit_requested, lines, day, slot, brand)
    _send(db, event, "visit_requested", [(to, request) for to in sales_inbox(db)])
    # Part 5 review L2: the lead.created email skips site-visit requests (this one announces
    # them), so the person routing gave the lead to is told here.
    lead_id = _uuid(event.payload.get("lead_id"))
    facts = lead_queries.alert_facts(db, lead_id) if lead_id else None
    owner_id = facts.owner_user_id if facts else None
    owner = directory.active_account(db, owner_id) if owner_id != event.actor_id else None
    if owner is not None:
        yours = partial(templates.lead_assigned, owner.name, lines, brand)
        _send(db, event, "lead_assigned", [(owner.email, yours)])


_LEAD_HANDLERS: Final = {
    "lead.created": lead_created,
    "lead.assigned": lead_assigned,
    "site_visit.requested": visit_requested,
}
for _type in PASSWORD_LINK_EVENTS:
    on(_type)(password_link)
for _type in SECURITY_NOTICE_EVENTS:
    on(_type)(security_notice)
for _type in LEAD_EVENTS:
    on(_type)(_LEAD_HANDLERS[_type])
for _type in ADMIN_CHANGE_EVENTS:
    on(_type)(admin_change_notice)
