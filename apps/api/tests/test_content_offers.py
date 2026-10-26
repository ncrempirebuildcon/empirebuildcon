"""Offers: placement, dates, button and terms rules, no pressure wording, the computed state,
list filters, delete only before going live, and permissions (`offers.manage`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI

from conftest import SignedIn
from content_support import OFFERS, block, create_offer, create_page, offer_body, put_blocks, soon
from media_support import document, photo, signed_as
from projects_support import create_project, ok


def post(signed: SignedIn, **fields: object) -> object:
    return signed.client.post(OFFERS, json=offer_body(**fields), headers=signed.headers())


def field_of(response: object) -> str:
    assert response.status_code == 422, response.text  # type: ignore[attr-defined]
    return str(response.json()["errors"][0]["field"])  # type: ignore[attr-defined]


@pytest.mark.parametrize(
    ("fields", "field"),
    [
        ({"starts_at": soon(2), "ends_at": soon(1)}, "ends_at"),
        ({"cta_label": "See offer"}, "cta_url"),
        ({"cta_url": "/offers"}, "cta_label"),
        ({"cta_label": "Go", "cta_url": "javascript:alert(1)"}, "cta_url"),
        ({"placement": "project"}, "project_id"),
        ({"placement": "popup"}, "placement"),
        ({"body": "Hurry, only 3 left at this price!", "terms": "T&C apply"}, "body"),
        ({"body": "Last few homes in Tower B"}, "body"),
        ({"body": "Flat 5% discount on booking"}, "terms"),
        ({"title": "Save ₹2 lakh this Diwali"}, "terms"),
        ({"body": "<b>Big</b> offer"}, "body"),
        ({"starts_at": "2026-11-01T00:00:00"}, "starts_at"),
        ({"countdown_to": soon(3)}, "countdown_to"),
    ],
)
def test_offer_rules(owner: SignedIn, fields: dict[str, object], field: str) -> None:
    assert field_of(post(owner, **fields)).startswith(field)


def test_terms_line_or_link_satisfies_the_price_rule(owner: SignedIn) -> None:
    ok(
        post(
            owner, body="Flat 5% discount on booking", terms="Valid on bookings till 30 Nov 2026."
        ),
        201,
    )
    ok(post(owner, body="Stamp duty waiver", terms_url="/legal/offer-terms"), 201)
    ok(post(owner, body="Visit our sample flat this weekend"), 201)


def test_images_and_projects_are_checked(owner: SignedIn) -> None:
    assert field_of(post(owner, image_media_id=document(owner)["id"])) == "image_media_id"
    project = create_project(owner)
    made = ok(
        post(
            owner, placement="project", project_id=project["id"], image_media_id=photo(owner)["id"]
        ),
        201,
    )
    assert made["project_name"] == "Aurum Heights" and made["image"]["kind"] == "image"


def test_states(owner: SignedIn) -> None:
    now = datetime.now(UTC)
    assert create_offer(owner)["state"] == "inactive"
    assert create_offer(owner, is_active=True)["state"] == "live"
    assert create_offer(owner, is_active=True, starts_at=soon(1))["state"] == "scheduled"
    past_start = (now - timedelta(days=3)).isoformat()
    past_end = (now - timedelta(days=1)).isoformat()
    ended = create_offer(owner, is_active=True, starts_at=past_start, ends_at=past_end)
    assert ended["state"] == "ended"
    by_state = {
        state: ok(owner.client.get(OFFERS, params={"state": state}))["meta"]["total"]
        for state in ("inactive", "live", "scheduled", "ended")
    }
    assert by_state == {"inactive": 1, "live": 1, "scheduled": 1, "ended": 1}
    today = ok(owner.client.get(OFFERS, params={"active_on": now.date().isoformat()}))
    assert today["meta"]["total"] == 1  # the live one without dates


def test_patch_rules_use_merged_values(owner: SignedIn) -> None:
    offer = create_offer(owner, starts_at=soon(1), ends_at=soon(5))
    refused = owner.client.patch(
        f"{OFFERS}/{offer['id']}", json={"ends_at": soon(0.5)}, headers=owner.headers()
    )
    assert field_of(refused) == "ends_at"
    moved = owner.client.patch(
        f"{OFFERS}/{offer['id']}", json={"priority": 10}, headers=owner.headers()
    )
    assert ok(moved)["priority"] == 10


def test_delete_only_before_going_live_and_not_while_a_block_shows_it(owner: SignedIn) -> None:
    draft = create_offer(owner)
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("offer_banner", {"offer_id": draft["id"]})]))
    shown = owner.client.delete(f"{OFFERS}/{draft['id']}", headers=owner.headers())
    assert shown.status_code == 409 and "block" in shown.json()["detail"]
    ok(put_blocks(owner, page["id"], []))
    assert (
        owner.client.delete(f"{OFFERS}/{draft['id']}", headers=owner.headers()).status_code == 204
    )
    live = create_offer(owner, is_active=True)
    kept = owner.client.delete(f"{OFFERS}/{live['id']}", headers=owner.headers())
    assert kept.status_code == 409 and "for the record" in kept.json()["detail"]


def test_offers_need_offers_manage(app: FastAPI) -> None:
    editor = signed_as(app, "content_editor")
    assert editor.client.get(OFFERS).status_code == 403
    assert post(editor).status_code == 403  # type: ignore[attr-defined]
    marketing = signed_as(app, "marketing")
    assert ok(post(marketing), 201)["state"] == "inactive"
