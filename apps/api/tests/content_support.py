"""Helpers for the content and SEO tests: create pages, posts, FAQs, offers, testimonials and
redirects through the API, and build valid blocks of every type."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from conftest import SignedIn
from empire_api.content.seed import seed_pages
from empire_api.db import get_sessionmaker
from empire_api.timeutil import today_ist
from media_support import MP4, confirm, direct_reply
from projects_support import ok

ADMIN = "/api/v1/admin"
PAGES = f"{ADMIN}/pages"
POSTS = f"{ADMIN}/posts"
FAQS = f"{ADMIN}/faqs"
OFFERS = f"{ADMIN}/offers"
TESTIMONIALS = f"{ADMIN}/testimonials"
REDIRECTS = f"{ADMIN}/redirects"


def soon(days: float = 1) -> str:
    return (datetime.now(UTC) + timedelta(days=days)).isoformat()


def later(hours: float) -> datetime:
    """A moment `hours` from now, for running the schedule tick in the future."""
    return datetime.now(UTC) + timedelta(hours=hours)


def seed_site_pages() -> None:
    """The system and legal pages `empire-api seed` adds."""
    with get_sessionmaker()() as db:
        seed_pages(db)
        db.commit()


def page_by_slug(signed: SignedIn, slug: str) -> Any:
    rows = ok(signed.client.get(PAGES, params={"q": slug, "per_page": 100}))["items"]
    return next(row for row in rows if row["slug"] == slug)


def get_page(signed: SignedIn, page_id: str) -> Any:
    return ok(signed.client.get(f"{PAGES}/{page_id}"))


def create_page(signed: SignedIn, title: str = "About us", **fields: Any) -> Any:
    body = {"title": title, "kind": "standard", **fields}
    return ok(signed.client.post(PAGES, json=body, headers=signed.headers()), 201)


def patch_page(signed: SignedIn, page_id: str, body: dict[str, Any]) -> Any:
    return signed.client.patch(f"{PAGES}/{page_id}", json=body, headers=signed.headers())


def put_blocks(signed: SignedIn, page_id: str, blocks: list[dict[str, Any]]) -> Any:
    return signed.client.put(
        f"{PAGES}/{page_id}/blocks", json={"blocks": blocks}, headers=signed.headers()
    )


def publish_page(signed: SignedIn, page_id: str) -> Any:
    return signed.client.post(f"{PAGES}/{page_id}/publish", headers=signed.headers())


def unpublish_page(signed: SignedIn, page_id: str) -> Any:
    return signed.client.post(f"{PAGES}/{page_id}/unpublish", headers=signed.headers())


def create_post(signed: SignedIn, title: str = "How to check a project", **fields: Any) -> Any:
    body = {"title": title, "body": "*Step one*: open up-rera.in.", **fields}
    return ok(signed.client.post(POSTS, json=body, headers=signed.headers()), 201)


def create_faq(signed: SignedIn, question: str = "Is parking included?", **fields: Any) -> Any:
    body = {"question": question, "answer": "Yes, one covered space.", **fields}
    return ok(signed.client.post(FAQS, json=body, headers=signed.headers()), 201)


def offer_body(**fields: Any) -> dict[str, Any]:
    return {"title": "Festive offer", "placement": "banner", **fields}


def create_offer(signed: SignedIn, **fields: Any) -> Any:
    return ok(signed.client.post(OFFERS, json=offer_body(**fields), headers=signed.headers()), 201)


def buyer_quote(**fields: Any) -> dict[str, Any]:
    return {
        "person_name": "R. Sharma",
        "quote": "Handover was on the date we were given.",
        "source": "Written feedback form, 2 Mar 2026",
        **fields,
    }


def create_testimonial(signed: SignedIn, **fields: Any) -> Any:
    body = buyer_quote(**fields)
    return ok(signed.client.post(TESTIMONIALS, json=body, headers=signed.headers()), 201)


def create_redirect(signed: SignedIn, from_path: str, to_path: str, **fields: Any) -> Any:
    body = {"from_path": from_path, "to_path": to_path, **fields}
    return signed.client.post(REDIRECTS, json=body, headers=signed.headers())


def list_redirects(signed: SignedIn) -> list[dict[str, Any]]:
    return list(ok(signed.client.get(REDIRECTS, params={"per_page": 100}))["items"])


def video(signed: SignedIn) -> Any:
    """A short MP4 through the fake store's direct upload; returns the Media JSON."""
    _, reply = direct_reply(signed, "video", "tour.mp4", MP4, "video/mp4")
    return ok(confirm(signed, reply), 201)


def block(type_: str, data: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"type": type_, "data": data if data is not None else {}, **extra}


def every_block(
    image_id: str, project_id: str, city_id: str, faq_id: str, testimonial_id: str, offer_id: str
) -> list[dict[str, Any]]:
    """One valid block of each of the 17 types, in the order of the contract's enum."""
    today = today_ist().isoformat()
    return [
        block(
            "hero",
            {
                "heading": "Homes that deliver happiness",
                "subheading": "[Intro text]",
                "image_id": image_id,
                "cta": {"label": "Explore projects", "href": "/projects"},
            },
        ),
        block("rich_text", {"body": "*Bold* and _italic_\n- a bullet\n  - nested"}),
        block("image", {"image_id": image_id, "caption": "Artist's impression"}),
        block("gallery", {"image_ids": [image_id]}),
        block("video", {"url": "https://youtu.be/dQw4w9WgXcQ"}),
        block("project_grid", {"status": "ongoing", "city_id": city_id, "limit": 6}),
        block("property_grid", {"featured_only": True, "limit": 3}),
        block("cta", {"label": "Book a site visit", "href": "https://empirebuildcon.com/contact"}),
        block("lead_form", {"source": "project_form", "project_id": project_id}),
        block("faq_list", {"faq_ids": [faq_id]}),
        block(
            "stats",
            {
                "items": [
                    {
                        "value": "[n]",
                        "label": "homes handed over",
                        "source": "Possession register",
                        "as_of": today,
                    }
                ]
            },
        ),
        block("testimonials", {"testimonial_ids": [testimonial_id]}),
        block("offer_banner", {"offer_id": offer_id}),
        block("map", {"project_id": project_id}),
        block("steps", {"items": [{"title": "Visit"}, {"title": "Book", "text": "[How]"}]}),
        block("columns", {"columns": [{"body": "Left"}, {"body": "Right"}]}),
        block("divider"),
    ]


def random_id() -> str:
    return str(uuid.uuid4())
