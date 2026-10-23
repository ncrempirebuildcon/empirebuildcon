"""Media links (media/links.py): roles and kinds per owner, single-valued replace, the cover
rules, show/hide, detach, reorder, their audit rows and events, and permissions."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.media.models import MediaLink
from media_support import (
    LINKS,
    MP4,
    attach,
    confirm,
    detach,
    direct_reply,
    document,
    patch_link,
    photo,
    reorder,
    signed_as,
)
from projects_support import (
    add_child,
    add_configuration,
    audit_rows,
    create_project,
    events,
    get_project,
    make_ready,
    ok,
    publish,
)


def video(signed: SignedIn) -> Any:
    _, reply = direct_reply(signed, "video", "tour.mp4", MP4, "video/mp4")
    return ok(confirm(signed, reply), 201)


def gallery_of(signed: SignedIn, project_id: str, count: int) -> list[Any]:
    """`count` photos attached to the project's gallery, in upload order (LinkedMedia)."""
    for _ in range(count):
        photo(signed, attach_to=f"project:{project_id}", role="gallery")
    return list(get_project(signed, project_id)["gallery"])


# --- Roles and kinds -------------------------------------------------------------------------


def test_each_owner_takes_its_own_roles(owner: SignedIn) -> None:
    project = create_project(owner)
    configuration = add_configuration(owner, project["id"])
    update = add_child(
        owner, project["id"], "construction-updates", {"title": "Slab", "update_date": "2026-09-30"}
    )
    image, pdf, clip = photo(owner), document(owner), video(owner)
    accepted = [
        (image, f"project:{project['id']}", "gallery"),
        (image, f"project:{project['id']}", "rera_qr"),
        (clip, f"project:{project['id']}", "video"),
        (pdf, f"project:{project['id']}", "document"),
        (pdf, f"project:{project['id']}", "brochure"),
        (pdf, f"configuration:{configuration['id']}", "floor_plan"),
        (image, f"construction_update:{update['id']}", "gallery"),
    ]
    for media, owner_ref, role in accepted:
        body = ok(attach(owner, media["id"], owner_ref, role), 201)
        assert (body["role"], body["id"], body["is_visible"]) == (role, media["id"], True)


@pytest.mark.parametrize(
    ("owner_kind", "role", "media_kind", "field"),
    [
        ("configuration", "gallery", "image", "role"),
        ("construction_update", "video", "video", "role"),
        ("project", "floor_plan", "image", "role"),
        ("project", "gallery", "video", "media_id"),
        ("project", "video", "image", "media_id"),
        ("project", "rera_qr", "document", "media_id"),
        ("project", "document", "image", "media_id"),
        ("configuration", "floor_plan", "video", "media_id"),
    ],
)
def test_wrong_role_or_kind_is_422(
    owner: SignedIn, owner_kind: str, role: str, media_kind: str, field: str
) -> None:
    project = create_project(owner)
    owners = {
        "project": project["id"],
        "configuration": add_configuration(owner, project["id"])["id"],
        "construction_update": add_child(
            owner,
            project["id"],
            "construction-updates",
            {"title": "x", "update_date": "2026-09-30"},
        )["id"],
    }
    media = {"image": photo, "video": video, "document": document}[media_kind](owner)
    response = attach(owner, media["id"], f"{owner_kind}:{owners[owner_kind]}", role)
    assert response.status_code == 422, response.text
    assert response.json()["errors"][0]["field"] == field


def test_a_brochure_must_be_a_pdf(owner: SignedIn) -> None:
    project = create_project(owner)
    _, reply = direct_reply(owner, "document", "list.docx", b"PK\x03\x04" + b"\x00" * 40, "")
    docx = ok(confirm(owner, reply), 201)
    response = attach(owner, docx["id"], f"project:{project['id']}", "brochure")
    assert response.status_code == 422 and "PDF" in response.json()["detail"]
    assert attach(owner, docx["id"], f"project:{project['id']}", "document").status_code == 201


def test_unknown_owner_or_media_is_404(owner: SignedIn) -> None:
    project = create_project(owner)
    image = photo(owner)
    nobody = "00000000-0000-0000-0000-000000000000"
    assert attach(owner, image["id"], f"project:{nobody}", "gallery").status_code == 404
    assert attach(owner, image["id"], f"configuration:{nobody}", "floor_plan").status_code == 404
    assert attach(owner, nobody, f"project:{project['id']}", "gallery").status_code == 404
    assert attach(owner, image["id"], "page:" + nobody, "gallery").status_code == 422


