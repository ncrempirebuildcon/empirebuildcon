"""Tests for public caching (Cache-Control, strong/weak ETag, 304) and rate limits (Task 5.1).

Covers:
- Cache-Control header: public, max-age=60, stale-while-revalidate=300.
- Strong SHA-256 ETag format: "<64 hex chars>".
- 304 Not Modified when If-None-Match matches strong ETag.
- Weak ETag comparison (RFC 9110 §13.1.2): W/"<etag>" matches strong ETag and returns 304 (S8).
- Per-network rate limiting: 120 req/min allowed; 121st returns 429 with Retry-After header
  and Cache-Control: no-store (M6, N7).
- Hashed rate limit key using HMAC-SHA256 (M6).
- Edge-verified requests without X-Empire-Client-IP (SSR / ISR) are exempt from limits (M6, N6).
- IPv6 /64 subnet sharing the rate limit counter (M6).
"""

from __future__ import annotations

import contextlib
import json
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy.orm import Session

from empire_api.config import Settings, get_settings
from empire_api.db import get_engine
from empire_api.main import create_app
from empire_api.platform.crypto import hash_ip, network_key
from empire_api.platform.models import RateLimitBucket
from empire_api.platform.rate_limit import _window_start
from empire_api.public.caching import SERVER_RATE_LIMIT, cached_response
from empire_api.timeutil import utcnow

EDGE_KEY = "test-edge-key-0123456789-abcdefghijklmnopqrstuvwxyz"


@pytest.fixture
def edge_app() -> Iterator[FastAPI]:
    """The app as deployed with EDGE_PROXY_KEY configured."""
    settings = Settings(**{**get_settings().model_dump(), "edge_proxy_key": SecretStr(EDGE_KEY)})
    yield create_app(settings)


def test_public_cache_control_and_etag_304(client: TestClient) -> None:
    res = client.get("/api/v1/public/site")
    assert res.status_code == 200

    # 1. Cache-Control header
    assert res.headers.get("cache-control") == "public, max-age=60, stale-while-revalidate=300"

    # 2. Strong ETag
    etag = res.headers.get("etag")
    assert etag is not None
    assert etag.startswith('"') and etag.endswith('"')
    assert len(etag) == 66  # 64 hex characters + 2 quotes

    # 3. If-None-Match returning 304 Not Modified
    res_cached = client.get("/api/v1/public/site", headers={"If-None-Match": etag})
    assert res_cached.status_code == 304
    assert res_cached.headers.get("etag") == etag
    expected_cache = "public, max-age=60, stale-while-revalidate=300"
    assert res_cached.headers.get("cache-control") == expected_cache
    assert res_cached.content == b""  # Empty body on 304

    # 4. Weak ETag comparison (S8): W/"<etag>" should match
    weak_etag = f"W/{etag}"
    res_weak = client.get("/api/v1/public/site", headers={"If-None-Match": weak_etag})
    assert res_weak.status_code == 304
    assert res_weak.content == b""

    # 5. If-None-Match wildcard '*' returning 304
    res_wildcard = client.get("/api/v1/public/site", headers={"If-None-Match": "*"})
    assert res_wildcard.status_code == 304


def test_public_rate_limiting_ipv4_and_headers(edge_app: FastAPI) -> None:
    client = TestClient(edge_app, base_url="https://testserver", follow_redirects=False)
    test_ip = "198.51.100.99"
    headers = {
        "X-Empire-Edge-Key": EDGE_KEY,
        "X-Empire-Client-IP": test_ip,
    }

    # First requests should succeed
    for _ in range(5):
        r = client.get("/api/v1/public/site", headers=headers)
        assert r.status_code == 200

    # Exhaust the remaining bucket for this network using ORM (Part B Item 5)
    now = utcnow()
    start = _window_start(now, 60)
    key = f"public:{hash_ip(network_key(test_ip))}"
    with Session(get_engine()) as session:
        bucket = session.get(RateLimitBucket, (key, start))
        if not bucket:
            bucket = RateLimitBucket(
                key=key,
                window_start=start,
                count=120,
                expires_at=start + timedelta(seconds=120),
            )
            session.add(bucket)
        else:
            bucket.count = 120
        session.commit()

    # Next request should be rate-limited (429 Too Many Requests)
    res_blocked = client.get("/api/v1/public/site", headers=headers)
    assert res_blocked.status_code == 429
    assert "Retry-After" in res_blocked.headers
    assert int(res_blocked.headers["Retry-After"]) >= 1
    # N7: 429 response must have Cache-Control: no-store
    assert res_blocked.headers.get("cache-control") == "no-store"


def test_public_rate_limiting_ipv6_64_subnet(edge_app: FastAPI) -> None:
    client = TestClient(edge_app, base_url="https://testserver", follow_redirects=False)
    # Two distinct addresses in the same /64 subnet
    ip1 = "2001:db8:abcd:0012:0000:0000:0000:0001"
    ip2 = "2001:db8:abcd:0012:ffff:ffff:ffff:ffff"

    headers1 = {
        "X-Empire-Edge-Key": EDGE_KEY,
        "X-Empire-Client-IP": ip1,
    }
    headers2 = {
        "X-Empire-Edge-Key": EDGE_KEY,
        "X-Empire-Client-IP": ip2,
    }

    # Requests from ip1 succeed
    for _ in range(5):
        r = client.get("/api/v1/public/site", headers=headers1)
        assert r.status_code == 200

    # Exhaust the /64 subnet bucket using ORM (Part B Item 5)
    now = utcnow()
    start = _window_start(now, 60)
    key = f"public:{hash_ip(network_key(ip1))}"
    with Session(get_engine()) as session:
        bucket = session.get(RateLimitBucket, (key, start))
        if not bucket:
            bucket = RateLimitBucket(
                key=key,
                window_start=start,
                count=120,
                expires_at=start + timedelta(seconds=120),
            )
            session.add(bucket)
        else:
            bucket.count = 120
        session.commit()

    # Next request from ip2 in same /64 subnet should be blocked
    res_blocked = client.get("/api/v1/public/site", headers=headers2)
    assert res_blocked.status_code == 429
    assert res_blocked.headers.get("cache-control") == "no-store"


