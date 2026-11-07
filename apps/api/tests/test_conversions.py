"""Server-side conversions (task 6.2, D-057): off by default, the consent gate, what is sent."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.integrations.conversions import google, handlers, hashing, meta
from empire_api.platform.models import OutboxEvent
from leads_support import enquiry, given, lead_by_reference, submit_ok

PIXEL = "123456789012345"
UA = "Mozilla/5.0 (Linux; Android 14) Test"


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class FakeMeta:
    def __init__(self) -> None:
        self.sent: list[tuple[str, dict[str, Any]]] = []

    def send(self, pixel_id: str, body: dict[str, Any]) -> None:
        self.sent.append((pixel_id, body))


class FakeGoogle:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, body: dict[str, Any]) -> None:
        self.sent.append(body)


@pytest.fixture
def platforms(monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FakeMeta, FakeGoogle]]:
    """Both platforms configured, consent version 1 approved, the real clients replaced."""
    env = {
        "CONVERSIONS_CONSENT_MIN_VERSION": "1",
        "META_CAPI_ACCESS_TOKEN": "meta-test-token",
        "GOOGLE_DM_CLIENT_ID": "client-id",
        "GOOGLE_DM_CLIENT_SECRET": "client-secret",
        "GOOGLE_DM_REFRESH_TOKEN": "refresh-token",
        "GOOGLE_ADS_CUSTOMER_ID": "123-456-7890",
        "GOOGLE_ADS_CONVERSION_ACTION_ID": "987654",
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    fake_meta, fake_google = FakeMeta(), FakeGoogle()
    monkeypatch.setattr(handlers, "_meta_pixel", lambda db: PIXEL)
    monkeypatch.setattr(handlers, "meta_client", lambda settings: fake_meta)
    monkeypatch.setattr(handlers, "google_client", lambda settings: fake_google)
    yield fake_meta, fake_google
    monkeypatch.undo()  # the environment back before the cache is cleared
    get_settings.cache_clear()


def marketing_enquiry(texts: dict[str, Any], n: int = 1, **fields: Any) -> dict[str, Any]:
    return enquiry(
        texts,
        n,
        email="Buyer.One+ads@Gmail.com",
        message="Please call after 6 pm",
        marketing_consent=given(texts["marketing"]),
        click_ids={"gclid": "GCLID-123", "fbclid": "FBCLID-456"},
        **fields,
    )


def post(client: TestClient, body: dict[str, Any]) -> str:
    response = client.post("/api/v1/public/leads", json=body, headers={"user-agent": UA})
    assert response.status_code == 201, response.text
    return str(response.json()["reference"])


def send_events(db: Session) -> list[OutboxEvent]:
    db.expire_all()
    return list(db.scalars(select(OutboxEvent).where(OutboxEvent.type == "conversion.send")))


# ── Off by default ─────────────────────────────────────────────────────────────────────────


def test_nothing_is_queued_without_configuration(
    client: TestClient, db: Session, texts: dict[str, Any]
) -> None:
    post(client, marketing_enquiry(texts))
    assert send_events(db) == []


def test_nothing_is_queued_without_the_approved_consent_version(
    client: TestClient, db: Session, texts: dict[str, Any], platforms: Any, monkeypatch: Any
) -> None:
    monkeypatch.delenv("CONVERSIONS_CONSENT_MIN_VERSION")
    get_settings.cache_clear()
    post(client, marketing_enquiry(texts))
    assert send_events(db) == []


# ── The consent gate ───────────────────────────────────────────────────────────────────────


def test_a_lead_without_marketing_consent_is_never_reported(
    client: TestClient, db: Session, texts: dict[str, Any], platforms: tuple[FakeMeta, FakeGoogle]
) -> None:
    submit_ok(client, enquiry(texts, email="a@example.com", click_ids={"gclid": "G1"}))
    assert send_events(db) == []
    assert platforms[0].sent == [] and platforms[1].sent == []


def test_marketing_consent_on_an_older_version_is_not_enough(
    client: TestClient,
    db: Session,
    texts: dict[str, Any],
    platforms: tuple[FakeMeta, FakeGoogle],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONVERSIONS_CONSENT_MIN_VERSION", "2")  # the reviewer approved v2
    get_settings.cache_clear()
    post(client, marketing_enquiry(texts))  # the visitor saw v1
    assert send_events(db) == []


def test_a_duplicate_is_not_reported_twice(
    client: TestClient, db: Session, texts: dict[str, Any], platforms: tuple[FakeMeta, FakeGoogle]
) -> None:
    post(client, marketing_enquiry(texts))
    post(client, marketing_enquiry(texts))  # same phone, same (no) project, within 24 h
    assert len(platforms[0].sent) == 1
    assert len(platforms[1].sent) == 1


# ── What is sent ───────────────────────────────────────────────────────────────────────────


def test_a_consented_lead_reaches_both_platforms_with_hashes_only(
    client: TestClient, db: Session, texts: dict[str, Any], platforms: tuple[FakeMeta, FakeGoogle]
) -> None:
    fake_meta, fake_google = platforms
    reference = post(client, marketing_enquiry(texts))
    lead = lead_by_reference(db, reference)

    [(pixel, meta_body)] = fake_meta.sent
    assert pixel == PIXEL
    [event] = meta_body["data"]
    assert event["event_name"] == "Lead"
    assert event["event_id"] == str(lead.id)
    assert event["action_source"] == "website"
    assert event["event_source_url"] == "https://empirebuildcon.com/contact"
    assert event["user_data"]["client_user_agent"] == UA
    assert event["user_data"]["ph"] == [sha("919876500001")]
    assert event["user_data"]["em"] == [sha("buyer.one+ads@gmail.com")]
    assert event["user_data"]["fbc"].startswith("fb.1.") and event["user_data"]["fbc"].endswith(
        ".FBCLID-456"
    )

    [google_body] = fake_google.sent
    [destination] = google_body["destinations"]
    assert destination["operatingAccount"] == {
        "accountType": "GOOGLE_ADS",
        "accountId": "1234567890",
    }
    assert destination["productDestinationId"] == "987654"
    [g_event] = google_body["events"]
    assert g_event["transactionId"] == str(lead.id)
    assert g_event["adIdentifiers"] == {"gclid": "GCLID-123"}
    assert {"emailAddress": sha("buyerone@gmail.com")} in g_event["userData"]["userIdentifiers"]
    assert {"phoneNumber": sha("+919876500001")} in g_event["userData"]["userIdentifiers"]
    assert google_body["encoding"] == "HEX"

    # COMPLIANCE: no name, message or raw contact detail in anything sent.
    sent = json.dumps([meta_body, google_body])
    for private in ("Visitor 1", "Please call", "9876500001", "Gmail.com", "Buyer.One"):
        assert private not in sent


def test_a_lead_erased_before_sending_is_skipped(
    client: TestClient,
    db: Session,
    texts: dict[str, Any],
    platforms: tuple[FakeMeta, FakeGoogle],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reference = post(client, marketing_enquiry(texts))
    lead = lead_by_reference(db, reference)
    # Erased after the event was queued: a later send (a retry, say) must send nothing.
    lead.erased_at = lead.created_at
    db.commit()
    fake_meta, _ = platforms
    before = len(fake_meta.sent)
    event = OutboxEvent(
        type="conversion.send",
        aggregate_type="lead",
        aggregate_id=str(lead.id),
        payload={"platform": "meta", "lead_id": str(lead.id), "user_agent": UA},
    )
    handlers.send_conversion(db, event)
    assert len(fake_meta.sent) == before


def test_without_a_user_agent_meta_gets_nothing(
    client: TestClient, db: Session, texts: dict[str, Any], platforms: tuple[FakeMeta, FakeGoogle]
) -> None:
    response = client.post(
        "/api/v1/public/leads", json=marketing_enquiry(texts), headers={"user-agent": ""}
    )
    assert response.status_code == 201
    fake_meta, fake_google = platforms
    assert fake_meta.sent == []
    assert len(fake_google.sent) == 1


# ── Clients: errors and secrets ────────────────────────────────────────────────────────────


def _transport(status: int, body: dict[str, Any]) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


def test_meta_client_keeps_the_token_out_of_the_url_and_errors() -> None:
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(400, json={"error": {"code": 100, "message": "secret-token bad"}})

    client = meta.MetaClient(
        "secret-token",
        "v26.0",
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(meta.ConversionRejectedError) as raised:
        client.send(PIXEL, {"data": []})
    assert str(raised.value) == "meta_100"
    assert "secret-token" not in str(seen[0].url)
    assert json.loads(seen[0].content)["access_token"] == "secret-token"
    assert "secret-token" not in repr(client)


def test_meta_server_errors_are_retried() -> None:
    client = meta.MetaClient(
        "t", "v26.0", client_factory=lambda: httpx.Client(transport=_transport(503, {}))
    )
    with pytest.raises(meta.ConversionRetryableError):
        client.send(PIXEL, {"data": []})


def test_google_client_gets_a_token_then_ingests() -> None:
    calls: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "ya29.test"})
        return httpx.Response(200, json={"requestId": "r1"})

    client = google.GoogleClient(
        "id",
        "client-secret-xyz",
        "refresh-xyz",
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    client.send({"events": []})
    assert [c.url.host for c in calls] == ["oauth2.googleapis.com", "datamanager.googleapis.com"]
    assert calls[1].headers["authorization"] == "Bearer ya29.test"
    assert "client-secret-xyz" not in repr(client) and "refresh-xyz" not in repr(client)
    assert b"client-secret-xyz" in calls[0].content  # only to the token endpoint
    assert b"client-secret-xyz" not in calls[1].content


def test_google_refusal_is_final_and_names_a_code_only() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.host == "oauth2.googleapis.com":
            return httpx.Response(200, json={"access_token": "ya29.test"})
        return httpx.Response(400, json={"error": {"status": "INVALID_ARGUMENT", "message": "x"}})

    client = google.GoogleClient(
        "id",
        "secret",
        "refresh",
        client_factory=lambda: httpx.Client(transport=httpx.MockTransport(respond)),
    )
    with pytest.raises(meta.ConversionRejectedError) as raised:
        client.send({"events": []})
    assert str(raised.value) == "google_INVALID_ARGUMENT"


def test_a_refusal_marks_the_send_event_dead(
    client: TestClient,
    db: Session,
    texts: dict[str, Any],
    platforms: tuple[FakeMeta, FakeGoogle],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Refusing(FakeMeta):
        def send(self, pixel_id: str, body: dict[str, Any]) -> None:
            raise meta.ConversionRejectedError("meta_100")

    monkeypatch.setattr(handlers, "meta_client", lambda settings: Refusing())
    post(client, marketing_enquiry(texts))
    statuses = {e.payload["platform"]: e.status for e in send_events(db)}
    assert statuses == {"meta": "dead", "google": "delivered"}


# ── Hashing rules ──────────────────────────────────────────────────────────────────────────


def test_google_email_rules() -> None:
    assert hashing.google_email(" John.Smith+promo@GoogleMail.com ") == sha(
        "johnsmith@googlemail.com"
    )
    assert hashing.google_email("John.Smith+promo@example.com") == sha(
        "john.smith+promo@example.com"
    )
    assert hashing.google_email("not-an-email") is None


def test_phone_rules() -> None:
    assert hashing.google_phone("+919876543210") == sha("+919876543210")
    assert hashing.meta_phone("+919876543210") == sha("919876543210")
    assert hashing.google_phone("9876543210") is None


# ── Review round (D-057): more gates, erasure, Meta's temporary errors ─────────────────────


def test_no_user_agent_is_kept_for_a_lead_without_marketing_consent(
    client: TestClient, db: Session, texts: dict[str, Any]
) -> None:
    post(client, enquiry(texts, email="a@example.com"))
    db.expire_all()
    [created] = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "lead.created")).all()
    assert created.payload["user_agent"] is None


def test_a_manual_lead_is_never_reported(
    owner: Any, db: Session, platforms: tuple[FakeMeta, FakeGoogle]
) -> None:
    body = {"name": "Walk-in", "phone": "98111 00001", "source": "phone", "consent_note": "Verbal"}
    response = owner.client.post("/api/v1/admin/leads", json=body, headers=owner.headers())
    assert response.status_code == 201, response.text
    assert send_events(db) == []


def test_spam_and_sample_leads_are_not_reported(
    client: TestClient, db: Session, texts: dict[str, Any], platforms: tuple[FakeMeta, FakeGoogle]
) -> None:
    reference = post(client, marketing_enquiry(texts))
    lead = lead_by_reference(db, reference)
    settings = get_settings()
    assert handlers.may_report(db, lead, settings)
    lead.is_spam = True
    assert not handlers.may_report(db, lead, settings)
    lead.is_spam, lead.is_sample = False, True
    assert not handlers.may_report(db, lead, settings)
    db.rollback()


def test_erasure_scrubs_a_queued_send_and_it_is_then_skipped(
    owner: Any,
    client: TestClient,
    db: Session,
    texts: dict[str, Any],
    platforms: tuple[FakeMeta, FakeGoogle],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Busy(FakeMeta):
        def send(self, pixel_id: str, body: dict[str, Any]) -> None:
            raise meta.ConversionRetryableError("meta_17")  # Meta busy: stays queued

    busy = Busy()
    monkeypatch.setattr(handlers, "meta_client", lambda settings: busy)
    reference = post(client, marketing_enquiry(texts))
    lead_id = str(lead_by_reference(db, reference).id)
    [queued] = [e for e in send_events(db) if e.payload.get("platform") == "meta"]
    assert queued.status == "pending" and queued.payload["user_agent"] == UA

    response = owner.client.delete(f"/api/v1/admin/leads/{lead_id}", headers=owner.headers())
    assert response.status_code == 204, response.text
    [scrubbed] = [e for e in send_events(db) if e.id == queued.id]
    assert scrubbed.payload.get("erased") is True and "user_agent" not in scrubbed.payload

    fake = FakeMeta()
    monkeypatch.setattr(handlers, "meta_client", lambda settings: fake)
    handlers.send_conversion(db, scrubbed)
    assert fake.sent == []


@pytest.mark.parametrize("code", [17, 613, 80004])
def test_meta_rate_limits_are_retried_not_dead(code: int) -> None:
    body = {"error": {"code": code, "message": "slow down"}}
    client = meta.MetaClient(
        "t", "v26.0", client_factory=lambda: httpx.Client(transport=_transport(400, body))
    )
    with pytest.raises(meta.ConversionRetryableError):
        client.send(PIXEL, {"data": []})


def test_meta_is_transient_flag_is_retried() -> None:
    body = {"error": {"code": 100, "is_transient": True}}
    client = meta.MetaClient(
        "t", "v26.0", client_factory=lambda: httpx.Client(transport=_transport(400, body))
    )
    with pytest.raises(meta.ConversionRetryableError):
        client.send(PIXEL, {"data": []})


def _ads_lead(**fields: Any) -> meta.LeadForAds:
    base: dict[str, Any] = {
        "lead_id": "01a1b0af-0000-7000-8000-000000000001",
        "created_at": datetime(2026, 11, 7, 10, 30, tzinfo=UTC),
        "phone_e164": "+919876543210",
        "email": None,
        "page_url": "https://empirebuildcon.com/contact",
        "gclid": None,
        "gbraid": None,
        "wbraid": None,
        "fbclid": None,
        "user_agent": UA,
    }
    base.update(fields)
    return meta.LeadForAds(**base)


def test_meta_needs_a_page_url() -> None:
    assert meta.event_body(_ads_lead(page_url=None)) is None
    assert meta.event_body(_ads_lead()) is not None


def test_google_sends_one_click_id_gclid_first() -> None:
    def ids(**clicks: str) -> Any:
        body = google.event_body(
            _ads_lead(**clicks),
            customer_id="1234567890",
            login_customer_id="",
            conversion_action_id="1",
            validate_only=True,
        )
        assert body is not None
        return body["events"][0].get("adIdentifiers")

    assert ids(gclid="G", gbraid="B", wbraid="W") == {"gclid": "G"}
    assert ids(gbraid="B", wbraid="W") == {"gbraid": "B"}
    assert ids() is None
