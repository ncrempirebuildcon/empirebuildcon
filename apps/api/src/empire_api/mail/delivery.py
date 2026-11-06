"""Send one event's email to each recipient exactly once, however often the event is retried.

Collaborators: mail/transport.py (send), mail/models.py (the sent-mail log), mail/handlers.py.
Implements: ARCHITECTURE §9 (handlers are idempotent, keyed on the event id).

How it works:
  1. Each (event, template, recipient) gets a `recipient_key` (keyed hash of the address) and an
     `Idempotency-Key` derived from the event id, the template and that key: the same on every
     retry, at most 256 characters (Resend's limit), with no address in it.
  2. Before sending, the sent-mail log is checked; a recipient already reached by this event is
     skipped. WHY our own log as well as Resend's key: Resend forgets keys after 24 hours, and
     the outbox retries for about 32 hours.
  3. After the transport accepts the message, the log row is written on its OWN connection and
     committed at once. INVARIANT: like the rate-limit counters, this must not be in the drain's
     transaction: if a later recipient fails, the drain rolls the handler back, and the record of
     the earlier ones would be lost, so they would get the email again on the retry.
  4. Several recipients: everyone is tried. Any retryable failure → the event is retried (only the
     people not yet reached get it). Otherwise any permanent failure → the event goes dead.

SECURITY: nothing here logs an address, a subject or a link; log lines carry ids and the
template name.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import timedelta
from typing import Final

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from empire_api.db import get_side_engine
from empire_api.logs import get_logger
from empire_api.mail.models import EmailMessage
from empire_api.mail.templates import Rendered
from empire_api.mail.transport import (
    OutgoingEmail,
    PermanentEmailError,
    RetryableEmailError,
    get_transport,
)
from empire_api.platform.crypto import data_digest
from empire_api.platform.models import OutboxEvent
from empire_api.timeutil import utcnow

RECIPIENT_PURPOSE: Final = "mail_recipient"
log = get_logger(__name__)


def recipient_key(address: str) -> str:
    return data_digest(RECIPIENT_PURPOSE, address.strip().lower())


def idempotency_key(event: OutboxEvent, template: str, key: str) -> str:
    """Step 1: 'empire-<event id>-<template>-<24 hex>' (about 90 characters)."""
    return f"empire-{event.event_id}-{template}-{key[:24]}"


def already_sent(event: OutboxEvent, template: str, key: str) -> bool:
    with get_side_engine().connect() as conn:
        found = conn.execute(
            select(EmailMessage.id).where(
                EmailMessage.event_id == event.event_id,
                EmailMessage.template == template,
                EmailMessage.recipient_key == key,
            )
        ).first()
    return found is not None


def _record(event: OutboxEvent, template: str, key: str, transport: str, provider_id: str) -> None:
    """Step 3: on its own connection, committed at once (module header INVARIANT)."""
    with get_side_engine().begin() as conn:
        conn.execute(
            insert(EmailMessage)
            .values(
                event_id=event.event_id,
                template=template,
                recipient_key=key,
                transport=transport,
                provider_message_id=provider_id[:100] or None,
            )
            .on_conflict_do_nothing()
        )


def send_once(
    event: OutboxEvent,
    template: str,
    to: str,
    render: Callable[[], Rendered],
    *,
    sender_name: str,
    reply_to: str | None,
) -> bool:
    """Steps 1–3 for one recipient. Returns False when this recipient was already reached."""
    key = recipient_key(to)
    if already_sent(event, template, key):
        return False
    message = render()
    transport = get_transport()
    provider_id = transport.send(
        OutgoingEmail(
            to=to,
            subject=message.subject,
            text=message.text,
            html=message.html,
            template=template,
            sender_name=sender_name,
            reply_to=reply_to,
            idempotency_key=idempotency_key(event, template, key),
            links=message.links,
        )
    )
    _record(event, template, key, transport.name, provider_id)
    log.info("email_sent", event_id=str(event.event_id), template=template)
    return True


def send_to_each(
    event: OutboxEvent,
    template: str,
    recipients: Iterable[tuple[str, Callable[[], Rendered]]],
    *,
    sender_name: str,
    reply_to: str | None,
) -> int:
    """Step 4. Returns how many were sent now; raises after trying everyone if any failed."""
    sent = 0
    retryable: RetryableEmailError | None = None
    permanent: PermanentEmailError | None = None
    seen: set[str] = set()
    for address, render in recipients:
        if address.strip().lower() in seen:
            continue
        seen.add(address.strip().lower())
        try:
            sent += send_once(
                event, template, address, render, sender_name=sender_name, reply_to=reply_to
            )
        except RetryableEmailError as exc:
            retryable = exc
        except PermanentEmailError as exc:
            permanent = exc
    if retryable is not None:
        raise retryable
    if permanent is not None:
        raise permanent
    return sent


def recent_template_sent(address: str, template: str, since_seconds: int) -> bool:
    """Whether this person got an email of this template in the last `since_seconds` (the lock
    notice is sent at most once an hour per person, so a stranger can't flood an inbox or use
    up the plan's daily quota by locking an account from many networks)."""
    with get_side_engine().connect() as conn:
        found = conn.execute(
            select(EmailMessage.id)
            .where(
                EmailMessage.recipient_key == recipient_key(address),
                EmailMessage.template == template,
                EmailMessage.created_at >= utcnow() - timedelta(seconds=since_seconds),
            )
            .limit(1)
        ).first()
    return found is not None
