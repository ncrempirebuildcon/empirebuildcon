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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from empire_api.config import Settings, get_settings
from empire_api.main import create_app
from empire_api.platform.crypto import hash_ip, network_key

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

    # First 120 requests should succeed
    for _ in range(120):
        r = client.get("/api/v1/public/site", headers=headers)
        assert r.status_code == 200

    # 121st request should be rate-limited (429 Too Many Requests)
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

    # 120 requests from ip1
    for _ in range(120):
        r = client.get("/api/v1/public/site", headers=headers1)
        assert r.status_code == 200

    # Next request from ip2 in same /64 subnet should be blocked
    res_blocked = client.get("/api/v1/public/site", headers=headers2)
    assert res_blocked.status_code == 429
    assert res_blocked.headers.get("cache-control") == "no-store"


def test_public_rate_limiting_edge_ssr_exempt(edge_app: FastAPI) -> None:
    client = TestClient(edge_app, base_url="https://testserver", follow_redirects=False)
    # SSR / ISR request from edge carries Edge Key but NO client IP header
    headers = {
        "X-Empire-Edge-Key": EDGE_KEY,
    }

    # Even 130 requests should all pass without being rate-limited
    for _ in range(130):
        r = client.get("/api/v1/public/site", headers=headers)
        assert r.status_code == 200


def test_public_rate_limit_key_hashing() -> None:
    # Test key hashing function
    ip = "203.0.113.195"
    net = network_key(ip)
    h = hash_ip(net)
    assert isinstance(h, str)
    assert len(h) == 32
    assert ip not in h  # Pseudonymized, does not leak raw IP
