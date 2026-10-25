"""Review fixes on saving pages and posts: a stale editor tab can't overwrite someone else's save
(L7), `seo.canonical_path` stays on our site (M5), and no SEO or translation text accepts HTML,
with per-field translation limits (L1)."""

from __future__ import annotations

from typing import Any

import pytest

from conftest import SignedIn
from content_support import (
    FAQS,
    POSTS,
    block,
    create_faq,
    create_page,
    create_post,
    get_page,
    patch_page,
    put_blocks,
)
from projects_support import create_project, ok, patch_project


def put_blocks_at(signed: SignedIn, page_id: str, blocks: list[Any], expected: str | None) -> Any:
    body: dict[str, Any] = {"blocks": blocks}
    if expected is not None:
        body["expected_updated_at"] = expected
    return signed.client.put(
        f"/api/v1/admin/pages/{page_id}/blocks", json=body, headers=signed.headers()
    )


# --- L7: optimistic concurrency on PUT /blocks and PATCH ---------------------------------------


def test_a_stale_blocks_save_is_refused(owner: SignedIn) -> None:
    page = create_page(owner)
    opened = page["updated_at"]  # both tabs open the page now
    first = ok(put_blocks_at(owner, page["id"], [block("divider")], opened))
    stale = put_blocks_at(owner, page["id"], [block("rich_text", {"body": "Mine"})], opened)
    assert stale.status_code == 409, stale.text
    assert stale.json()["errors"][0]["field"] == "expected_updated_at"
    assert "Someone else saved this page" in stale.json()["detail"]
    assert [b["type"] for b in get_page(owner, page["id"])["blocks"]] == ["divider"]
    # The fresh value from the last response works; leaving it out skips the check.
    ok(put_blocks_at(owner, page["id"], [block("divider")], first["updated_at"]))
    ok(put_blocks_at(owner, page["id"], [], None))


def test_a_stale_patch_is_refused(owner: SignedIn) -> None:
    page = create_page(owner)
    opened = page["updated_at"]
    saved = ok(
        patch_page(owner, page["id"], {"title": "About Empire", "expected_updated_at": opened})
    )
    stale = patch_page(owner, page["id"], {"title": "About", "expected_updated_at": opened})
    assert stale.status_code == 409 and stale.json()["errors"][0]["field"] == "expected_updated_at"
    after_blocks = ok(put_blocks(owner, page["id"], [block("divider")]))
    assert after_blocks["updated_at"] != saved["updated_at"]  # blocks count as an edit
    ok(
        patch_page(
            owner, page["id"], {"title": "About", "expected_updated_at": after_blocks["updated_at"]}
        )
    )
    # An unchanged value with nothing else sent is a harmless no-op.
    ok(
        patch_page(
            owner, page["id"], {"expected_updated_at": get_page(owner, page["id"])["updated_at"]}
        )
    )
    assert patch_page(owner, page["id"], {"expected_updated_at": None}).status_code == 200


# --- M5: canonical_path is a path on our site ---------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/\t/evil.example", "/\n/evil.example", "/\r/evil.example", "/a\x0bb", "//evil.example"],
)
def test_security_canonical_path_refuses_whitespace_and_control_characters(
    owner: SignedIn, path: str
) -> None:
    page = create_page(owner)
    refused = patch_page(owner, page["id"], {"seo": {"canonical_path": path}})
    assert refused.status_code == 422, (path, refused.text)
    assert refused.json()["errors"][0]["field"] == "seo.canonical_path"
    project = create_project(owner)
    on_project = patch_project(owner, project["id"], {"seo": {"canonical_path": path}})
    assert on_project.status_code == 422, (path, on_project.text)


# --- L1: no HTML in SEO or translation text; per-field translation limits ----------------------


def test_security_seo_text_refuses_html(owner: SignedIn) -> None:
    page = create_page(owner)
    for seo, field in (
        ({"title": "<script>alert(1)</script>"}, "seo.title"),
        ({"description": "Homes <b>now</b>"}, "seo.description"),
    ):
        refused = patch_page(owner, page["id"], {"seo": seo})
        assert refused.status_code == 422 and refused.json()["errors"][0]["field"] == field
    ok(patch_page(owner, page["id"], {"seo": {"title": "Prices < ₹50 L in Noida"}}))


def test_security_translations_refuse_html(owner: SignedIn) -> None:
    page = create_page(owner)
    refused = patch_page(owner, page["id"], {"translations": {"hi": {"title": "<b>हमारे</b>"}}})
    assert refused.status_code == 422 and refused.json()["errors"][0]["field"] == "translations"
    post = create_post(owner)
    for fields in ({"body": "<iframe src=//evil>"}, {"excerpt": "<!-- x -->"}):
        response = owner.client.patch(
            f"{POSTS}/{post['id']}", json={"translations": {"hi": fields}}, headers=owner.headers()
        )
        assert response.status_code == 422, (fields, response.text)
    faq = create_faq(owner)
    response = owner.client.patch(
        f"{FAQS}/{faq['id']}",
        json={"translations": {"hi": {"answer": "<img src=x onerror=alert(1)>"}}},
        headers=owner.headers(),
    )
    assert response.status_code == 422


def test_translation_limits_follow_the_english_fields(owner: SignedIn) -> None:
    post = create_post(owner)

    def translate(fields: dict[str, str]) -> Any:
        return owner.client.patch(
            f"{POSTS}/{post['id']}", json={"translations": {"hi": fields}}, headers=owner.headers()
        )

    assert translate({"body": "अ" * 30_000}).status_code == 200  # was capped at 20,000
    assert translate({"body": "अ" * 50_000}).status_code == 200  # same as the English body
    assert translate({"body": "अ" * 50_001}).status_code == 422
    assert translate({"title": "अ" * 161}).status_code == 422  # English title: 160
    assert translate({"excerpt": "अ" * 301}).status_code == 422
    page = create_page(owner)
    long_title = patch_page(owner, page["id"], {"translations": {"hi": {"title": "अ" * 121}}})
    assert long_title.status_code == 422
    project = create_project(owner)
    too_long = patch_project(owner, project["id"], {"translations": {"hi": {"name": "अ" * 121}}})
    assert too_long.status_code == 422
    ok(patch_project(owner, project["id"], {"translations": {"hi": {"description": "अ" * 20_000}}}))
