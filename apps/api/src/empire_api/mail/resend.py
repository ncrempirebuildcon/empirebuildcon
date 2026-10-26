"""The Resend transport: `POST https://api.resend.com/emails` with httpx (D-007, no SDK).

Collaborators: mail/transport.py (interface, errors), config.py (EMAIL_API_KEY, EMAIL_FROM).
Facts read on resend.com/docs on 25 Oct 2026 (send-email, errors, rate-limit, and account quotas
pages): Bearer API key; JSON body `from`, `to` (up to 50), `subject`, `html`, `text`,
`reply_to`; answer `{"id": …}`; an optional `Idempotency-Key` header of 1–256 characters, kept
for 24 hours; 429 for the rate limit (`rate_limit_exceeded`, 10 requests per second per team)
and for the plan's quotas (`daily_quota_exceeded`: the Free plan sends 100 a day and 3,000 a
month, and the day is a UTC calendar day, reset at midnight UTC; `monthly_quota_exceeded`);
409 `concurrent_idempotent_requests` while the same key is in flight, and
`invalid_idempotent_request` when a key is reused with a different body. The error body's
field names aren't documented; `_error_name` reads `name` when present and says "unknown"
otherwise.

How errors are sorted (mail/transport.py):
  - Retryable: network errors and timeouts, 429, 5xx, 409 concurrent request, and 401/403
    (a missing, wrong or restricted key, or an unverified sending domain). WHY 401/403 too: the
    owner can fix the key or the domain, and the outbox keeps the alerts and password links
    for about 32 hours of retries instead of losing them; the alert log says what to fix.
  - Already sent: 409 `invalid_idempotent_request` (an earlier attempt with this key was
    accepted; see `_fail`).
  - Permanent: every other 4xx (400, 404, 405, 422): the message itself is refused, so sending
    it again can't work.
SECURITY: the key is read once into the client's headers and never logged; error messages
carry the status and Resend's error name only, never the response text (it may echo an
address back) or the key.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Final

import httpx

from empire_api.config import Settings
from empire_api.logs import get_logger
from empire_api.mail.transport import (
    OutgoingEmail,
    PermanentEmailError,
    RetryableEmailError,
    TransportName,
    from_header,
)

ENDPOINT: Final = "https://api.resend.com/emails"
TIMEOUT_SECONDS: Final = 10.0
_CONFIG_STATUSES: Final = frozenset({401, 403})

log = get_logger(__name__)


def _error_name(response: httpx.Response) -> str:
    """Resend's error type (`name`), only if it is a short plain token."""
    try:
        body = response.json()
    except ValueError:
        return "unknown"
    name = body.get("name") if isinstance(body, dict) else None
    if isinstance(name, str) and name.replace("_", "").isalnum() and len(name) <= 60:
        return name
    return "unknown"


def _default_client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=False)


def _message_id(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    found = body.get("id") if isinstance(body, dict) else None
    return found[:100] if isinstance(found, str) else ""


class ResendTransport:
    name: TransportName = "resend"

    def __init__(
        self,
        api_key: str,
        *,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self._api_key = api_key
        self._client_factory = client_factory

    @classmethod
    def from_settings(cls, settings: Settings) -> ResendTransport:
        return cls(settings.email_api_key.get_secret_value().strip())

    def __repr__(self) -> str:  # SECURITY: never show the key, even in a debugger or a crash
        return "ResendTransport(api_key=***)"

    def _body(self, message: OutgoingEmail) -> dict[str, object]:
        body: dict[str, object] = {
            "from": from_header(message.sender_name),
            "to": [message.to],
            "subject": message.subject,
            "text": message.text,
            "html": message.html,
        }
        if message.reply_to:
            body["reply_to"] = message.reply_to
        return body

    def send(self, message: OutgoingEmail) -> str:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Idempotency-Key": message.idempotency_key,
            "Content-Type": "application/json",
        }
        try:
            with (self._client_factory or _default_client)() as client:
                response = client.post(ENDPOINT, json=self._body(message), headers=headers)
        except httpx.HTTPError as exc:
            raise RetryableEmailError(f"Resend unreachable ({type(exc).__name__})") from None
        if response.status_code in (200, 201, 202):
            return _message_id(response)
        return self._fail(response)

    def _fail(self, response: httpx.Response) -> str:
        status = response.status_code
        name = _error_name(response)
        reason = f"Resend answered {status} ({name})"
        if status in _CONFIG_STATUSES:
            # The owner must fix EMAIL_API_KEY or verify the sending domain at Resend.
            log.error("email_provider_config_error", status=status, error=name)
            raise RetryableEmailError(reason)
        if status == 429 or status >= 500 or name == "concurrent_idempotent_requests":
            raise RetryableEmailError(reason)
        if name == "invalid_idempotent_request":
            # WHY success: Resend already accepted a message with this key (an earlier attempt
            # whose answer we never recorded); this retry's body differs only because something
            # it shows was edited meanwhile. The person has the email, so don't send another.
            log.warning("email_already_accepted", status=status)
            return ""
        log.error("email_refused", status=status, error=name)
        raise PermanentEmailError(reason)
