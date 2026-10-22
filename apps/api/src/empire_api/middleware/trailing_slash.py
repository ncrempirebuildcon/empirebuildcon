"""Strip trailing slashes before routing so `/x` and `/x/` reach the same handler, with no redirect.

Implements: ARCHITECTURE §3 step 4 (the API never redirects).

DO NOT CHANGE: this replaces FastAPI's `redirect_slashes` (turned off in main.py). A 307/308 on
`/api/*` broke Current Investor in production: the browser re-sent the request to a different
origin and dropped the session cookie. tests/test_no_redirects.py calls every route both ways
and fails on any 3xx.
"""

from __future__ import annotations

from starlette.types import ASGIApp, Receive, Scope, Send


class StripTrailingSlashMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http":
            path: str = scope["path"]
            if len(path) > 1 and path.endswith("/"):
                stripped = path.rstrip("/") or "/"
                scope = dict(scope)
                scope["path"] = stripped
                raw: bytes | None = scope.get("raw_path")
                if raw is not None:
                    scope["raw_path"] = raw.rstrip(b"/") or b"/"
        await self.app(scope, receive, send)
