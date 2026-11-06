"""A small size cap on request bodies sent to the public API (`/api/v1/public/*`).

Implements: the L2 security review (launch task L2). Anyone can POST an enquiry; without a cap
FastAPI reads and parses a body of any size (up to the web proxy's 10 MB) before validation or
the rate limit runs, so oversized posts would cost memory and CPU without being counted.
The largest real public body (an enquiry with a full message) is a few KB.

How it works: for a write to a public path, the body is read here up to PUBLIC_BODY_LIMIT bytes
(checked against Content-Length first, then while reading, so a chunked body is capped too),
then handed to the app unchanged. Past the cap the answer is 413 and the app never runs.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

PUBLIC_BODY_LIMIT = 32 * 1024
_PREFIX = "/api/v1/public"
_WRITES = frozenset({"POST", "PUT", "PATCH", "DELETE"})


async def _too_large(scope: Scope, send: Send) -> None:
    body = json.dumps(
        {
            "type": "about:blank",
            "title": "Payload Too Large",
            "status": 413,
            "detail": "That request is too large.",
            "instance": scope["path"],
        }
    ).encode()
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/problem+json"),
                (b"content-length", str(len(body)).encode()),
                (b"cache-control", b"no-store"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class PublicBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, limit: int = PUBLIC_BODY_LIMIT) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path: str = scope.get("path", "")
        if (
            scope["type"] != "http"
            or scope.get("method") not in _WRITES
            or not (path == _PREFIX or path.startswith(_PREFIX + "/"))
        ):
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    declared = int(value)
                except ValueError:
                    declared = self.limit + 1
                if declared > self.limit:
                    await _too_large(scope, send)
                    return
        chunks: list[bytes] = []
        size = 0
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # The client went away; let the app see the disconnect as usual.
                await self.app(scope, _replay([message], receive), send)
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > self.limit:
                await _too_large(scope, send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break
        body = {"type": "http.request", "body": b"".join(chunks)}
        await self.app(scope, _replay([body], receive), send)


def _replay(messages: list[Message], then: Receive | None = None) -> Receive:
    """Hands out `messages` first, then the real `receive` (a later disconnect stays real)."""
    queue = list(messages)

    async def receive() -> Message:
        if queue:
            return queue.pop(0)
        if then is not None:
            return await then()
        return {"type": "http.disconnect"}

    return receive