def test_invariant_the_same_file_once_per_owner_and_role(owner: SignedIn) -> None:
    project = create_project(owner)
    image = photo(owner)
    ok(attach(owner, image["id"], f"project:{project['id']}", "gallery"), 201)
    again = attach(owner, image["id"], f"project:{project['id']}", "gallery")
    assert again.status_code == 409 and again.json()["errors"][0]["field"] == "media_id"
    # The same file in another role of the same project is fine (e.g. also the RERA QR slot).
    assert attach(owner, image["id"], f"project:{project['id']}", "rera_qr").status_code == 201


# --- Single-valued roles ---------------------------------------------------------------------


def test_single_valued_roles_replace_with_an_audit_row(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    first, second = document(owner), document(owner)
    ok(attach(owner, first["id"], f"project:{project['id']}", "brochure"), 201)
    ok(attach(owner, second["id"], f"project:{project['id']}", "brochure"), 201)
    view = get_project(owner, project["id"])
    assert view["brochure"]["id"] == second["id"]
    links = db.scalars(select(MediaLink).where(MediaLink.role == "brochure")).all()
    assert [str(link.media_id) for link in links] == [second["id"]]
    replaced = audit_rows(db, "media_link.replaced")
    assert replaced[0].changes == {"media_id": [first["id"], second["id"]]}
    library = ok(owner.client.get("/api/v1/admin/media", params={"unattached": "true"}))
    assert [m["id"] for m in library["items"]] == [first["id"]]  # the old file stays


def test_invariant_one_floor_plan_per_configuration(owner: SignedIn) -> None:
    project = create_project(owner)
    configuration = add_configuration(owner, project["id"])
    target = f"configuration:{configuration['id']}"
    ok(attach(owner, photo(owner)["id"], target, "floor_plan"), 201)
    newer = document(owner)
    ok(attach(owner, newer["id"], target, "floor_plan"), 201)
    plans = get_project(owner, project["id"])["configurations"][0]["floor_plans"]
    assert [p["id"] for p in plans] == [newer["id"]]


# --- Cover, show/hide ------------------------------------------------------------------------


def test_invariant_cover_is_pinned_else_first_visible(owner: SignedIn) -> None:
    """Regression: PATCH on a link once failed with FOR UPDATE on an outer join (PostgreSQL)."""
    project = create_project(owner)
    first, second, third = gallery_of(owner, project["id"], 3)
    assert get_project(owner, project["id"])["cover"]["id"] == first["id"]
    hidden = ok(patch_link(owner, first["link_id"], is_visible=False))
    assert hidden["is_visible"] is False
    assert get_project(owner, project["id"])["cover"]["id"] == second["id"]
    pinned = ok(patch_link(owner, third["link_id"], is_cover=True))
    assert pinned["is_cover"] is True
    view = get_project(owner, project["id"])
    assert view["cover"]["id"] == third["id"]
    assert [m["is_visible"] for m in view["gallery"]] == [False, True, True]  # hidden listed too
    assert view["gallery"][0]["link_id"] == first["link_id"]


def test_pinning_one_unpins_the_others(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    first, second = gallery_of(owner, project["id"], 2)
    ok(patch_link(owner, first["link_id"], is_cover=True))
    ok(patch_link(owner, second["link_id"], is_cover=True))
    db.expire_all()
    covers = db.scalars(select(MediaLink.id).where(MediaLink.is_cover.is_(True))).all()
    assert [str(i) for i in covers] == [second["link_id"]]
    unpinned = ok(patch_link(owner, second["link_id"], is_cover=False))
    assert unpinned["is_cover"] is False


def test_hidden_items_cant_be_the_cover(owner: SignedIn) -> None:
    project = create_project(owner)
    (only,) = gallery_of(owner, project["id"], 1)
    ok(patch_link(owner, only["link_id"], is_visible=False))
    refused = patch_link(owner, only["link_id"], is_cover=True)
    assert refused.status_code == 422 and refused.json()["errors"][0]["field"] == "is_cover"
    both = ok(patch_link(owner, only["link_id"], is_cover=True, is_visible=True))
    assert (both["is_cover"], both["is_visible"]) == (True, True)


def test_hiding_the_pinned_cover_unpins_it(owner: SignedIn) -> None:
    project = create_project(owner)
    first, second = gallery_of(owner, project["id"], 2)
    ok(patch_link(owner, second["link_id"], is_cover=True))
    hidden = ok(patch_link(owner, second["link_id"], is_visible=False))
    assert (hidden["is_cover"], hidden["is_visible"]) == (False, False)
    assert get_project(owner, project["id"])["cover"]["id"] == first["id"]


def test_only_photos_have_a_cover(owner: SignedIn) -> None:
    project = create_project(owner)
    link = ok(attach(owner, document(owner)["id"], f"project:{project['id']}", "document"), 201)
    refused = patch_link(owner, link["link_id"], is_cover=True)
    assert refused.status_code == 422
    assert "Only photos" in refused.json()["errors"][0]["message"]


def test_link_patch_validation_and_404(owner: SignedIn) -> None:
    project = create_project(owner)
    (only,) = gallery_of(owner, project["id"], 1)
    assert patch_link(owner, only["link_id"], is_visible=None).status_code == 422  # type: ignore[arg-type]
    unknown = owner.client.patch(
        f"{LINKS}/00000000-0000-0000-0000-000000000000",
        json={"is_visible": True},
        headers=owner.headers(),
    )
    assert unknown.status_code == 404
    extra = owner.client.patch(
        f"{LINKS}/{only['link_id']}", json={"sort_order": 3}, headers=owner.headers()
    )
    assert extra.status_code == 422


def test_no_change_writes_nothing(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    (only,) = gallery_of(owner, project["id"], 1)
    ok(patch_link(owner, only["link_id"], is_visible=True))
    assert audit_rows(db, "media_link.updated") == []


# --- Detach and reorder ----------------------------------------------------------------------


def test_detach_keeps_the_file_and_closes_the_gap(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    first, second, third = gallery_of(owner, project["id"], 3)
    assert detach(owner, second["link_id"]).status_code == 204
    gallery = get_project(owner, project["id"])["gallery"]
    assert [(m["id"], m["sort_order"]) for m in gallery] == [(first["id"], 0), (third["id"], 1)]
    library = ok(owner.client.get("/api/v1/admin/media", params={"unattached": "true"}))
    assert [m["id"] for m in library["items"]] == [second["id"]]
    assert len(audit_rows(db, "media_link.detached")) == 1
    assert detach(owner, second["link_id"]).status_code == 404


def test_reorder_sets_the_full_order(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    first, second, third = gallery_of(owner, project["id"], 3)
    new = [third["link_id"], first["link_id"], second["link_id"]]
    assert reorder(owner, new).status_code == 204
    view = get_project(owner, project["id"])
    assert [m["link_id"] for m in view["gallery"]] == new
    assert view["cover"]["id"] == third["id"]  # first visible in the new order
    rows = audit_rows(db, "media_link.reordered")
    assert rows[0].entity_type == "project" and rows[0].changes["gallery_order"][1] == new


def test_reorder_must_list_one_list_exactly_once(owner: SignedIn) -> None:
    project = create_project(owner)
    first, second = gallery_of(owner, project["id"], 2)
    other = create_project(owner, "Other")
    (elsewhere,) = gallery_of(owner, other["id"], 1)
    doc = ok(attach(owner, document(owner)["id"], f"project:{project['id']}", "document"), 201)
    for ids in (
        [first["link_id"]],  # missing one
        [first["link_id"], second["link_id"], elsewhere["link_id"]],  # another owner's link
        [first["link_id"], doc["link_id"]],  # another role
        ["00000000-0000-0000-0000-000000000000"],
    ):
        response = reorder(owner, ids)
        assert response.status_code == 422, ids
        assert response.json()["errors"][0]["field"] == "ids"
    assert reorder(owner, [first["link_id"], first["link_id"]]).status_code == 422
    assert reorder(owner, []).status_code == 422


# --- Events and permissions ------------------------------------------------------------------


def test_events_name_the_change_and_follow_the_owner(
    owner: SignedIn, db: Session, qr_present: None
) -> None:
    project = create_project(owner)
    image = photo(owner)
    link = ok(attach(owner, image["id"], f"project:{project['id']}", "gallery"), 201)
    assert [e.payload["change"] for e in events(db, "media.updated")] == ["attached"]
    assert events(db, "project.updated") == []  # a draft: nothing to revalidate
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    ok(patch_link(owner, link["link_id"], is_visible=False))
    updated = events(db, "project.updated")
    assert updated[-1].payload["changed"] == ["gallery"]
    assert updated[-1].payload["change"] == "media_hidden"
    configuration = get_project(owner, project["id"])["configurations"][0]
    ok(
        attach(owner, document(owner)["id"], f"configuration:{configuration['id']}", "floor_plan"),
        201,
    )
    changed = events(db, "configuration.changed")
    assert changed[-1].aggregate_id == configuration["id"]
    assert changed[-1].payload["change"] == "media_attached"


def test_sales_cannot_attach_and_marketing_can(app: FastAPI, owner: SignedIn) -> None:
    project = create_project(owner)
    image = photo(owner)
    sales = signed_as(app, "sales")
    assert attach(sales, image["id"], f"project:{project['id']}", "gallery").status_code == 403
    marketing = signed_as(app, "marketing")
    link = ok(attach(marketing, image["id"], f"project:{project['id']}", "gallery"), 201)
    assert patch_link(sales, link["link_id"], is_visible=False).status_code == 403
    assert reorder(sales, [link["link_id"]]).status_code == 403
    assert detach(sales, link["link_id"]).status_code == 403
    assert detach(marketing, link["link_id"]).status_code == 204
