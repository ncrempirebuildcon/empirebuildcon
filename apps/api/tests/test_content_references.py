"""Review fix L12: what page blocks and offers name can't vanish under them. Saving blocks reads
the rows they name FOR SHARE (so a concurrent delete waits and then sees the block), a project
that an offer or a page block names can't be deleted (409 naming where), and a project-placement
offer always has its project (CHECK)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from conftest import SignedIn
from content_support import (
    OFFERS,
    block,
    create_faq,
    create_offer,
    create_page,
    create_testimonial,
    put_blocks,
)
from empire_api.content import block_refs
from empire_api.content.block_types import BlockInput
from empire_api.db import get_sessionmaker
from projects_support import create_project, ok

PROJECTS = "/api/v1/admin/projects"


def delete_project(signed: SignedIn, project_id: str) -> Any:
    return signed.client.delete(f"{PROJECTS}/{project_id}", headers=signed.headers())


@pytest.mark.parametrize(
    ("make_block", "where"),
    [
        (lambda p: block("map", {"project_id": p}), "a map block"),
        (lambda p: block("lead_form", {"project_id": p}), "an enquiry form block"),
        (lambda p: block("faq_list", {"project_id": p}), "an FAQ list block"),
        (lambda p: block("testimonials", {"project_id": p}), "a testimonials block"),
    ],
)
def test_a_project_a_page_block_names_cant_be_deleted(
    owner: SignedIn, make_block: Any, where: str
) -> None:
    project = create_project(owner)
    page = create_page(owner, title="Aurum landing")
    ok(put_blocks(owner, page["id"], [make_block(project["id"])]))
    refused = delete_project(owner, project["id"])
    assert refused.status_code == 409, refused.text
    assert f"page “Aurum landing” ({where})" in refused.json()["detail"]
    ok(put_blocks(owner, page["id"], []))
    assert delete_project(owner, project["id"]).status_code == 204


def test_a_project_whose_faqs_a_block_picked_cant_be_deleted(owner: SignedIn) -> None:
    """Its FAQs go with it (CASCADE), which would leave the block pointing at nothing."""
    project = create_project(owner)
    faq = create_faq(owner, project_id=project["id"])
    page = create_page(owner, title="Parking")
    ok(put_blocks(owner, page["id"], [block("faq_list", {"faq_ids": [faq["id"]]})]))
    refused = delete_project(owner, project["id"])
    assert (
        refused.status_code == 409
        and "page “Parking” (an FAQ list block)" in refused.json()["detail"]
    )


def test_a_project_an_offer_names_cant_be_deleted(owner: SignedIn) -> None:
    project = create_project(owner)
    offer = create_offer(owner, placement="project", project_id=project["id"])
    create_testimonial(owner, project_id=project["id"])  # testimonials just lose the project
    refused = delete_project(owner, project["id"])
    assert refused.status_code == 409 and "offer “Festive offer”" in refused.json()["detail"]
    owner.client.delete(f"{OFFERS}/{offer['id']}", headers=owner.headers())
    assert delete_project(owner, project["id"]).status_code == 204


def test_invariant_a_project_offer_always_has_its_project(owner: SignedIn, db: Session) -> None:
    offer = create_offer(owner)
    with pytest.raises(IntegrityError):
        db.execute(
            text("UPDATE offer SET placement = 'project' WHERE id = :id"), {"id": offer["id"]}
        )
        db.commit()
    db.rollback()


@pytest.fixture
def other_session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        session.execute(text("SET lock_timeout = '200ms'"))
        yield session
        session.rollback()


def test_saving_blocks_holds_a_share_lock_on_what_they_name(
    owner: SignedIn, other_session: Session
) -> None:
    """While a blocks save is checking, a delete of a named FAQ, testimonial, offer or project
    can't take its row (it waits, then sees the new block)."""
    project = create_project(owner)
    faq = create_faq(owner)
    testimonial = create_testimonial(owner)
    offer = create_offer(owner)
    blocks = [
        BlockInput.model_validate(item).root
        for item in (
            block("faq_list", {"faq_ids": [faq["id"]]}),
            block("testimonials", {"testimonial_ids": [testimonial["id"]]}),
            block("offer_banner", {"offer_id": offer["id"]}),
            block("map", {"project_id": project["id"]}),
        )
    ]
    with get_sessionmaker()() as saving:
        assert block_refs.check(saving, block_refs.collect(blocks)) == []
        for table, row_id in (
            ("faq", faq["id"]),
            ("testimonial", testimonial["id"]),
            ("offer", offer["id"]),
            ("project", project["id"]),
        ):
            with pytest.raises(OperationalError, match="lock"):
                other_session.execute(
                    text(f"SELECT id FROM {table} WHERE id = :id FOR UPDATE"),  # noqa: S608
                    {"id": row_id},
                )
            other_session.rollback()
            other_session.execute(text("SET lock_timeout = '200ms'"))
        saving.rollback()
