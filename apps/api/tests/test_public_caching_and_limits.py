"""Tests for public endpoints caching (Cache-Control, strong ETag, 304) and rate limits (Task 5.1).

Covers:
- Cache-Control header: public, max-age=60, stale-while-revalidate=300.
- Strong SHA-256 ETag format: "<64 hex chars>".
- 304 Not Modified when If-None-Match matches.
- Per-network rate limiting: 120 req/min allowed; 121st returns 429 with Retry-After header.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


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

    # 4. If-None-Match wildcard '*' returning 304
    res_wildcard = client.get("/api/v1/public/site", headers={"If-None-Match": "*"})
    assert res_wildcard.status_code == 304


def test_public_rate_limiting(client: TestClient) -> None:
    # Use a custom unique IP header for rate-limit isolation
    test_ip = "198.51.100.42"
    headers = {"X-Forwarded-For": test_ip}

    # First 120 requests should succeed
    for _ in range(120):
        r = client.get("/api/v1/public/site", headers=headers)
        assert r.status_code == 200

    # 121st request should be rate-limited (429 Too Many Requests)
    res_blocked = client.get("/api/v1/public/site", headers=headers)
    assert res_blocked.status_code == 429
    assert "Retry-After" in res_blocked.headers
    assert int(res_blocked.headers["Retry-After"]) >= 1
