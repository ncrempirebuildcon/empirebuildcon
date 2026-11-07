"""Google Ads conversions through the Data Manager API (task 6.2, D-057).

Why the Data Manager API and not the Google Ads API: Google closed `UploadClickConversions`
(offline click conversions and enhanced conversions for leads) to accounts that hadn't used it
in the previous 180 days, from 15 June 2026; the Data Manager API replaces it
(searchengineland.com/google-is-moving-offline-conversion-imports-out-of-the-google-ads-api-477669).

Request (developers.google.com/data-manager/api/reference/rest/v1/events/ingest and the Google
Ads "send events" guide, read 7 Nov 2026):
  POST https://datamanager.googleapis.com/v1/events:ingest, OAuth scope
  https://www.googleapis.com/auth/datamanager; body `destinations` (operatingAccount
  {accountType GOOGLE_ADS, accountId}, optional loginAccount, productDestinationId = the
  conversion action id), `encoding` HEX, `events` (transactionId, eventTimestamp RFC 3339,
  eventSource WEB, adIdentifiers {gclid|gbraid|wbraid}, userData.userIdentifiers with hashed
  emailAddress / phoneNumber), `consent` {adUserData, adPersonalization}, `validateOnly`.

A lead is sent only when it has an ad click id or a hashed contact detail. `transactionId` is the
lead's id, so a retried send isn't counted twice.

SECURITY: the client secret and refresh token go only to oauth2.googleapis.com; the access token
only to datamanager.googleapis.com. Neither is logged.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import httpx

from empire_api.integrations.conversions import hashing
from empire_api.integrations.conversions.meta import (
    ConversionRejectedError,
    ConversionRetryableError,
    LeadForAds,
)

TOKEN_URL: Final = "https://oauth2.googleapis.com/token"  # noqa: S105 — a URL, not a secret
INGEST_URL: Final = "https://datamanager.googleapis.com/v1/events:ingest"
TIMEOUT: Final = httpx.Timeout(5.0, connect=3.0)  # WHY short: as meta.TIMEOUT


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


def event_body(
    lead: LeadForAds,
    *,
    customer_id: str,
    login_customer_id: str,
    conversion_action_id: str,
    validate_only: bool,
) -> dict[str, Any] | None:
    """The request body, or None when there is nothing Google could match the lead on."""
    identifiers: list[dict[str, str]] = []
    if email := hashing.google_email(lead.email):
        identifiers.append({"emailAddress": email})
    if phone := hashing.google_phone(lead.phone_e164):
        identifiers.append({"phoneNumber": phone})
    # One click id only, gclid first: Google treats them as alternatives for one click.
    ad_ids: dict[str, str] = {}
    for key, value in (("gclid", lead.gclid), ("gbraid", lead.gbraid), ("wbraid", lead.wbraid)):
        if value:
            ad_ids = {key: value}
            break
    if not identifiers and not ad_ids:
        return None
    destination: dict[str, Any] = {
        "operatingAccount": {"accountType": "GOOGLE_ADS", "accountId": _digits(customer_id)},
        "productDestinationId": conversion_action_id.strip(),
    }
    if login_customer_id.strip():
        destination["loginAccount"] = {
            "accountType": "GOOGLE_ADS",
            "accountId": _digits(login_customer_id),
        }
    event: dict[str, Any] = {
        "transactionId": lead.lead_id,
        "eventTimestamp": lead.created_at.isoformat(),
        "eventSource": "WEB",
    }
    if ad_ids:
        event["adIdentifiers"] = ad_ids
    if identifiers:
        event["userData"] = {"userIdentifiers": identifiers}
    return {
        "destinations": [destination],
        "encoding": "HEX",
        # COMPLIANCE: only leads that gave marketing consent reach here (handlers.py).
        "consent": {"adUserData": "CONSENT_GRANTED", "adPersonalization": "CONSENT_DENIED"},
        "events": [event],
        "validateOnly": validate_only,
    }


def _error_code(response: httpx.Response, prefix: str) -> str:
    try:
        error = response.json().get("error")
    except ValueError, AttributeError:
        return f"{prefix}_http_{response.status_code}"
    status = error.get("status") if isinstance(error, dict) else error
    if isinstance(status, str) and status.replace("_", "").isalnum() and len(status) <= 60:
        return f"{prefix}_{status}"
    return f"{prefix}_http_{response.status_code}"


class GoogleClient:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        client_factory: Callable[[], httpx.Client] | None = None,
    ) -> None:
        self._client_id = client_id
        self._client_secret = client_secret
        self._refresh_token = refresh_token
        self._client_factory = client_factory

    def __repr__(self) -> str:  # SECURITY
        return "GoogleClient(secret=***)"

    def _client(self) -> httpx.Client:
        factory = self._client_factory or (
            lambda: httpx.Client(timeout=TIMEOUT, follow_redirects=False)
        )
        return factory()

    def _access_token(self, client: httpx.Client) -> str:
        response = client.post(
            TOKEN_URL,
            data={
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code != 200:
            code = _error_code(response, "google_oauth")
            if response.status_code >= 500 or response.status_code == 429:
                raise ConversionRetryableError(code)
            raise ConversionRejectedError(code)
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise ConversionRetryableError("google_oauth_no_token")
        return token

    def send(self, body: dict[str, Any]) -> None:
        try:
            with self._client() as client:
                token = self._access_token(client)
                response = client.post(
                    INGEST_URL, json=body, headers={"Authorization": f"Bearer {token}"}
                )
        except httpx.HTTPError as exc:
            raise ConversionRetryableError(f"google_unreachable_{type(exc).__name__}") from None
        if response.status_code == 200:
            return
        code = _error_code(response, "google")
        if response.status_code == 429 or response.status_code >= 500:
            raise ConversionRetryableError(code)
        raise ConversionRejectedError(code)
