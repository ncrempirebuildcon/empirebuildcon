"""Request id, one access-log line per request, and the safety net for unexpected errors.

The id comes from `X-Request-ID` when a trusted hop set a sane one (letters, digits, dashes,
up to 64 chars), otherwise we make one. It is echoed back so a staff member can quote it.

WHY the error catch lives here: Starlette hands unhandled exceptions to its outermost layer,
which sits outside every middleware, so a 500 made there would miss the security headers,
`Cache-Control: no-store`, the request id and the request-id log context. Catching here keeps
all of those (main.py places this layer inside the security-headers layer).
"""

from __future__ import annotations

import json
import re
import secrets
import time

import sentry_sdk
import structlog
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from empire_api.errors import PROBLEM_MEDIA_TYPE
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
        started_response = {"value": False}

        async def send_with_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                started_response["value"] = True
                status_holder["status"] = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        except Exception as exc:
            if started_response["value"]:
                raise  # too late to send a clean error; the server closes the connection
            # SECURITY: log the type only; no request body, no exception message (may hold data).
            log.exception("unhandled_error", error_type=type(exc).__name__)
            sentry_sdk.capture_exception(exc)
            body = json.dumps(
                {
                    "type": "about:blank",
                    "title": "Internal Server Error",
                    "status": 500,
                    "detail": "Something went wrong on our side. Please try again in a minute.",
                    "instance": scope["path"],
                }
            ).encode()
            await send_with_id(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", PROBLEM_MEDIA_TYPE.encode()),
                        (b"content-length", str(len(body)).encode()),
                    ],
                }
            )
            await send_with_id({"type": "http.response.body", "body": body})
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 1)
            # PERF: health checks run every few minutes from monitors; don't fill logs with them.
            if not scope["path"].startswith("/api/health"):
                log.info("request", status=status_holder["status"], duration_ms=duration_ms)
            structlog.contextvars.clear_contextvars()
