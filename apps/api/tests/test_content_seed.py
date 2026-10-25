"""Seeds: the system and legal pages (drafts, legal text only the D-017 placeholder) in every
environment, idempotently; sample content only outside production, all `is_sample`, SAMPLE in
the titles, and never a testimonial."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from empire_api.config import get_settings
from empire_api.content import models as content_models
from empire_api.content.models import Faq, Offer, Page, Post
from empire_api.content.seed import (
    SampleContentRefusedError,
    seed_pages,
    seed_sample_content,
)
from empire_api.content.vocab import LEGAL_DRAFT_MARK
from empire_api.projects.seed import seed_sample


def test_seed_pages_once(db: Session) -> None:
    assert seed_pages(db) == 7
    db.commit()
    assert seed_pages(db) == 0
    pages = {p.slug: p for p in db.scalars(select(Page))}
    assert {s for s, p in pages.items() if p.kind == "system"} == {
        "home",
        "projects",
        "about",
        "contact",
    }
    legal = [p for p in pages.values() if p.kind == "legal"]
    assert {p.slug for p in legal} == {"privacy", "terms", "disclaimer"}
    for page in legal:
        assert page.publish_state == "draft"
        assert [b.data["body"] for b in page.blocks] == [LEGAL_DRAFT_MARK]
    assert all(p.publish_state == "draft" and not p.is_sample for p in pages.values())
    assert pages["projects"].show_in_nav and pages["projects"].nav_order == 1
    assert not pages["home"].show_in_nav


def test_sample_content_is_marked_and_has_no_testimonials(db: Session) -> None:
    seed_sample(db)
    db.commit()
    result = seed_sample_content(db)
    db.commit()
    assert (result.posts, result.offers, result.faqs) == (1, 1, 4)
    assert seed_sample_content(db).faqs == 0
    for model in (Post, Offer):
        rows = db.scalars(select(model)).all()
        assert rows and all(r.is_sample and "SAMPLE" in r.title for r in rows)
    faqs = db.scalars(select(Faq)).all()
    assert all(f.is_sample and f.question.startswith("SAMPLE") for f in faqs)
    assert len([f for f in faqs if f.project_id is None]) == 2
    assert db.scalars(select(Post)).one().publish_state == "draft"
    assert db.scalars(select(Offer)).one().is_active is False
    assert db.scalar(select(func.count()).select_from(content_models.Testimonial)) == 0


def test_sample_content_is_refused_in_production(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "app_env", "production")
    with pytest.raises(SampleContentRefusedError):
        seed_sample_content(db)
