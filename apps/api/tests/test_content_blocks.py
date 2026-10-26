"""Page blocks: every block type saves and reads back; invalid data, raw HTML and unsafe link
schemes are refused at their exact field; ids are checked against the library (kind and honest
label), projects, cities, FAQs, testimonials and offers; the page's media links follow its
blocks (a library item in use can't be deleted)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    block,
    create_faq,
    create_offer,
    create_page,
    create_testimonial,
    every_block,
    put_blocks,
    random_id,
    video,
)
from empire_api.content.models import PageBlock
from empire_api.media.models import MediaLink
from empire_api.timeutil import today_ist
from media_support import document, photo
from projects_support import create_city, create_project, ok

TYPES = (
    "hero",
    "rich_text",
    "image",
    "gallery",
    "video",
    "project_grid",
    "property_grid",
    "cta",
    "lead_form",
    "faq_list",
    "stats",
    "testimonials",
    "offer_banner",
    "map",
    "steps",
    "columns",
    "divider",
)


@pytest.fixture
def refs(owner: SignedIn) -> dict[str, str]:
    """One of everything a block can name."""
    return {
        "image_id": photo(owner)["id"],
        "project_id": create_project(owner)["id"],
        "city_id": create_city(owner)["id"],
        "faq_id": create_faq(owner)["id"],
        "testimonial_id": create_testimonial(owner)["id"],
        "offer_id": create_offer(owner)["id"],
    }


def errors_of(response: Any) -> dict[str, str]:
    assert response.status_code == 422, response.text
    return {e["field"]: e["message"] for e in response.json()["errors"]}


def test_every_block_type_saves_in_order_and_reads_back(
    owner: SignedIn, refs: dict[str, str]
) -> None:
    page = create_page(owner)
    saved = ok(put_blocks(owner, page["id"], every_block(**refs)))
    assert [b["type"] for b in saved["blocks"]] == list(TYPES)
    assert [b["sort_order"] for b in saved["blocks"]] == list(range(len(TYPES)))
    video_block = saved["blocks"][4]["data"]
    assert video_block["provider"] == "youtube" and video_block["video_id"] == "dQw4w9WgXcQ"
    assert video_block["url"] == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    assert [m["id"] for m in saved["media"]] == [refs["image_id"]]
    assert saved["block_count"] == len(TYPES)
    # The editor sends back what it received: the same list saves again unchanged.
    again = ok(put_blocks(owner, page["id"], [_input(b) for b in saved["blocks"]]))
    assert [b["id"] for b in again["blocks"]] == [b["id"] for b in saved["blocks"]]
    assert again["blocks"] == saved["blocks"]


def _input(saved: dict[str, Any]) -> dict[str, Any]:
    return {k: saved[k] for k in ("id", "type", "data", "is_visible")}


def test_video_link_is_stored_as_its_id_only(
    owner: SignedIn, refs: dict[str, str], db: Session
) -> None:
    page = create_page(owner)
    url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ&utm_source=newsletter"
    ok(put_blocks(owner, page["id"], [block("video", {"url": url})]))
    row = db.scalar(select(PageBlock).where(PageBlock.type == "video"))
    assert row is not None and "url" not in row.data
    assert row.data["provider"] == "youtube" and row.data["video_id"] == "dQw4w9WgXcQ"
    vimeo = ok(
        put_blocks(owner, page["id"], [block("video", {"url": "https://vimeo.com/76979871"})])
    )
    assert vimeo["blocks"][0]["data"]["url"] == "https://vimeo.com/76979871"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/watch?v=dQw4w9WgXcQ",
        "http://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/watch?v=short",
        "javascript:alert(1)",
    ],
)
def test_video_links_only_from_allowed_hosts(owner: SignedIn, url: str) -> None:
    page = create_page(owner)
    found = errors_of(put_blocks(owner, page["id"], [block("video", {"url": url})]))
    assert "YouTube or Vimeo" in next(iter(found.values()))


def test_a_library_video_works_and_a_photo_is_refused_as_video(owner: SignedIn) -> None:
    page = create_page(owner)
    clip = video(owner)
    saved = ok(put_blocks(owner, page["id"], [block("video", {"media_id": clip["id"]})]))
    assert saved["media"][0]["kind"] == "video"
    image = photo(owner)
    found = errors_of(put_blocks(owner, page["id"], [block("video", {"media_id": image["id"]})]))
    assert found == {"blocks.0.data.media_id": "Choose a video."}


@pytest.mark.parametrize(
    ("type_", "data", "field"),
    [
        ("hero", {"heading": ""}, "heading"),
        ("hero", {"heading": "x" * 121}, "heading"),
        ("hero", {"heading": "Hi", "colour": "gold"}, "colour"),
        ("rich_text", {}, "body"),
        ("image", {"caption": "No image"}, "image_id"),
        ("gallery", {"image_ids": []}, "image_ids"),
        ("gallery", {"image_ids": [random_id() for _ in range(25)]}, "image_ids"),
        ("project_grid", {"limit": 25}, "limit"),
        ("property_grid", {"limit": 0}, "limit"),
        ("cta", {"label": "Go"}, "href"),
        ("lead_form", {"source": "phone"}, "source"),
        ("stats", {"items": []}, "items"),
        ("steps", {"items": [{"title": f"Step {n}"} for n in range(9)]}, "items"),
        ("columns", {"columns": [{"body": "Only one"}]}, "columns"),
        (
            "columns",
            {"columns": [{"body": "a"}, {"body": "b"}, {"body": "c"}, {"body": "d"}]},
            "columns",
        ),
        ("map", {}, "project_id"),
        ("divider", {"style": "thick"}, "style"),
    ],
)
def test_invalid_block_data_is_refused_at_its_field(
    owner: SignedIn, type_: str, data: dict[str, Any], field: str
) -> None:
    page = create_page(owner)
    found = errors_of(put_blocks(owner, page["id"], [block(type_, data)]))
    assert any(key.startswith("blocks.0.") and field in key for key in found), found


def test_unknown_block_type_is_refused(owner: SignedIn) -> None:
    page = create_page(owner)
    errors_of(put_blocks(owner, page["id"], [block("marquee", {"text": "Hurry"})]))


@pytest.mark.parametrize(
    ("type_", "data"),
    [
        ("hero", {"heading": "<b>Big</b> homes"}),
        ("rich_text", {"body": "Hello <script>alert(1)</script>"}),
        ("rich_text", {"body": "<!-- note --> text"}),
        ("image", {"image_id": "IMAGE", "caption": '<img src="x" onerror="y">'}),
        ("cta", {"label": "<i>Go</i>", "href": "/contact"}),
        ("steps", {"items": [{"title": "Visit", "text": "<p>Come</p>"}]}),
        ("columns", {"columns": [{"body": "<div>a</div>"}, {"body": "b"}]}),
        (
            "stats",
            {"items": [{"value": "1", "label": "<u>x</u>", "source": "s", "as_of": "2026-01-01"}]},
        ),
    ],
)
def test_raw_html_is_refused_in_every_text(
    owner: SignedIn, type_: str, data: dict[str, Any]
) -> None:
    page = create_page(owner)
    if data.get("image_id") == "IMAGE":
        data = {**data, "image_id": photo(owner)["id"]}
    found = errors_of(put_blocks(owner, page["id"], [block(type_, data)]))
    assert any("HTML" in message for message in found.values()), found


def test_text_that_merely_mentions_angle_brackets_is_fine(owner: SignedIn) -> None:
    page = create_page(owner)
    text = "Budget < 50 L, 3<4, and 2 BHK > 1 BHK"
    saved = ok(put_blocks(owner, page["id"], [block("rich_text", {"body": text})]))
    assert saved["blocks"][0]["data"]["body"] == text


@pytest.mark.parametrize(
    "href",
    [
        "javascript:alert(1)",
        "JavaScript:alert(1)",
        "data:text/html;base64,PHNjcmlwdD4=",
        "vbscript:msgbox(1)",
        "http://example.com",
        "//evil.example/path",
        "https://empirebuildcon.com@evil.example/",
        "mailto:sales@example.com",
        "/path with space",
    ],
)
def test_unsafe_link_schemes_are_refused(owner: SignedIn, href: str) -> None:
    page = create_page(owner)
    for type_, data in (
        ("cta", {"label": "Go", "href": href}),
        ("hero", {"heading": "Hi", "cta": {"label": "Go", "href": href}}),
    ):
        found = errors_of(put_blocks(owner, page["id"], [block(type_, data)]))
        assert any("href" in key for key in found), (type_, found)


@pytest.mark.parametrize(
    "href", ["/projects/aurum-heights", "/contact?from=home", "https://x.org/a"]
)
def test_safe_links_are_accepted(owner: SignedIn, href: str) -> None:
    page = create_page(owner)
    ok(put_blocks(owner, page["id"], [block("cta", {"label": "Go", "href": href})]))


def test_compliance_stats_need_source_and_date_not_in_the_future(owner: SignedIn) -> None:
    page = create_page(owner)
    item = {"value": "[n]", "label": "homes", "source": "Register", "as_of": "2026-01-01"}
    for missing in ("source", "as_of"):
        body = {"items": [{k: v for k, v in item.items() if k != missing}]}
        found = errors_of(put_blocks(owner, page["id"], [block("stats", body)]))
        assert any(missing in key for key in found), found
    future = (today_ist() + timedelta(days=3)).isoformat()
    found = errors_of(
        put_blocks(owner, page["id"], [block("stats", {"items": [{**item, "as_of": future}]})])
    )
    assert any("future" in m for m in found.values())


def test_ids_are_checked_against_the_database(owner: SignedIn) -> None:
    page = create_page(owner)
    blocks = [
        block("image", {"image_id": random_id()}),
        block("project_grid", {"city_id": random_id()}),
        block("map", {"project_id": random_id()}),
        block("faq_list", {"faq_ids": [random_id()]}),
        block("testimonials", {"testimonial_ids": [random_id()]}),
        block("offer_banner", {"offer_id": random_id()}),
    ]
    found = errors_of(put_blocks(owner, page["id"], blocks))
    assert set(found) == {
        "blocks.0.data.image_id",
        "blocks.1.data.city_id",
        "blocks.2.data.project_id",
        "blocks.3.data.faq_ids.0",
        "blocks.4.data.testimonial_ids.0",
        "blocks.5.data.offer_id",
    }


def test_media_kind_is_checked(owner: SignedIn) -> None:
    page = create_page(owner)
    pdf = document(owner)
    found = errors_of(put_blocks(owner, page["id"], [block("gallery", {"image_ids": [pdf["id"]]})]))
    assert found == {"blocks.0.data.image_ids.0": "Choose an image."}


def test_compliance_block_photos_need_an_honest_label(owner: SignedIn) -> None:
    page = create_page(owner)
    unlabelled = photo(owner, label="")
    for type_, data in (
        ("hero", {"heading": "Hi", "image_id": unlabelled["id"]}),
        ("image", {"image_id": unlabelled["id"]}),
        ("gallery", {"image_ids": [unlabelled["id"]]}),
    ):
        found = errors_of(put_blocks(owner, page["id"], [block(type_, data)]))
        assert any("honest label" in m for m in found.values()), (type_, found)


def test_choices_that_exclude_each_other(owner: SignedIn, refs: dict[str, str]) -> None:
    page = create_page(owner)
    both = [
        block("faq_list", {"project_id": refs["project_id"], "faq_ids": [refs["faq_id"]]}),
        block(
            "testimonials",
            {"project_id": refs["project_id"], "testimonial_ids": [refs["testimonial_id"]]},
        ),
        block("offer_banner", {"offer_id": refs["offer_id"], "placement": "banner"}),
        block("offer_banner", {}),
        block("video", {}),
    ]
    found = errors_of(put_blocks(owner, page["id"], both))
    assert {key.split(".")[1] for key in found} == {"0", "1", "2", "3", "4"}


def test_blocks_left_out_are_deleted_and_unknown_ids_refused(owner: SignedIn) -> None:
    page = create_page(owner)
    saved = ok(put_blocks(owner, page["id"], [block("divider"), block("rich_text", {"body": "a"})]))
    keep = _input(saved["blocks"][1])
    again = ok(put_blocks(owner, page["id"], [keep]))
    assert [b["id"] for b in again["blocks"]] == [keep["id"]]
    other = create_page(owner, title="Other page")
    found = errors_of(put_blocks(owner, other["id"], [keep]))
    assert "blocks.0.id" in found


def test_invariant_page_media_links_follow_the_blocks(owner: SignedIn, db: Session) -> None:
    page = create_page(owner)
    first, second = photo(owner), photo(owner)
    ok(
        put_blocks(
            owner, page["id"], [block("gallery", {"image_ids": [second["id"], first["id"]]})]
        )
    )
    links = db.scalars(
        select(MediaLink).where(MediaLink.page_id == page["id"]).order_by(MediaLink.sort_order)
    ).all()
    assert [str(link.media_id) for link in links] == [second["id"], first["id"]]
    assert {link.role for link in links} == {"block"}
    ok(put_blocks(owner, page["id"], [block("image", {"image_id": first["id"]})]))
    db.expire_all()
    links = db.scalars(select(MediaLink).where(MediaLink.page_id == page["id"])).all()
    assert [str(link.media_id) for link in links] == [first["id"]]


def test_hidden_blocks_are_kept_hidden(owner: SignedIn) -> None:
    page = create_page(owner)
    saved = ok(put_blocks(owner, page["id"], [block("divider", is_visible=False)]))
    assert saved["blocks"][0]["is_visible"] is False


def test_too_many_blocks_are_refused(owner: SignedIn) -> None:
    page = create_page(owner)
    errors_of(put_blocks(owner, page["id"], [block("divider") for _ in range(61)]))
