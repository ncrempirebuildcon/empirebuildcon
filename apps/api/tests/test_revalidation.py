"""Tests for outbox web revalidation handler and signature (Phase 5 Task 5.2)."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from empire_api.integrations.handlers import handlers_for
from empire_api.integrations.revalidation import (
    REVALIDATION_EVENTS,
    SIGNATURE_HEADER,
    TIMESTAMP_HEADER,
    compute_signature,
    handle_revalidation,
    send_revalidation,
    tags_for_event,
)
from empire_api.platform.models import OutboxEvent


def test_shared_signature_test_vector() -> None:
    """N8: Exact shared test vector between Python API and TypeScript web."""
    shared_secret = "test-secret-shared-vector-48-chars-long-example"
    timestamp = 1793557400000
    body = b'{"tags":["site","projects"]}'
    expected = "1aa1e51fbe111e5f91493b9e78089e7e29e572fbacce7d4d1da1079ec9d6e6ed"

    assert compute_signature(shared_secret, timestamp, body) == expected


def test_revalidation_headers_match_m1_spec() -> None:
    """M1: Signature headers do not use the x-empire- prefix to avoid proxy stripping."""
    assert SIGNATURE_HEADER == "x-revalidate-signature"
    assert TIMESTAMP_HEADER == "x-revalidate-timestamp"


def test_revalidation_events_registered() -> None:
    for event_type in REVALIDATION_EVENTS:
        handlers = handlers_for(event_type)
        assert handle_revalidation in handlers


def test_revalidation_maps_project_events(db: Session) -> None:
    event = OutboxEvent(
        type="project.published",
        aggregate_type="project",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "aurum-heights"},
    )
    tags = tags_for_event(db, event)
    assert "projects" in tags
    assert "project:aurum-heights" in tags
    assert "properties" in tags
    assert "site" in tags
    assert "content" in tags

    # Project updated with previous slug
    event_rename = OutboxEvent(
        type="project.updated",
        aggregate_type="project",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "aurum-villas", "previous_slug": "aurum-heights"},
    )
    tags_rename = tags_for_event(db, event_rename)
    assert "project:aurum-villas" in tags_rename
    assert "project:aurum-heights" in tags_rename
    assert "content" in tags_rename


def test_revalidation_maps_configuration_and_updates(db: Session) -> None:
    # S1: configuration.changed must clear projects as well as properties & project:<slug>
    cfg_event = OutboxEvent(
        type="configuration.changed",
        aggregate_type="configuration",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "aurum-heights"},
    )
    tags = tags_for_event(db, cfg_event)
    assert tags == ["content", "project:aurum-heights", "projects", "properties"]

    update_event = OutboxEvent(
        type="construction_update.published",
        aggregate_type="construction_update",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "aurum-heights"},
    )
    assert tags_for_event(db, update_event) == ["content", "project:aurum-heights"]


def test_revalidation_maps_content_and_site_events_table_driven(db: Session) -> None:
    """S1: Table-driven check of all publish and content events."""
    cases = [
        ("page.published", "page", {"slug": "about"}, ["content", "page:about", "site"]),
        ("post.published", "post", {"slug": "trends"}, ["content", "post:trends", "posts"]),
        (
            "faq.changed",
            "faq",
            {"project_slug": "aurum"},
            ["content", "faqs", "project:aurum", "site"],
        ),
        ("faq.changed", "faq", {}, ["content", "faqs", "site"]),
        ("testimonial.changed", "testimonial", {}, ["content", "site", "testimonials"]),
        ("redirect.changed", "redirect", {}, ["redirects", "site"]),
        ("settings.updated", "settings", {}, ["content", "site"]),
        ("flag.changed", "flag", {"flag": "locale_hi"}, ["content", "site"]),
        (
            "offer.started",
            "offer",
            {"project_slug": "aurum"},
            ["content", "project:aurum", "site"],
        ),
    ]

    for event_type, agg_type, payload, expected_tags in cases:
        event = OutboxEvent(
            type=event_type,
            aggregate_type=agg_type,
            aggregate_id=str(uuid.uuid4()),
            payload=payload,
        )
        assert tags_for_event(db, event) == expected_tags


def test_revalidation_http_post_success() -> None:
    secret = "test-secret-at-least-32-chars-long-here"
    url = "http://web.internal/_internal/revalidate"
    received: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        received.append(request)
        sig = request.headers.get(SIGNATURE_HEADER)
        ts = request.headers.get(TIMESTAMP_HEADER)
        assert sig is not None
        assert ts is not None
        expected_sig = compute_signature(secret, int(ts), request.content)
        assert sig == expected_sig
        body = json.loads(request.content)
        assert body == {"tags": ["project:aurum", "site"]}
        return httpx.Response(200, json={"revalidated": True, "tags": body["tags"]})

    transport = httpx.MockTransport(handler)
    with httpx.Client(transport=transport) as client:
        send_revalidation(
            ["site", "project:aurum"],
            url=url,
            secret=secret,
            client=client,
        )

    assert len(received) == 1


def test_revalidation_retries_on_failure() -> None:
    secret = "test-secret-at-least-32-chars-long-here"
    url = "http://web.internal/_internal/revalidate"

    def fail_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "Internal server error"})

    transport = httpx.MockTransport(fail_handler)
    with (
        httpx.Client(transport=transport) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        send_revalidation(["site"], url=url, secret=secret, client=client)


def test_revalidation_skipped_when_no_url() -> None:
    # Must not raise when URL is empty (e.g. in dev)
    send_revalidation(["site"], url="", secret="some-secret")


def test_revalidation_failure_is_isolated_and_does_not_block_other_handlers(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """M2: A failing web revalidation call must never abort or block other handlers."""

    # Mock send_revalidation to fail loudly
    def mock_fail(*args: object, **kwargs: object) -> None:
        raise httpx.ConnectError("Connection refused by web host")

    monkeypatch.setattr("empire_api.integrations.revalidation.send_revalidation", mock_fail)

    event = OutboxEvent(
        type="media.removed",
        aggregate_type="media",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "aurum"},
    )
    db.add(event)
    db.flush()

    # Calling handle_revalidation must NOT raise
    handle_revalidation(db, event)

    # Instead, an isolated web.revalidate event is queued for independent retry
    queued = db.scalars(select(OutboxEvent).where(OutboxEvent.type == "web.revalidate")).all()
    assert len(queued) == 1
    assert "project:aurum" in queued[0].payload.get("tags", [])
