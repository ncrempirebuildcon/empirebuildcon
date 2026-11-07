"""Meta Conversions API: one "Lead" event per reported enquiry (task 6.2, D-057).

Request: POST https://graph.facebook.com/{META_GRAPH_VERSION}/{pixel_id}/events, with the access
token in the JSON body. Customer fields and `fbc` follow Meta's "Customer information parameters"
page (developers.facebook.com/docs/marketing-api/conversions-api/parameters/
customer-information-parameters, read 7 Nov 2026). TODO(phase-9): before switching it on, send a
test with META_TEST_EVENT_CODE and check it in Events Manager → Test Events.
`event_id` is the lead's reference (EMP-…), so the browser Pixel's Lead event (task 6.3) and
this one are counted once. Website events need `client_user_agent` and `event_source_url`;
without either nothing is sent.

SECURITY: the token travels only in the request to graph.facebook.com and never appears in logs
or errors (`__repr__`, `_error`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import httpx

from empire_api.integrations.conversions import hashing

# WHY short: a send runs inside the outbox drain's batch, which holds row locks (D-057 review).
TIMEOUT: Final = httpx.Timeout(5.0, connect=3.0)
# Meta's throttling and temporary errors come back as 4xx with these codes or `is_transient`
# (Graph API error codes: 1 unknown, 2 service, 4 app limit, 17 user limit, 32 page limit,
# 341 app limit, 613 rate limit, 80004 too many calls to the ad account).
TRANSIENT_CODES: Final = frozenset({1, 2, 4, 17, 32, 341, 613, 80004})


class ConversionRetryableError(Exception):
    """The platform may accept it later (network, 5xx, rate limit). Message: a code only."""


class ConversionRejectedError(Exception):
    """The platform refused the request as it is; a retry can't help. Message: a code only."""


@dataclass(frozen=True)
class LeadForAds:
    """What a platform may receive about one lead. COMPLIANCE: nothing else."""

    lead_id: str
    reference: str
    created_at: datetime
    phone_e164: str | None
    email: str | None
    page_url: str | None
    gclid: str | None
    gbraid: str | None
    wbraid: str | None
    fbclid: str | None
    user_agent: str | None


def fbc(fbclid: str | None, created_at: datetime) -> str | None:
    """Meta's click id format, built from the `fbclid` we stored: fb.1.<ms>.<fbclid>."""
    if not fbclid:
        return None
    return f"fb.1.{int(created_at.timestamp() * 1000)}.{fbclid}"


def event_body(lead: LeadForAds, *, test_event_code: str = "") -> dict[str, Any] | None:
    """The request body, or None when the lead can't be sent as a website event."""
    if not lead.user_agent or not lead.page_url:
        return None  # both are required for website events
    user_data: dict[str, Any] = {"client_user_agent": lead.user_agent}
    if phone := hashing.meta_phone(lead.phone_e164):
        user_data["ph"] = [phone]
    if email := hashing.meta_email(lead.email):
        user_data["em"] = [email]
    if click := fbc(lead.fbclid, lead.created_at):
        user_data["fbc"] = click
    event: dict[str, Any] = {
        "event_name": "Lead",
        "event_time": int(lead.created_at.timestamp()),
        # WHY the reference: the browser Pixel's Lead event (6.3) only knows the reference the
        # form shows, and Meta counts the two once when their event ids match (D-058).
        "event_id": lead.reference,
        "action_source": "website",
        "user_data": user_data,
    }
    event["event_source_url"] = lead.page_url
    body: dict[str, Any] = {"data": [event]}
    if test_event_code:
        body["test_event_code"] = test_event_code
    return body


def _error(response: httpx.Response) -> tuple[str, bool]:
    """A code-only description of Meta's error, and whether a retry may help."""
    try:
        error = response.json().get("error", {})
    except ValueError, AttributeError:
        error = {}
    if not isinstance(error, dict):
        error = {}
    code = error.get("code")
    transient = bool(error.get("is_transient")) or code in TRANSIENT_CODES
    name = f"meta_{code}" if isinstance(code, int) else f"http_{response.status_code}"
    return name, transient


class MetaClient:
    def __init__(
        self,
        token: str,
        version: str,
        *,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self._token = token
        self._version = version
        self._client_factory = client_factory

    def __repr__(self) -> str:  # SECURITY
        return "MetaClient(token=***)"

    def send(self, pixel_id: str, body: dict[str, Any]) -> None:
        url = f"https://graph.facebook.com/{self._version}/{pixel_id}/events"
        factory = self._client_factory or (
            lambda: httpx.Client(timeout=TIMEOUT, follow_redirects=False)
        )
        try:
            with factory() as client:
                # SECURITY: the token goes in the body, never the URL (URLs reach logs).
                response = client.post(url, json={**body, "access_token": self._token})
        except httpx.HTTPError as exc:
            raise ConversionRetryableError(f"meta_unreachable_{type(exc).__name__}") from None
        if response.status_code == 200:
            return
        code, transient = _error(response)
        if transient or response.status_code == 429 or response.status_code >= 500:
            raise ConversionRetryableError(code)
        raise ConversionRejectedError(code)
