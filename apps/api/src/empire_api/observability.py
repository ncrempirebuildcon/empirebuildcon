"""Sentry error tracking for the API and worker (ARCHITECTURE §20). Off when no DSN is set.

SECURITY: `send_default_pii=False` keeps cookies, IPs and request bodies (lead data) out of
Sentry; the before_send hook also drops request bodies and cookies defensively.
DO NOT CHANGE `include_local_variables=False`: with local variables on, a crash during sign-in
or a password change would send the typed password (and lead details) to Sentry.
"""

from __future__ import annotations

from typing import Any

import sentry_sdk

from empire_api.config import Settings

# SECURITY (L2 security review): headers kept on an event; everything else is dropped. The
# visitor's IP (X-Empire-Client-IP and the host's client-IP header) and every key are not here.
_KEPT_HEADERS = frozenset(
    {"accept", "content-type", "content-length", "user-agent", "x-request-id", "host"}
)


def _scrub(event: Any, hint: Any) -> Any:
    """Before an event or transaction leaves for Sentry: no body, cookies, query string (lead
    search text), unlisted headers, or exception messages (they can quote stored values)."""
    if not isinstance(event, dict):
        return event
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        request.pop("env", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() not in _KEPT_HEADERS:
                    headers[name] = "[removed]"
    exception = event.get("exception")
    values = exception.get("values") if isinstance(exception, dict) else None
    for item in values if isinstance(values, list) else []:
        if isinstance(item, dict) and item.get("value"):
            # The type and the stack stay; the message can hold a lead's phone or name.
            item["value"] = "[removed]"
    return event


def _scrub_breadcrumb(crumb: Any, hint: Any) -> Any:
    """Breadcrumbs (HTTP calls, stdlib log lines) without query strings or log messages."""
    if not isinstance(crumb, dict):
        return crumb
    data = crumb.get("data")
    if isinstance(data, dict):
        if isinstance(data.get("url"), str):
            data["url"] = data["url"].split("?", 1)[0]
        if "http.query" in data:
            data["http.query"] = "[removed]"
    if crumb.get("category") != "http" and crumb.get("message"):
        crumb["message"] = "[removed]"
    return crumb


def init_sentry(settings: Settings, *, component: str) -> bool:
    if not settings.sentry_dsn_api:
        return False
    sentry_sdk.init(
        dsn=settings.sentry_dsn_api,
        environment=settings.app_env,
        release=f"empire-api@{settings.version}",
        send_default_pii=False,
        include_local_variables=False,
        traces_sample_rate=0.05,
        before_send=_scrub,
        before_send_transaction=_scrub,
        before_breadcrumb=_scrub_breadcrumb,
    )
    sentry_sdk.set_tag("component", component)
    return True
