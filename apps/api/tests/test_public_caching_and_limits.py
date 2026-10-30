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

from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import text

from empire_api.config import Settings, get_settings
from empire_api.db import get_engine
from empire_api.main import create_app
from empire_api.platform.crypto import hash_ip, network_key
from empire_api.platform.rate_limit import _window_start
from empire_api.public.caching import SERVER_RATE_LIMIT
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

    # Exhaust the remaining bucket for this network
    now = utcnow()
    start = _window_start(now, 60)
    key = f"public:{hash_ip(network_key(test_ip))}"
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO rate_limit_bucket (key, window_start, count, expires_at) "
                "VALUES (:key, :start, :limit, :expires) "
                "ON CONFLICT (key, window_start) DO UPDATE SET count = :limit"
            ),
            {"key": key, "start": start, "limit": 120, "expires": start + timedelta(seconds=120)},
        )

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

    # Exhaust the /64 subnet bucket
    now = utcnow()
    start = _window_start(now, 60)
    key = f"public:{hash_ip(network_key(ip1))}"
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO rate_limit_bucket (key, window_start, count, expires_at) "
                "VALUES (:key, :start, :limit, :expires) "
                "ON CONFLICT (key, window_start) DO UPDATE SET count = :limit"
            ),
            {"key": key, "start": start, "limit": 120, "expires": start + timedelta(seconds=120)},
        )

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

    # Exhaust the server bucket in DB
    now = utcnow()
    start = _window_start(now, 60)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO rate_limit_bucket (key, window_start, count, expires_at) "
                "VALUES ('public:server', :start, :limit, :expires) "
                "ON CONFLICT (key, window_start) DO UPDATE SET count = :limit"
            ),
            {"start": start, "limit": SERVER_RATE_LIMIT, "expires": start + timedelta(seconds=120)},
        )

    # Next request to public endpoint should be blocked with 429 and no-store
    res_blocked = client.get("/api/v1/public/site", headers=headers)
    assert res_blocked.status_code == 429
    assert res_blocked.headers.get("cache-control") == "no-store"


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
