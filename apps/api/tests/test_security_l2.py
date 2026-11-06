"""Fixes from the L2 security review (launch task L2): personal data stays out of logs and
Sentry; the API refuses to start without APP_ENV on a host; public bodies are capped."""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from empire_api import observability
from empire_api.config import Settings
from empire_api.db import get_engine
from empire_api.logs import _exception_without_message, _NoMessageFormatter
from empire_api.middleware.body_limit import PUBLIC_BODY_LIMIT

PHONE = "+919876543210"


def test_database_errors_hide_the_bound_values() -> None:
    """SQLAlchemy lists no bound values (hide_parameters). Postgres's own message can still quote
    a value, which is why logs and Sentry drop exception messages (the next two tests)."""
    with pytest.raises(DBAPIError) as caught, get_engine().connect() as conn:
        conn.execute(text("SELECT CAST(:phone AS integer)"), {"phone": PHONE})
    assert "[SQL parameters hidden" in str(caught.value)
    assert f"'phone': '{PHONE}'" not in str(caught.value)


def test_a_logged_exception_keeps_its_type_and_stack_but_not_its_message() -> None:
    try:
        raise ValueError(f"duplicate lead for {PHONE}")
    except ValueError:
        event = _exception_without_message(
            None, "error", {"event": "x", "exc_info": sys.exc_info()}
        )
    assert "ValueError" in event["exception"]
    assert "test_security_l2.py" in event["exception"]
    assert PHONE not in str(event)
    assert "exc_info" not in event


def test_sentry_events_lose_query_strings_unlisted_headers_and_messages() -> None:
    event = {
        "request": {
            "url": "https://api.example/api/v1/admin/leads",
            "query_string": f"q={PHONE}",
            "headers": {"User-Agent": "x", "X-Empire-Client-IP": "203.0.113.9", "Cookie": "s=1"},
            "data": {"phone": PHONE},
        },
        "exception": {"values": [{"type": "IntegrityError", "value": f"phone {PHONE}"}]},
    }
    out = observability._scrub(event, None)
    assert "query_string" not in out["request"] and "data" not in out["request"]
    assert out["request"]["headers"] == {
        "User-Agent": "x",
        "X-Empire-Client-IP": "[removed]",
        "Cookie": "[removed]",
    }
    assert out["exception"]["values"][0] == {"type": "IntegrityError", "value": "[removed]"}
    assert PHONE not in str(out)


def test_a_hosted_server_refuses_to_start_without_app_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("K_SERVICE", "empire-api")
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValueError, match="APP_ENV must be staging or production"):
        Settings()
    monkeypatch.setenv("APP_ENV", "test")
    with pytest.raises(ValueError, match="APP_ENV must be staging or production"):
        Settings()


def test_without_a_host_marker_development_still_starts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("K_SERVICE", raising=False)
    monkeypatch.delenv("CLOUD_RUN_JOB", raising=False)
    monkeypatch.setenv("APP_ENV", "development")
    assert Settings().app_env == "development"


def test_a_large_public_body_is_refused_before_the_app_reads_it(client: TestClient) -> None:
    big = {"name": "x" * (PUBLIC_BODY_LIMIT + 10)}
    answer = client.post("/api/v1/public/leads", json=big)
    assert answer.status_code == 413
    assert answer.json()["status"] == 413


def test_a_chunked_public_body_is_capped_too(client: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        for _ in range(5):
            yield b"x" * (PUBLIC_BODY_LIMIT // 4)

    answer = client.post(
        "/api/v1/public/leads", content=chunks(), headers={"content-type": "application/json"}
    )
    assert answer.status_code == 413


def test_a_normal_public_body_still_reaches_the_app(client: TestClient) -> None:
    # Invalid on purpose: the app answers (422), not the cap.
    answer = client.post("/api/v1/public/leads", json={"name": "Asha"})
    assert answer.status_code == 422


def test_chained_exceptions_keep_every_type_and_no_message() -> None:
    try:
        try:
            raise KeyError(PHONE)
        except KeyError as inner:
            raise RuntimeError(f"insert failed for {PHONE}") from inner
    except RuntimeError:
        event = _exception_without_message(None, "error", {"exc_info": sys.exc_info()})
    assert "KeyError" in event["exception"] and "RuntimeError" in event["exception"]
    assert PHONE not in event["exception"]


def test_stdlib_log_tracebacks_have_no_message() -> None:
    try:
        raise ValueError(PHONE)
    except ValueError:
        record = logging.LogRecord(
            "uvicorn.error", logging.ERROR, __file__, 1, "boom", None, sys.exc_info()
        )
    text = _NoMessageFormatter("%(message)s").format(record)
    assert "ValueError" in text and PHONE not in text


def test_breadcrumbs_lose_query_strings_and_log_messages() -> None:
    http = observability._scrub_breadcrumb(
        {
            "category": "http",
            "data": {"url": f"https://x/api?q={PHONE}", "http.query": f"q={PHONE}"},
        },
        None,
    )
    assert PHONE not in str(http) and http["data"]["url"] == "https://x/api"
    log = observability._scrub_breadcrumb({"category": "sqlalchemy", "message": PHONE}, None)
    assert log["message"] == "[removed]"
