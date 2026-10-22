"""Security headers on every API response (SECURITY.md §4).

The web app sets its own headers for pages; these cover JSON answers from the API, including
error responses produced by exception handlers.

SECURITY: `Cache-Control: no-store` on auth, admin and internal routes stops shared caches
(Cloudflare, browsers) from keeping staff data or session responses.
"""

from __future__ import annotations

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_NO_STORE_PREFIXES = ("/api/v1/admin", "/api/v1/auth", "/api/v1/internal")
_DOCS_PATHS = ("/api/docs", "/api/redoc")

_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
    "X-Frame-Options": "DENY",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}
# JSON never needs to load anything; the docs UI (development only) loads Swagger assets.
_API_CSP = "default-src 'none'; frame-ancestors 'none'"
_HSTS = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in _BASE_HEADERS.items():
                    headers.setdefault(name, value)
                if not path.startswith(_DOCS_PATHS):
                    headers.setdefault("Content-Security-Policy", _API_CSP)
                if path.startswith(_NO_STORE_PREFIXES):
                    headers["Cache-Control"] = "no-store"
                if self.hsts:
                    headers.setdefault("Strict-Transport-Security", _HSTS)
            await send(message)

        await self.app(scope, receive, send_with_headers)
