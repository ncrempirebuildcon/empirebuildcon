"""How email leaves the system: one `Transport` interface, two transports (like media/store.py).

- `ResendTransport` (resend.py): Resend's HTTP API with plain httpx (no SDK), D-007.
- `DevTransport` (dev.py): development, tests and the browser suite. Never sends; each message
  is a JSON file in MAIL_DEV_DIR, which the dev mailbox route (routes_dev.py) reads.

Collaborators: mail/delivery.py calls `get_transport()`; config.py decides which is active
(`Settings.email_transport_kind`) and refuses the dev transport in staging and production.

Errors: a transport raises `RetryableEmailError` (the outbox retries the event: rate limits,
the daily quota, the provider being down, a network error, a key problem the owner can fix) or
`PermanentEmailError` (the event goes dead at once with an alert: the provider refused the
message itself, so sending it again can't work).
SECURITY: error messages name an HTTP status and the provider's error type only. They end up
in `outbox_event.last_error` and the logs, so they never hold an address, a link or the key.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.utils import formataddr
from functools import lru_cache
from typing import Literal, Protocol

from empire_api.config import get_settings
from empire_api.integrations.handlers import PermanentDeliveryError

TransportName = Literal["resend", "dev"]


class RetryableEmailError(RuntimeError):
    """Sending failed for now; the outbox tries the event again later."""


class PermanentEmailError(PermanentDeliveryError):
    """The provider refused this message; retrying can't help (the event goes dead)."""


@dataclass(frozen=True)
class OutgoingEmail:
    """One message to one person, already rendered (mail/templates.py)."""

    to: str
    subject: str
    text: str
    html: str
    template: str
    sender_name: str
    reply_to: str | None
    # Stable across retries of the same event (mail/delivery.py), at most 256 characters.
    idempotency_key: str
    # The links in the message, for the dev mailbox only (the browser suite opens them).
    links: tuple[str, ...] = ()


class Transport(Protocol):
    name: TransportName

    def send(self, message: OutgoingEmail) -> str:
        """Hand the message over; returns the provider's message id. Raises the errors above."""
        ...


@lru_cache(maxsize=1)
def get_transport() -> Transport:
    """The active transport for this process. Tests call `get_transport.cache_clear()`."""
    settings = get_settings()
    if settings.email_transport_kind == "resend":
        from empire_api.mail.resend import ResendTransport  # noqa: PLC0415 — only when used

        return ResendTransport.from_settings(settings)
    from empire_api.mail.dev import DevTransport  # noqa: PLC0415

    return DevTransport.from_settings(settings)


def sender_address() -> str:
    """EMAIL_FROM, or a clearly fake address for the dev mailbox."""
    return get_settings().email_from.strip() or "no-reply@example.com"


def from_header(sender_name: str) -> str:
    """'Empire Sales <alerts@…>', quoted or encoded as RFC 5322 needs (part 5 review L4)."""
    return formataddr((sender_name, sender_address()))
