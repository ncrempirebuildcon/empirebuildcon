"""The rate-limit counter must not wait for the request pool (task L7a).

The L7a load test sent 10 enquiries at once: each request held its session's connection and
then asked the same pool for a second one for the rate limit, so all of them waited for each
other and failed after 30 s. The counter now uses its own small pool (db.get_side_engine).
"""

from __future__ import annotations

import time
from collections.abc import Iterator

import pytest

from empire_api.config import get_settings
from empire_api.db import get_engine, reset_engine
from empire_api.platform import rate_limit


@pytest.fixture
def tiny_pool(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """The request pool shrunk to 1 + 1 overflow, so it is easy to use up."""
    monkeypatch.setenv("DB_POOL_SIZE", "1")
    get_settings.cache_clear()
    reset_engine()
    yield
    monkeypatch.delenv("DB_POOL_SIZE")
    get_settings.cache_clear()
    reset_engine()


def test_rate_limit_counts_while_every_request_connection_is_in_use(tiny_pool: None) -> None:
    engine = get_engine()
    held = [engine.connect() for _ in range(2)]  # the whole request pool, as busy requests hold it
    try:
        started = time.monotonic()
        result = rate_limit.hit("l7a-side-pool-test", limit=5, window_seconds=60)
        assert result.allowed and result.count == 1
        assert time.monotonic() - started < 5  # no wait for the request pool
    finally:
        for conn in held:
            conn.close()
