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


def _scrub(event: Any, hint: Any) -> Any:
    request = event.get("request") if isinstance(event, dict) else None
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        headers = request.get("headers")
        if isinstance(headers, dict):
            for name in list(headers):
                if name.lower() in {
                    "cookie",
                    "x-csrf-token",
                    "x-internal-key",
                    "x-empire-edge-key",
                    "authorization",
                }:
                    headers[name] = "[removed]"
    return event


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
    )
    sentry_sdk.set_tag("component", component)
    return True
