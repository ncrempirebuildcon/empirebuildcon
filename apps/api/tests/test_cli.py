"""The `empire-api` admin commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from conftest import make_user, sign_in
from empire_api.cli import app
from empire_api.config import get_settings
from empire_api.projects.models import (
    Amenity,
    City,
    Configuration,
    PaymentPlan,
    Project,
    Tower,
)
from empire_api.projects.seed import DEFAULT_AMENITIES, SampleRefusedError, seed_sample
from empire_api.site_settings.models import FeatureFlag, Setting
from empire_api.users.models import User

runner = CliRunner()


def test_create_superadmin_prints_a_setup_link_once(db: Session) -> None:
    first = runner.invoke(app, ["create-superadmin", "--email", "Admin@EmpireBuildcon.com"])
    assert first.exit_code == 0, first.output
    assert "/admin/setup#token=" in first.output
    user = db.scalar(select(User).where(User.role == "super_admin"))
    assert user is not None and user.email == "admin@empirebuildcon.com"
    assert user.password_hash is None
    second = runner.invoke(app, ["create-superadmin", "--email", "other@example.com"])
    assert second.exit_code == 1
    assert "already exists" in second.output


def test_create_user_reads_password_from_stdin(db: Session) -> None:
    result = runner.invoke(
        app,
        ["create-user", "--email", "e2e@example.com", "--role", "admin", "--password-stdin"],
        input="a long enough phrase\n",
    )
    assert result.exit_code == 0, result.output
    user = db.scalar(select(User).where(User.email == "e2e@example.com"))
    assert user is not None and user.password_hash


def test_create_user_refuses_weak_passwords_and_missing_stdin() -> None:
    weak = runner.invoke(
        app,
        ["create-user", "--email", "w@example.com", "--role", "sales", "--password-stdin"],
        input="password1234\n",
    )
    assert weak.exit_code == 1
    assert (
        runner.invoke(app, ["create-user", "--email", "w@example.com", "--role", "sales"]).exit_code
        == 1
    )


def test_create_user_is_refused_outside_dev_and_test(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "app_env", "staging")
    result = runner.invoke(
        app,
        ["create-user", "--email", "x@example.com", "--role", "sales", "--password-stdin"],
        input="a long enough phrase\n",
    )
    assert result.exit_code == 1


def test_seed_is_idempotent_and_keeps_switches(db: Session) -> None:
    assert runner.invoke(app, ["seed"]).exit_code == 0
    flag = db.get(FeatureFlag, "captcha")
    assert flag is not None
    flag.enabled = True
    db.commit()
    result = runner.invoke(app, ["seed"])
    assert result.exit_code == 0
    assert "0 new flags" in result.output
    db.expire_all()
    assert db.get(FeatureFlag, "captcha").enabled is True  # type: ignore[union-attr]
    routing = db.get(Setting, "lead_routing")
    assert routing is not None and routing.value["mode"] == "single"


def test_seed_adds_the_amenity_catalogue_once_and_keeps_edits(db: Session) -> None:
    first = runner.invoke(app, ["seed"])
    assert f"{len(DEFAULT_AMENITIES)} new amenities" in first.output
    slugs = set(db.scalars(select(Amenity.slug)))
    assert {"swimming-pool", "childrens-play-area", "24x7-security", "cctv"} <= slugs
    gym = db.scalar(select(Amenity).where(Amenity.slug == "gym"))
    assert gym is not None and (gym.icon, gym.category) == ("gym", "sports")
    gym.name = "Fitness centre"
    db.commit()
    again = runner.invoke(app, ["seed"])
    assert "0 new amenities" in again.output
    db.expire_all()
    assert db.scalar(select(Amenity.name).where(Amenity.slug == "gym")) == "Fitness centre"
    assert db.scalar(select(func.count()).select_from(Amenity)) == len(DEFAULT_AMENITIES)


def test_seed_sample_adds_marked_sample_projects_once(db: Session) -> None:
    result = runner.invoke(app, ["seed", "--sample"])
    assert result.exit_code == 0, result.output
    assert "2 sample projects added" in result.output
    assert "Sample media: 6 SAMPLE placeholder tiles added" in result.output
    projects = db.scalars(select(Project).order_by(Project.slug)).all()
    assert [p.name for p in projects] == ["Sample — Project A", "Sample — Project B"]
    for project in projects:
        # COMPLIANCE (D-015): every sample row is marked, uses RERA placeholders, stays a draft.
        assert project.is_sample is True
        assert project.publish_state == "draft"
        assert project.rera_number is not None and "SAMPLE" in project.rera_number
        assert project.seo.get("noindex") is True
    configurations = db.scalars(select(Configuration)).all()
    assert configurations and all(c.is_sample for c in configurations)
    assert {c.sales_status for c in configurations} == {"available", "sold_out"}
    city = db.scalar(select(City))
    assert city is not None and (city.name, city.state) == ("Sample City", "Uttar Pradesh")
    assert db.scalar(select(func.count()).select_from(Tower)) == 3
    for plan in db.scalars(select(PaymentPlan)):
        assert sum(stage["percent"] for stage in plan.stages) == 100
    again = runner.invoke(app, ["seed", "--sample"])
    assert "0 sample projects added, 2 already there" in again.output
    assert "0 SAMPLE placeholder tiles added, 2 projects already had photos" in again.output
    assert db.scalar(select(func.count()).select_from(Project)) == 2


def test_seed_sample_is_refused_in_production(monkeypatch: pytest.MonkeyPatch, db: Session) -> None:
    monkeypatch.setattr(get_settings(), "app_env", "production")
    result = runner.invoke(app, ["seed", "--sample"])
    assert result.exit_code == 1
    assert "never added in production" in result.output
    assert db.scalar(select(func.count()).select_from(Project)) == 0
    with pytest.raises(SampleRefusedError):
        seed_sample(db)


def test_sample_projects_are_valid_through_the_api(client: TestClient) -> None:
    """The seeded rows read back cleanly through ProjectAdmin (no impossible values)."""
    assert runner.invoke(app, ["seed", "--sample"]).exit_code == 0
    signed = sign_in(client, make_user("admin"))
    items = signed.client.get("/api/v1/admin/projects").json()["items"]
    assert {item["is_sample"] for item in items} == {True}
    for item in items:
        full = signed.client.get(f"/api/v1/admin/projects/{item['id']}").json()
        assert full["rera"]["number"].startswith("UPRERAPRJ-SAMPLE-")
        assert full["configurations"] and full["amenities"]
    b = next(i for i in items if i["slug"] == "sample-project-b")
    assert b["price"]["display"] == "Price on request"


def test_openapi_command_writes_the_spec(tmp_path: Path) -> None:
    out = tmp_path / "openapi.json"
    assert runner.invoke(app, ["openapi", "--out", str(out)]).exit_code == 0
    spec = json.loads(out.read_text())
    assert spec["paths"]["/api/v1/admin/flags/{key}"]["patch"]["x-permission"] == "flags.manage"


def test_gen_secrets_prints_every_variable() -> None:
    result = runner.invoke(app, ["gen-secrets"])
    names = [line.split("=", 1)[0] for line in result.output.strip().splitlines()]
    assert names == [
        "SESSION_SECRET",
        "DATA_ENCRYPTION_KEY",
        "INTERNAL_API_KEY",
        "IP_HASH_SALT",
        "REVALIDATE_SECRET",
        "EDGE_PROXY_KEY",
    ]
