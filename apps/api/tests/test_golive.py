"""Task L8: `empire-api golive-check`, the read-only "is this database ready to go live?" report."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from conftest import SignedIn
from content_support import block, create_faq, create_page, publish_page, put_blocks
from empire_api import golive
from empire_api.cli import app as cli_app
from empire_api.content.models import ConsentText, Page
from empire_api.content.seed import seed_pages
from empire_api.platform import outbox
from empire_api.platform.models import OutboxEvent
from empire_api.site_settings.models import FeatureFlag
from empire_api.timeutil import utcnow
from empire_api.users.models import UserTwoFactor
from projects_support import create_project, make_ready, ok, patch_project, publish


def by_name(checks: list[golive.Check]) -> dict[str, list[golive.Check]]:
    out: dict[str, list[golive.Check]] = {}
    for check in checks:
        out.setdefault(check.name, []).append(check)
    return out


def statuses(checks: list[golive.Check], name: str) -> list[str]:
    return [c.status for c in by_name(checks).get(name, [])]


# ── The placeholder rule ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Office at [Office address].", ["[Office address]"]),
        ("[DRAFT — text to be drafted]", ["[DRAFT — text to be drafted]"]),
        ("Possession [TBD]", ["[TBD]"]),
        ("See [the brochure](https://x.example).", []),  # a Markdown link
        ("Carpet area 650 sq ft [1]", []),
        ("Plain text with no brackets.", []),
    ],
)
def test_placeholders(text: str, found: list[str]) -> None:
    assert golive._placeholders(text) == found


# ── Projects ───────────────────────────────────────────────────────────────────────────────


def test_no_live_project_fails(db: Session) -> None:
    assert statuses(golive.check_projects(db), "projects") == ["FAIL"]


def test_a_ready_project_passes_and_a_placeholder_fails(
    owner: SignedIn, db: Session, qr_present: None
) -> None:
    project = create_project(owner, name="Aurum Heights")
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    checks = golive.check_projects(db)
    assert statuses(checks, "projects") == ["PASS"]
    assert "project aurum-heights" not in by_name(checks)

    ok(patch_project(owner, project["id"], {"description": "Near [Landmark name]."}))
    db.expire_all()
    found = by_name(golive.check_projects(db))["project aurum-heights"]
    assert [c.status for c in found] == ["FAIL"]
    assert "[Landmark name]" in found[0].detail


def test_a_live_project_that_lost_its_rera_qr_fails(
    owner: SignedIn, db: Session, qr_present: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """COMPLIANCE (D-002): publishing checks the QR once; the report checks it again."""
    project = create_project(owner, name="Lost QR")
    make_ready(owner, project["id"])
    ok(publish(owner, project["id"]))
    monkeypatch.setattr("empire_api.projects.blockers.projects_with_rera_qr", lambda db, ids: set())
    found = by_name(golive.check_projects(db))["project lost-qr"]
    assert found[0].status == "FAIL"
    assert "QR" in found[0].detail


# ── Pages, legal texts and consent ─────────────────────────────────────────────────────────


def test_unpublished_or_draft_legal_pages_fail(owner: SignedIn, db: Session) -> None:
    seed_pages(db)
    db.commit()
    legal = list(db.scalars(select(Page.slug).where(Page.kind == "legal")))
    assert legal
    checks = by_name(golive.check_pages_and_posts(db))
    for slug in legal:
        assert [c.status for c in checks[f"page /{slug}"]] == ["FAIL"]


def test_a_live_page_with_a_placeholder_fails(owner: SignedIn, db: Session) -> None:
    faq = create_faq(owner, "[Another common question]", answer="Yes.")
    page = create_page(owner, "Help")
    put_blocks(owner, page["id"], [block("faq_list", {"faq_ids": [faq["id"]]})])
    ok(publish_page(owner, page["id"]))
    found = by_name(golive.check_pages_and_posts(db))[f"page /{page['slug']}"]
    assert found[0].status == "FAIL"
    assert "[Another common question]" in found[0].detail


def test_consent_texts_must_be_published_and_approved(db: Session) -> None:
    checks = golive.check_consent(db)
    assert {c.name: c.status for c in checks} == {
        "consent lead_form": "FAIL",
        "consent marketing": "FAIL",
        "consent brochure": "FAIL",
    }
    for kind in golive.LAUNCH_CONSENTS:
        db.add(
            ConsentText(
                kind=kind,
                version=1,
                body="Approved wording.",
                checkbox_label="I agree.",
                published_at=utcnow(),
                is_current=True,
            )
        )
    db.commit()
    assert {c.status for c in golive.check_consent(db)} == {"PASS"}


# ── People, features, background work ──────────────────────────────────────────────────────


def test_super_admin_needs_two_factor(owner: SignedIn, db: Session) -> None:
    assert statuses(golive.check_people(db), "super-admin") == ["FAIL"]
    db.add(UserTwoFactor(user_id=owner.user.id, secret_encrypted="x", confirmed_at=utcnow()))
    db.commit()
    db.expire_all()
    checks = golive.check_people(db)
    assert statuses(checks, "super-admin") == ["PASS"]
    assert statuses(checks, "lead alerts") == ["WARN"]  # no shared inbox set (D-050)


def test_chat_on_without_a_provider_fails(db: Session) -> None:
    assert statuses(golive.check_features(db), "chat_widget") == ["PASS"]
    row = db.get(FeatureFlag, "chat_widget")
    assert row is not None
    row.enabled = True
    db.commit()
    assert statuses(golive.check_features(db), "chat_widget") == ["FAIL"]


def test_stuck_and_dead_events(db: Session) -> None:
    assert statuses(golive.check_outbox(db), "background job") == ["PASS"]
    old = outbox.emit(db, type_="settings.updated", aggregate_type="settings", aggregate_id="x")
    old.available_at = utcnow() - timedelta(hours=2)
    dead = outbox.emit(db, type_="settings.updated", aggregate_type="settings", aggregate_id="y")
    dead.status = "dead"
    db.commit()
    assert statuses(golive.check_outbox(db), "background job") == ["FAIL", "WARN"]
    assert db.scalars(select(OutboxEvent)).all()  # read-only: nothing changed or removed


# ── The command ────────────────────────────────────────────────────────────────────────────


def test_cli_fails_on_an_empty_site_and_prints_json(db: Session) -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["golive-check"])
    assert result.exit_code == 1
    assert "FAIL  projects: No project is live" in result.output
    assert "to fix" in result.output
    as_json = runner.invoke(cli_app, ["golive-check", "--json"])
    rows: list[dict[str, Any]] = json.loads(as_json.stdout)
    assert {"status", "name", "detail"} == set(rows[0])
    assert as_json.exit_code == 1
