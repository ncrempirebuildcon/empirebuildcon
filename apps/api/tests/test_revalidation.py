"""Tests for outbox web revalidation handler and signature (Phase 5 Task 5.2)."""

from __future__ import annotations

import json
import uuid

import httpx
import pytest
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


def test_revalidation_maps_configuration_and_updates(db: Session) -> None:
    cfg_event = OutboxEvent(
        type="configuration.changed",
        aggregate_type="configuration",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "aurum-heights"},
    )
    tags = tags_for_event(db, cfg_event)
    assert tags == ["project:aurum-heights", "properties"]

    update_event = OutboxEvent(
        type="construction_update.published",
        aggregate_type="construction_update",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "aurum-heights"},
    )
    assert tags_for_event(db, update_event) == ["project:aurum-heights"]


def test_revalidation_maps_content_and_site_events(db: Session) -> None:
    page_event = OutboxEvent(
        type="page.published",
        aggregate_type="page",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "about"},
    )
    assert tags_for_event(db, page_event) == ["page:about", "site"]

    post_event = OutboxEvent(
        type="post.published",
        aggregate_type="post",
        aggregate_id=str(uuid.uuid4()),
        payload={"slug": "market-trends-2026"},
    )
    assert tags_for_event(db, post_event) == ["post:market-trends-2026", "posts"]

    faq_event = OutboxEvent(
        type="faq.changed",
        aggregate_type="faq",
        aggregate_id=str(uuid.uuid4()),
        payload={},
    )
    assert tags_for_event(db, faq_event) == ["faqs", "site"]

    testimonial_event = OutboxEvent(
        type="testimonial.changed",
        aggregate_type="testimonial",
        aggregate_id=str(uuid.uuid4()),
        payload={},
    )
    assert tags_for_event(db, testimonial_event) == ["site", "testimonials"]

    redirect_event = OutboxEvent(
        type="redirect.changed",
        aggregate_type="redirect",
        aggregate_id=str(uuid.uuid4()),
        payload={},
    )
    assert tags_for_event(db, redirect_event) == ["redirects", "site"]

    settings_event = OutboxEvent(
        type="settings.updated",
        aggregate_type="settings",
        aggregate_id="global",
        payload={},
    )
    assert tags_for_event(db, settings_event) == ["site"]


def test_revalidation_signature_computation() -> None:
    secret = "test-secret-at-least-32-chars-long-here"
    ts = 1700000000000
    body = b'{"tags":["project:aurum","site"]}'
    sig1 = compute_signature(secret, ts, body)
    sig2 = compute_signature(secret, ts, body)
    assert sig1 == sig2
    assert len(sig1) == 64

    # Timestamp change produces different signature
    assert compute_signature(secret, ts + 1, body) != sig1
    # Body change produces different signature
    assert compute_signature(secret, ts, b'{"tags":["site"]}') != sig1


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
