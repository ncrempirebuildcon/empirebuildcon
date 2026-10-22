"""Only our own web proxy may call the API (when EDGE_PROXY_KEY is set).

How it works:
  1. apps/web/src/proxy.ts adds `X-Empire-Edge-Key` (a shared secret) to every /api/* request
     it forwards, after removing any copy the visitor sent.
  2. Here we compare it in constant time. A match marks the request as coming from our edge,
     which is what lets `platform.crypto.client_ip` trust `X-Empire-Client-IP`.
  3. A missing or wrong key gets 403, so the API host (e.g. *.run.app) can't be used directly
     to dodge rate limits or to spoof client IPs.

Exempt: health checks (uptime monitors and the host's own probes) and /api/v1/internal/*
(the scheduler calls those directly with its own X-Internal-Key).

SECURITY: with no EDGE_PROXY_KEY (local development only — staging and production refuse to
start without one, see config.py) every request passes and the socket address is used.
"""

from __future__ import annotations

import hmac
import json

from starlette.types import ASGIApp, Receive, Scope, Send

from empire_api.errors import PROBLEM_MEDIA_TYPE

EDGE_KEY_HEADER = b"x-empire-edge-key"
_EXEMPT_PREFIXES = ("/api/health", "/api/v1/internal/")


class EdgeGuardMiddleware:
    def __init__(self, app: ASGIApp, *, edge_key: str) -> None:
        self.app = app
        self._expected = edge_key.encode()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        expected = self._expected
        if not expected:
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        presented = b""
        for name, value in scope.get("headers", []):
            if name == EDGE_KEY_HEADER:
                presented = value
                break
        if presented and hmac.compare_digest(presented, expected):
            scope["empire_edge_verified"] = True
            await self.app(scope, receive, send)
            return
        if path.startswith(_EXEMPT_PREFIXES):
            await self.app(scope, receive, send)
            return
        body = json.dumps(
            {
                "type": "about:blank",
                "title": "Forbidden",
                "status": 403,
                "detail": "Use the website to reach this service.",
                "instance": path,
            }
        ).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", PROBLEM_MEDIA_TYPE.encode()),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
