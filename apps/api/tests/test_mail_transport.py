"""The email transports (mail/transport.py): Resend's request shape and headers (httpx mocked,
never the real API), which failures are retried and which are permanent, a stable idempotency
key across retries, the dev mailbox, its route existing only in development and test, and the
configuration rules for staging and production."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.config import Settings, get_settings
from empire_api.integrations import handlers
from empire_api.integrations.outbox_drain import drain
from empire_api.mail import delivery, transport
from empire_api.mail import resend as resend_module
from empire_api.mail.dev import DevTransport
from empire_api.mail.models import EmailMessage
from empire_api.mail.resend import ENDPOINT, TIMEOUT_SECONDS, ResendTransport
from empire_api.mail.templates import Rendered
from empire_api.mail.transport import OutgoingEmail, PermanentEmailError, RetryableEmailError
from empire_api.main import create_app
from empire_api.platform.models import OutboxEvent
from empire_api.platform.outbox import emit

KEY = "not-a-real-resend-key-for-tests"
# Taken before conftest's `no_network` swaps it for one that fails the test.
REAL_CLIENT = resend_module._default_client


def message(**overrides: Any) -> OutgoingEmail:
    values: dict[str, Any] = {
        "to": "owner@example.com",
        "subject": "Subject",
        "text": "Plain text",
        "html": "<p>HTML</p>",
        "template": "reset_link",
        "sender_name": "Empire CMS",
        "reply_to": "sales@example.com",
        "idempotency_key": "empire-event-reset_link-abc",
    }
    values.update(overrides)
    return OutgoingEmail(**values)


def resend_with(
    handler: Callable[[httpx.Request], httpx.Response], seen: list[httpx.Request]
) -> ResendTransport:
    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    return ResendTransport(
        KEY, client_factory=lambda: httpx.Client(transport=httpx.MockTransport(record))
    )


def answer(
    status: int, body: dict[str, Any] | None = None
) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(status, json=body or {})


# --- Resend --------------------------------------------------------------------------------


def test_resend_request_shape_and_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EMAIL_FROM", "alerts@example.com")
    get_settings.cache_clear()
    seen: list[httpx.Request] = []
    sender = resend_with(answer(200, {"id": "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"}), seen)
    try:
        provider_id = sender.send(message())
    finally:
        monkeypatch.delenv("EMAIL_FROM")
        get_settings.cache_clear()
    assert provider_id == "49a3999c-0ce1-4ea6-ab68-afcd6dc2e794"
    [request] = seen
    assert request.method == "POST" and str(request.url) == ENDPOINT
    assert request.headers["authorization"] == f"Bearer {KEY}"
    assert request.headers["idempotency-key"] == "empire-event-reset_link-abc"
    assert request.headers["content-type"] == "application/json"
    assert json.loads(request.content) == {
        "from": "Empire CMS <alerts@example.com>",
        "to": ["owner@example.com"],
        "subject": "Subject",
        "text": "Plain text",
        "html": "<p>HTML</p>",
        "reply_to": "sales@example.com",
    }


def test_resend_uses_a_ten_second_timeout_and_no_redirects() -> None:
    with REAL_CLIENT() as client:  # building a client opens no connection
        assert client.timeout.read == TIMEOUT_SECONDS
        assert client.follow_redirects is False


def test_no_reply_to_when_none_is_set() -> None:
    seen: list[httpx.Request] = []
    resend_with(answer(200, {"id": "x"}), seen).send(message(reply_to=None))
    assert "reply_to" not in json.loads(seen[0].content)


@pytest.mark.parametrize(
    ("status", "name"),
    [
        (429, "rate_limit_exceeded"),
        (429, "daily_quota_exceeded"),
        (500, "application_error"),
        (503, "service_unavailable"),
        (409, "concurrent_idempotent_requests"),
        (401, "missing_api_key"),
        (403, "validation_error"),
    ],
)
def test_these_failures_are_retried(status: int, name: str) -> None:
    sender = resend_with(answer(status, {"statusCode": status, "name": name, "message": "x"}), [])
    with pytest.raises(RetryableEmailError) as raised:
        sender.send(message())
    assert str(status) in str(raised.value) and name in str(raised.value)


@pytest.mark.parametrize(
    ("status", "name"),
    [(422, "missing_required_field"), (400, "validation_error"), (422, "invalid_parameter")],
)
def test_a_refused_message_is_permanent(status: int, name: str) -> None:
    sender = resend_with(answer(status, {"name": name, "message": "owner@example.com is bad"}), [])
    with pytest.raises(PermanentEmailError) as raised:
        sender.send(message())
    # SECURITY: the error names the status and type, never what Resend echoed back.
    assert "owner@example.com" not in str(raised.value)


def test_network_errors_and_timeouts_are_retried() -> None:
    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    with pytest.raises(RetryableEmailError, match="unreachable"):
        resend_with(boom, []).send(message())


def test_a_changed_body_for_a_used_key_counts_as_sent() -> None:
    sender = resend_with(answer(409, {"name": "invalid_idempotent_request"}), [])
    assert sender.send(message()) == ""


def test_the_key_never_shows_in_repr_or_errors() -> None:
    sender = resend_with(answer(500, {"name": "application_error"}), [])
    assert KEY not in repr(sender)
    with pytest.raises(RetryableEmailError) as raised:
        sender.send(message())
    assert KEY not in str(raised.value)


def test_tests_can_not_reach_the_real_resend() -> None:
    with pytest.raises(AssertionError, match="Resend"):
        ResendTransport(KEY).send(message())


# --- Idempotency across retries ------------------------------------------------------------


def event_row(db: Session) -> OutboxEvent:
    row = emit(db, type_="test.mail", aggregate_type="user", aggregate_id="x")
    db.commit()
    db.refresh(row)
    return row


def test_the_idempotency_key_is_stable_and_short(db: Session) -> None:
    row = event_row(db)
    key = delivery.recipient_key("Owner@Example.com ")
    assert key == delivery.recipient_key("owner@example.com")
    first = delivery.idempotency_key(row, "reset_link", key)
    assert first == delivery.idempotency_key(row, "reset_link", key)
    assert len(first) <= 256 and "owner" not in first
    assert first != delivery.idempotency_key(row, "setup_link", key)


def test_a_retry_reaches_only_the_people_not_yet_reached(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    row = event_row(db)
    sent: list[tuple[str, str]] = []
    fail_once = {"b@example.com": True}

    class Flaky:
        name = "resend"

        def send(self, outgoing: OutgoingEmail) -> str:
            if fail_once.pop(outgoing.to, False):
                raise RetryableEmailError("Resend answered 500 (application_error)")
            sent.append((outgoing.to, outgoing.idempotency_key))
            return "id"

    monkeypatch.setattr(delivery, "get_transport", Flaky)
    people = [(a, _rendered) for a in ("a@example.com", "b@example.com", "c@example.com")]
    with pytest.raises(RetryableEmailError):
        delivery.send_to_each(row, "lead_alert", people, sender_name="Empire CMS", reply_to=None)
    assert [to for to, _ in sent] == ["a@example.com", "c@example.com"]
    assert (
        delivery.send_to_each(row, "lead_alert", people, sender_name="Empire CMS", reply_to=None)
        == 1
    )
    assert [to for to, _ in sent] == ["a@example.com", "c@example.com", "b@example.com"]
    assert len({key for _, key in sent}) == 3
    assert len(db.scalars(select(EmailMessage)).all()) == 3


def _rendered() -> Rendered:
    return Rendered(subject="s", text="t", html="<p>h</p>")


def test_a_permanent_failure_still_tries_everyone_then_goes_dead(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    sent: list[str] = []

    class Refusing:
        name = "resend"

        def send(self, outgoing: OutgoingEmail) -> str:
            if outgoing.to == "bad@example.com":
                raise PermanentEmailError("Resend answered 422 (validation_error)")
            sent.append(outgoing.to)
            return "id"

    monkeypatch.setattr(delivery, "get_transport", Refusing)
    row = event_row(db)
    people = [(a, _rendered) for a in ("bad@example.com", "ok@example.com")]
    with pytest.raises(PermanentEmailError):
        delivery.send_to_each(row, "lead_alert", people, sender_name="Empire CMS", reply_to=None)
    assert sent == ["ok@example.com"]


def test_a_permanent_failure_marks_the_event_dead_at_once(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(_db: Session, _event: OutboxEvent) -> None:
        raise PermanentEmailError("Resend answered 422 (validation_error)")

    monkeypatch.setitem(handlers._registry, "test.permanent", [refuse])
    emit(db, type_="test.permanent", aggregate_type="user", aggregate_id="x")
    db.commit()
    drain()
    db.expire_all()
    row = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "test.permanent")).one()
    assert row.status == "dead" and row.attempts == 1
    assert row.last_error == "PermanentEmailError: Resend answered 422 (validation_error)"


# --- The dev mailbox -----------------------------------------------------------------------


def test_the_dev_transport_keeps_the_first_message_for_a_key(tmp_path: Path) -> None:
    dev = DevTransport(tmp_path)
    first = dev.send(message(subject="First", links=("https://x/admin/reset#token=a",)))
    again = dev.send(message(subject="Second"))
    assert first == again
    [stored] = dev.messages()
    assert stored.subject == "First" and stored.links == ("https://x/admin/reset#token=a",)
    assert dev.latest("OWNER@example.com") == stored
    assert dev.latest("someone@example.com") is None


def test_the_dev_mailbox_route_answers_in_test(owner: SignedIn, client: TestClient) -> None:
    r = owner.client.post(
        "/api/v1/admin/users",
        json={"email": "new@example.com", "name": "New Person", "role": "sales"},
        headers=owner.headers(),
    )
    assert r.status_code == 201
    latest = client.get("/api/v1/dev-mail/latest", params={"to": "new@example.com"})
    assert latest.status_code == 200
    body = latest.json()
    assert body["template"] == "setup_link" and body["subject"].startswith("Set up your")
    assert body["links"][0].startswith(get_settings().site_url.rstrip("/") + "/admin/setup#token=")
    assert latest.headers["cache-control"] == "no-store"
    assert client.get("/api/v1/dev-mail/latest", params={"to": "x@example.com"}).status_code == 404


def _paths(app: FastAPI) -> set[str]:
    return set(app.openapi()["paths"])


def test_the_dev_mailbox_exists_only_with_the_dev_transport_in_dev_or_test() -> None:
    base = get_settings().model_dump()
    assert "/api/v1/dev-mail/latest" in _paths(create_app(Settings(**{**base, "app_env": "test"})))
    assert "/api/v1/dev-mail/latest" in _paths(
        create_app(Settings(**{**base, "app_env": "development"}))
    )
    with_key = Settings(**{**base, "email_api_key": SecretStr(KEY), "email_from": "a@example.com"})
    assert with_key.email_transport_kind == "resend"
    resend_app = create_app(with_key)
    assert "/api/v1/dev-mail/latest" not in _paths(resend_app)
    with TestClient(resend_app, base_url="https://testserver") as c:
        assert c.get("/api/v1/dev-mail/latest", params={"to": "a@example.com"}).status_code == 404
    production = Settings(
        app_env="production",
        session_secret=SecretStr("s" * 48),
        internal_api_key=SecretStr("i" * 48),
        ip_hash_salt=SecretStr("p" * 48),
        data_encryption_key=SecretStr(Fernet.generate_key().decode()),
        edge_proxy_key=SecretStr("e" * 48),
        cloudinary_url=SecretStr("cloudinary://key:not-a-secret@demo"),
        email_api_key=SecretStr(KEY),
        email_from="alerts@example.com",
    )
    assert "/api/v1/dev-mail/latest" not in _paths(create_app(production))


# --- Configuration -------------------------------------------------------------------------


def _production(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "staging",
        "session_secret": SecretStr("s" * 48),
        "internal_api_key": SecretStr("i" * 48),
        "ip_hash_salt": SecretStr("p" * 48),
        "data_encryption_key": SecretStr(Fernet.generate_key().decode()),
        "edge_proxy_key": SecretStr("e" * 48),
        "cloudinary_url": SecretStr("cloudinary://key:not-a-secret@demo"),
        "email_api_key": SecretStr(KEY),
        "email_from": "alerts@example.com",
    }
    return Settings(**{**values, **overrides})


def test_staging_and_production_need_the_key_and_the_sender() -> None:
    assert _production().email_transport_kind == "resend"
    with pytest.raises(ValueError, match="EMAIL_API_KEY must be set") as no_key:
        _production(email_api_key=SecretStr(""))
    with pytest.raises(ValueError, match="EMAIL_FROM must be set"):
        _production(email_from="")
    with pytest.raises(ValueError, match="EMAIL_TRANSPORT=dev is for development"):
        _production(email_transport="dev")
    for app_env in ("staging", "production"):
        with pytest.raises(ValueError, match="EMAIL_API_KEY"):
            _production(app_env=app_env, email_api_key=SecretStr(""))
    assert KEY not in str(no_key.value)


def test_the_sender_must_be_a_plain_address() -> None:
    with pytest.raises(ValueError, match="EMAIL_FROM must be a plain address"):
        Settings(app_env="development", email_from="Empire <alerts@example.com>")
    with pytest.raises(ValueError, match="EMAIL_TRANSPORT=resend needs EMAIL_API_KEY"):
        Settings(app_env="development", email_transport="resend")
    assert Settings(app_env="development", email_transport="").email_transport_kind == "dev"


def test_the_key_is_never_in_a_configuration_error() -> None:
    with pytest.raises(ValueError) as raised:
        _production(email_from="", email_api_key=SecretStr("re_secret_value_123"))
    assert "re_secret_value_123" not in str(raised.value)


def test_transport_choice_follows_the_settings(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("MAIL_DEV_DIR", str(tmp_path))
    get_settings.cache_clear()
    transport.get_transport.cache_clear()
    try:
        assert isinstance(transport.get_transport(), DevTransport)
        monkeypatch.setenv("EMAIL_API_KEY", KEY)
        get_settings.cache_clear()
        transport.get_transport.cache_clear()
        assert isinstance(transport.get_transport(), ResendTransport)
    finally:
        monkeypatch.delenv("EMAIL_API_KEY", raising=False)
        get_settings.cache_clear()
        transport.get_transport.cache_clear()
