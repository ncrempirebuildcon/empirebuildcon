"""Consent texts (content/consent.py): versions per kind, one current text per kind, publish,
never edited, draft wording refused in production, and seeds only in development and test."""

from __future__ import annotations

import concurrent.futures
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from conftest import SignedIn, make_user
from empire_api.content import consent
from empire_api.content.models import ConsentText
from empire_api.content.vocab import DRAFT_MARK
from empire_api.db import get_sessionmaker
from empire_api.projects.common import Actor
from empire_api.timeutil import utcnow
from leads_support import staff_client
from projects_support import audit_rows, events, ok

TEXTS = "/api/v1/admin/consent-texts"


def draft(signed: SignedIn, kind: str = "lead_form", body: str = "Approved wording.") -> Any:
    payload = {"kind": kind, "body": body, "checkbox_label": "Contact me about this enquiry."}
    return signed.client.post(TEXTS, json=payload, headers=signed.headers())


def publish(signed: SignedIn, text_id: str) -> Any:
    return signed.client.post(f"{TEXTS}/{text_id}/publish", headers=signed.headers())


def test_a_new_text_is_a_draft_with_the_next_version(owner: SignedIn) -> None:
    first = ok(draft(owner), 201)
    second = ok(draft(owner, body="Better wording."), 201)
    other = ok(draft(owner, "marketing"), 201)
    assert (first["version"], second["version"], other["version"]) == (1, 2, 1)
    assert first["is_current"] is False and first["published_at"] is None
    assert first["created_by"]["id"] == str(owner.user.id)
    assert first["is_draft"] is False
    listed = ok(owner.client.get(TEXTS, params={"kind": "lead_form"}))
    assert [t["version"] for t in listed] == [2, 1]


def test_publishing_makes_one_current_text_per_kind(owner: SignedIn, db: Session) -> None:
    first, second = ok(draft(owner), 201), ok(draft(owner, body="v2"), 201)
    published = ok(publish(owner, first["id"]))
    assert published["is_current"] and published["published_at"]
    ok(publish(owner, second["id"]))
    current = {t["version"]: t["is_current"] for t in ok(owner.client.get(TEXTS))}
    assert current == {2: True, 1: False}
    again = ok(publish(owner, first["id"]))  # an older version can come back
    assert again["is_current"] and again["published_at"] == published["published_at"]
    assert [e.payload["version"] for e in events(db, "consent_text.published")] == [1, 2, 1]
    assert audit_rows(db, "consent_text.published")[1].changes["replaces_version"] == [None, 1]
    assert ok(publish(owner, first["id"]))["is_current"]  # already current: nothing changes
    assert len(events(db, "consent_text.published")) == 3


def test_texts_are_never_edited(app: FastAPI) -> None:
    """COMPLIANCE: a change is a new version; no route changes a stored text."""
    paths = app.openapi()["paths"]
    methods = {m for p, item in paths.items() if p.startswith(TEXTS) for m in item}
    assert methods == {"get", "post"}


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "terms", "body": "x", "checkbox_label": "y"},
        {"kind": "lead_form", "body": "", "checkbox_label": "y"},
        {"kind": "lead_form", "body": "x" * 5001, "checkbox_label": "y"},
        {"kind": "lead_form", "body": "x", "checkbox_label": "y" * 301},
        {"kind": "lead_form", "body": "x", "checkbox_label": "y", "is_current": True},
    ],
)
def test_bad_texts_are_422(owner: SignedIn, body: dict[str, Any]) -> None:
    assert owner.client.post(TEXTS, json=body, headers=owner.headers()).status_code == 422


@pytest.mark.parametrize(
    ("role", "read", "write"), [("admin", 200, 201), ("marketing", 200, 403), ("sales", 403, 403)]
)
def test_who_may_read_and_publish(app: FastAPI, role: str, read: int, write: int) -> None:
    signed = staff_client(app, role)
    assert signed.client.get(TEXTS).status_code == read
    assert draft(signed).status_code == write


def test_production_refuses_to_publish_draft_wording(
    owner: SignedIn, monkeypatch: pytest.MonkeyPatch
) -> None:
    marked = ok(draft(owner, body=f"{DRAFT_MARK} Our wording."), 201)
    assert marked["is_draft"] is True
    monkeypatch.setattr(consent, "get_settings", lambda: SimpleNamespace(app_env="production"))
    refused = publish(owner, marked["id"])
    assert refused.status_code == 409
    assert refused.json()["detail"] == consent.STILL_DRAFT
    approved = ok(draft(owner, body="Our approved wording."), 201)
    assert ok(publish(owner, approved["id"]))["is_current"] is True


def test_an_unknown_text_is_404(owner: SignedIn) -> None:
    assert publish(owner, "01a16862-56ac-74cc-b260-0dfe5c63b4c5").status_code == 404


def test_seeds_are_draft_marked_current_and_only_in_development_or_test(
    db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert consent.seed_consent_texts(db) == 2
    db.commit()
    assert consent.seed_consent_texts(db) == 0  # idempotent
    rows = db.scalars(select(ConsentText)).all()
    assert {(r.kind, r.version, r.is_current) for r in rows} == {
        ("lead_form", 1, True),
        ("marketing", 1, True),
    }
    assert all(consent.is_draft(r) and r.body.startswith(DRAFT_MARK) for r in rows)
    db.execute(delete(ConsentText))
    db.commit()
    for env in ("staging", "production"):
        monkeypatch.setattr(consent, "get_settings", lambda env=env: SimpleNamespace(app_env=env))
        assert consent.seed_consent_texts(db) == 0


def test_two_drafts_at_once_get_different_versions(db: Session) -> None:
    author = make_user("admin")

    def write(n: int) -> int:
        with get_sessionmaker()() as session:
            row = consent.create_draft(
                session, "lead_form", f"Wording {n}", "Label", Actor(user_id=author.id, ip=None)
            )
            return row.version

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        versions = sorted(pool.map(write, range(6)))
    assert versions == [1, 2, 3, 4, 5, 6]


def test_the_database_allows_only_one_current_text_per_kind(db: Session) -> None:
    """INVARIANT: uq_consent_text_current_kind and ck_consent_text_current_is_published."""
    now = utcnow()
    db.add(
        ConsentText(
            kind="chat", version=1, body="a", checkbox_label="a", published_at=now, is_current=True
        )
    )
    db.commit()
    db.add(
        ConsentText(
            kind="chat", version=2, body="b", checkbox_label="b", published_at=now, is_current=True
        )
    )
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    db.add(ConsentText(kind="cookies", version=1, body="c", checkbox_label="c", is_current=True))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