def test_public_rate_limiting_edge_ssr_server_bucket(edge_app: FastAPI) -> None:
    """R2-M2 / R2-S2: Header-less edge requests have a dedicated server bucket (3,000 req/min)."""
    client = TestClient(edge_app, base_url="https://testserver", follow_redirects=False)
    # SSR / ISR request from edge carries Edge Key but NO client IP header
    headers = {
        "X-Empire-Edge-Key": EDGE_KEY,
    }

    # Verify requests pass under the server budget
    for _ in range(5):
        r = client.get("/api/v1/public/site", headers=headers)
        assert r.status_code == 200

    # Exhaust the server bucket in DB using ORM (Part B Item 5)
    now = utcnow()
    start = _window_start(now, 60)
    with Session(get_engine()) as session:
        bucket = session.get(RateLimitBucket, ("public:server", start))
        if not bucket:
            bucket = RateLimitBucket(
                key="public:server",
                window_start=start,
                count=SERVER_RATE_LIMIT,
                expires_at=start + timedelta(seconds=120),
            )
            session.add(bucket)
        else:
            bucket.count = SERVER_RATE_LIMIT
        session.commit()

    # Next request to public endpoint should be blocked with 429 and no-store
    res_blocked = client.get("/api/v1/public/site", headers=headers)
    assert res_blocked.status_code == 429
    assert res_blocked.headers.get("cache-control") == "no-store"


def test_public_rate_limiting_server_bucket_structured_warning_log(
    edge_app: FastAPI, capsys: pytest.CaptureFixture[str]
) -> None:
    """Part B Item 1: Server rate bucket usage emits structured warning with no IP."""
    client = TestClient(edge_app, base_url="https://testserver", follow_redirects=False)
    headers = {"X-Empire-Edge-Key": EDGE_KEY}

    res = client.get("/api/v1/public/site", headers=headers)
    assert res.status_code == 200

    captured = capsys.readouterr()
    log_lines = []
    for line in captured.out.strip().splitlines():
        if line.strip().startswith("{") and line.strip().endswith("}"):
            with contextlib.suppress(json.JSONDecodeError):
                log_lines.append(json.loads(line))

    warning_logs = [
        entry for entry in log_lines if entry.get("event") == "public_rate_limit_server_bucket_used"
    ]
    assert len(warning_logs) > 0, f"Expected server bucket warning in logs, got: {captured.out}"
    entry = warning_logs[0]
    assert entry.get("level") == "info"
    assert entry.get("path") == "/api/v1/public/site"
    assert entry.get("method") == "GET"
    # INVARIANT: Structured log must not carry raw IP
    assert "ip" not in entry
    assert "client_ip" not in entry
    assert "127.0.0.1" not in str(entry)


def test_cached_response_honours_status_code_and_no_store_on_error() -> None:
    """Part B Item 5: cached_response honours status_code and sets no-store on >= 400."""
    req = Request({"type": "http", "method": "GET", "path": "/test", "headers": []})
    res_200 = cached_response(req, {"ok": True}, status_code=200)
    assert res_200.status_code == 200
    assert "public" in res_200.headers.get("cache-control", "")
    assert "ETag" in res_200.headers

    # Error status 404
    res_404 = cached_response(req, {"detail": "Missing"}, status_code=404)
    assert res_404.status_code == 404
    assert res_404.headers.get("cache-control") == "no-store"

    # Error status 422
    res_422 = cached_response(req, {"detail": "Invalid"}, status_code=422)
    assert res_422.status_code == 422
    assert res_422.headers.get("cache-control") == "no-store"

    # Even if client sends matching If-None-Match, an error must NEVER return 304
    req_etag = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/test",
            "headers": [(b"if-none-match", b"*")],
        }
    )
    res_err = cached_response(req_etag, {"detail": "Failed"}, status_code=500)
    assert res_err.status_code == 500
    assert res_err.headers.get("cache-control") == "no-store"


def test_public_404_cache_control_no_store(client: TestClient) -> None:
    """R2-S3: 404 responses from public detail routes must carry Cache-Control: no-store."""
    res_proj = client.get("/api/v1/public/projects/missing-project-slug")
    assert res_proj.status_code == 404
    assert res_proj.headers.get("cache-control") == "no-store"

    res_page = client.get("/api/v1/public/pages/missing-page-slug")
    assert res_page.status_code == 404
    assert res_page.headers.get("cache-control") == "no-store"

    res_post = client.get("/api/v1/public/posts/missing-post-slug")
    assert res_post.status_code == 404
    assert res_post.headers.get("cache-control") == "no-store"

    res_prop = client.get("/api/v1/public/projects/some-proj/configurations/missing-cfg")
    assert res_prop.status_code == 404
    assert res_prop.headers.get("cache-control") == "no-store"


def test_public_rate_limit_key_hashing() -> None:
    # Test key hashing function and key construction
    ip = "203.0.113.195"
    net = network_key(ip)
    h = hash_ip(net)
    assert isinstance(h, str)
    assert len(h) == 32
    assert ip not in h  # Pseudonymized, does not leak raw IP
    assert f"public:{h}".startswith("public:")
