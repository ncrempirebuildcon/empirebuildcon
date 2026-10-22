"""Request id + one access-log line per request (ARCHITECTURE §20).

The id comes from `X-Request-ID` when a trusted hop set a sane one (letters, digits, dashes,
up to 64 chars), otherwise we make one. It is echoed back so a staff member can quote it.
"""

from __future__ import annotations

import re
import secrets
import time

import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from empire_api.logs import get_logger

_VALID_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")
log = get_logger("empire_api.access")


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        incoming = ""
        for name, value in scope.get("headers", []):
            if name == b"x-request-id":
                incoming = value.decode("latin-1")
                break
        request_id = incoming if _VALID_ID.match(incoming) else secrets.token_hex(8)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id, method=scope["method"], path=scope["path"]
        )
        started = time.perf_counter()
        status_holder = {"status": 500}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                status_holder["status"] = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            # PERF: health checks run every few minutes from monitors; don't fill logs with them.
            if not scope["path"].startswith("/api/health"):
                log.info("request", status=status_holder["status"], duration_ms=duration_ms)
            structlog.contextvars.clear_contextvars()
