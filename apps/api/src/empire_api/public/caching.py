"""Caching, ETag generation, and rate limits for public read endpoints (Task 5.1).

Implements:
- Scope #13: Cache-Control: public, max-age=60, stale-while-revalidate=300
- Strong SHA-256 ETag (answers 304 Not Modified when If-None-Match matches)
- Per-network rate limit (120 req/min per network key) answering 429 with Retry-After.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Final

from fastapi import Request, Response
from pydantic import BaseModel

from empire_api.errors import ApiProblem
from empire_api.platform.crypto import client_ip, hash_ip, network_key
from empire_api.platform.rate_limit import hit

PUBLIC_CACHE_CONTROL: Final = "public, max-age=60, stale-while-revalidate=300"
PUBLIC_RATE_LIMIT: Final = 120
PUBLIC_RATE_WINDOW: Final = 60


def make_etag(data_bytes: bytes) -> str:
    """Generate a strong SHA-256 ETag enclosed in double quotes."""
    return f'"{hashlib.sha256(data_bytes).hexdigest()}"'


def _strip_etag_weakness(tag: str) -> str:
    t = tag.strip()
    if t.startswith("W/") or t.startswith("w/"):
        t = t[2:].strip()
    return t


def matches_etag(if_none_match: str | None, etag: str) -> bool:
    """Check whether any tag in If-None-Match matches ETag (weak comparison, RFC 9110 §13.1.2)."""
    if not if_none_match:
        return False
    clean_etag = _strip_etag_weakness(etag)
    tags = [_strip_etag_weakness(t) for t in if_none_match.split(",")]
    return clean_etag in tags or "*" in tags


def check_public_rate_limit(request: Request) -> None:
    """Enforce per-network rate limit on public endpoints.

    M6: Edge-verified requests carrying no X-Empire-Client-IP header are internal Next.js
    server-side renders (SSR / ISR) or build pre-fetches and are exempt from the per-visitor limit.
    Visitor requests forwarded by the edge proxy carry X-Empire-Client-IP, which is
    network-bucketed (/64 for IPv6) and pseudonymized via hash_ip.
    """
    is_edge = bool(request.scope.get("empire_edge_verified"))
    has_client_header = "x-empire-client-ip" in request.headers
    if is_edge and not has_client_header:
        return

    ip = client_ip(request)
    net = network_key(ip)
    key = f"public:{hash_ip(net)}"
    result = hit(key, limit=PUBLIC_RATE_LIMIT, window_seconds=PUBLIC_RATE_WINDOW)
    if not result.allowed:
        raise ApiProblem(
            429,
            "Too many requests. Please slow down and try again.",
            headers={
                "Retry-After": str(result.retry_after),
                "Cache-Control": "no-store",
            },
        )


def cached_response(
    request: Request,
    data: Any,
    *,
    status_code: int = 200,
) -> Response:
    """Serialize response data, calculate strong ETag, check 304, and set Cache-Control."""
    if isinstance(data, BaseModel):
        body_dict: Any = data.model_dump(mode="json")
    elif isinstance(data, list):
        body_dict = [
            item.model_dump(mode="json") if isinstance(item, BaseModel) else item for item in data
        ]
    else:
        body_dict = data

    body_bytes = json.dumps(body_dict, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    etag = make_etag(body_bytes)

    cache_control = "no-store" if status_code >= 400 else PUBLIC_CACHE_CONTROL

    if matches_etag(request.headers.get("if-none-match"), etag):
        return Response(
            status_code=304,
            headers={
                "ETag": etag,
                "Cache-Control": cache_control,
            },
        )

    return Response(
        content=body_bytes,
        status_code=status_code,
        media_type="application/json",
        headers={
            "ETag": etag,
            "Cache-Control": cache_control,
        },
    )
