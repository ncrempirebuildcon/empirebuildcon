"""Media inside projects: the RERA QR publish flow end to end (no `qr_present` fixture here),
the QR rules on a live project, the media fields of ProjectAdmin and list rows, duplicate
copying no media, and owners' deletes cascading to links only."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from conftest import SignedIn
from empire_api.media.models import Media, MediaLink
from empire_api.projects.blockers import RERA_QR_MISSING
from media_support import (
    MP4,
    attach,
    confirm,
    detach,
    direct_reply,
    document,
    patch_link,
    photo,
)
from projects_support import (
    PROJECTS,
    add_child,
    add_configuration,
    create_project,
    events,
    get_project,
    ok,
    patch_project,
    publish,
)


def ready_without_qr(signed: SignedIn) -> dict[str, str]:
    project = create_project(signed)
    ok(patch_project(signed, project["id"], {"rera_number": "UPRERAPRJ-TEST-01"}))
    add_configuration(signed, project["id"])
    return project


def test_the_rera_qr_publish_flow(owner: SignedIn, db: Session) -> None:
    """COMPLIANCE (D-002): publish needs a visible QR; a live project keeps one at all times."""
    project = ready_without_qr(owner)
    target = f"project:{project['id']}"
    assert get_project(owner, project["id"])["publish_blockers"] == [RERA_QR_MISSING]
    blocked = publish(owner, project["id"])
    assert blocked.status_code == 409
    assert {e["field"] for e in blocked.json()["errors"]} == {"rera.qr"}

    qr = photo(owner, title="RERA QR", attach_to=target, role="rera_qr")
    view = get_project(owner, project["id"])
    assert view["publish_blockers"] == [] and view["rera"]["qr"]["id"] == qr["id"]
    live = ok(publish(owner, project["id"]))
    assert live["publish_state"] == "published"

    link = next(
        str(row.id) for row in db.scalars(select(MediaLink).where(MediaLink.role == "rera_qr"))
    )
    hide = patch_link(owner, link, is_visible=False)
    assert hide.status_code == 409 and "Upload the new QR first" in hide.json()["detail"]
    remove = detach(owner, link)
    assert remove.status_code == 409
    hidden_replacement = attach(owner, photo(owner)["id"], target, "rera_qr", is_visible=False)
    assert hidden_replacement.status_code == 409

    new_qr = photo(owner, title="RERA QR (new)", attach_to=target, role="rera_qr")
    view = get_project(owner, project["id"])
    assert view["rera"]["qr"]["id"] == new_qr["id"] and view["publish_state"] == "published"
    assert events(db, "project.updated")[-1].payload["changed"] == ["rera"]

    ok(owner.client.post(f"{PROJECTS}/{project['id']}/unpublish", headers=owner.headers()))
    new_link = get_project(owner, project["id"])
    qr_link = db.scalar(select(MediaLink.id).where(MediaLink.role == "rera_qr"))
    assert new_link["publish_state"] == "draft"
    assert patch_link(owner, str(qr_link), is_visible=False).status_code == 200
    assert get_project(owner, project["id"])["publish_blockers"] == [RERA_QR_MISSING]


def test_a_hidden_qr_does_not_count(owner: SignedIn) -> None:
    project = ready_without_qr(owner)
    qr = photo(owner)
    ok(attach(owner, qr["id"], f"project:{project['id']}", "rera_qr", is_visible=False), 201)
    view = get_project(owner, project["id"])
    assert view["publish_blockers"] == [RERA_QR_MISSING] and view["rera"]["qr"] is None
    assert publish(owner, project["id"]).status_code == 409


def test_project_admin_fills_every_media_field(owner: SignedIn) -> None:
    project = create_project(owner)
    target = f"project:{project['id']}"
    configuration = add_configuration(owner, project["id"])
    update = add_child(
        owner, project["id"], "construction-updates", {"title": "Slab", "update_date": "2026-09-30"}
    )
    first = photo(owner, attach_to=target, role="gallery")
    second = photo(owner, attach_to=target, role="gallery")
    _, clip = direct_reply(owner, "video", "tour.mp4", MP4, "video/mp4")
    tour = ok(confirm(owner, clip, attach_to=target, role="video"), 201)
    price_list = document(owner, attach_to=target, role="document")
    brochure = document(owner, attach_to=target, role="brochure")
    plan = photo(owner, attach_to=f"configuration:{configuration['id']}", role="floor_plan")
    progress = photo(
        owner,
        attach_to=f"construction_update:{update['id']}",
        role="gallery",
        label="progress_photo",
        label_month="2026-09-01",
    )
    view = get_project(owner, project["id"])
    assert [m["id"] for m in view["gallery"]] == [first["id"], second["id"]]
    assert [m["sort_order"] for m in view["gallery"]] == [0, 1]
    assert view["cover"]["id"] == first["id"]
    assert [m["id"] for m in view["videos"]] == [tour["id"]]
    assert [m["id"] for m in view["documents"]] == [price_list["id"]]
    assert view["brochure"]["id"] == brochure["id"] and view["brochure"]["role"] == "brochure"
    assert [m["id"] for m in view["configurations"][0]["floor_plans"]] == [plan["id"]]
    photos = view["construction_updates"][0]["photos"]
    assert [(m["id"], m["label"]) for m in photos] == [(progress["id"], "progress_photo")]
    listed = ok(owner.client.get(PROJECTS))["items"][0]
    assert listed["cover"]["id"] == first["id"] and listed["rera"]["qr"] is None
    # The child lists carry their media too.
    configurations = ok(owner.client.get(f"{PROJECTS}/{project['id']}/configurations"))
    assert configurations[0]["floor_plans"][0]["id"] == plan["id"]
    updates = ok(owner.client.get(f"{PROJECTS}/{project['id']}/construction-updates"))
    assert updates[0]["photos"][0]["id"] == progress["id"]


def test_duplicate_copies_no_media(owner: SignedIn, db: Session) -> None:
    """COMPLIANCE: the copy needs its own RERA QR and photos (duplicate.py)."""
    project = ready_without_qr(owner)
    target = f"project:{project['id']}"
    photo(owner, attach_to=target, role="rera_qr")
    share = photo(owner, attach_to=target, role="gallery")
    ok(patch_project(owner, project["id"], {"seo": {"og_image_id": share["id"]}}))
    copy = ok(
        owner.client.post(f"{PROJECTS}/{project['id']}/duplicate", headers=owner.headers()), 201
    )
    assert copy["gallery"] == [] and copy["cover"] is None and copy["rera"]["qr"] is None
    assert copy["seo"]["og_image_id"] is None and copy["og_image"] is None
    assert RERA_QR_MISSING in copy["publish_blockers"]
    assert db.scalar(select(MediaLink.id).where(MediaLink.project_id == copy["id"])) is None


def test_deleting_an_owner_removes_its_links_not_the_files(owner: SignedIn, db: Session) -> None:
    project = create_project(owner)
    configuration = add_configuration(owner, project["id"])
    plan = photo(owner, attach_to=f"configuration:{configuration['id']}", role="floor_plan")
    gallery = photo(owner, attach_to=f"project:{project['id']}", role="gallery")
    url = f"{PROJECTS}/{project['id']}/configurations/{configuration['id']}"
    assert owner.client.delete(url, headers=owner.headers()).status_code == 204
    assert db.scalar(select(MediaLink.id).where(MediaLink.media_id == plan["id"])) is None
    assert (
        owner.client.delete(f"{PROJECTS}/{project['id']}", headers=owner.headers()).status_code
        == 204
    )
    db.expire_all()
    assert db.scalar(select(MediaLink.id)) is None
    assert {str(i) for i in db.scalars(select(Media.id))} == {plan["id"], gallery["id"]}
