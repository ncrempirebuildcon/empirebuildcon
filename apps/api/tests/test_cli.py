"""The `empire-api` admin commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session
from typer.testing import CliRunner

from empire_api.cli import app
from empire_api.config import get_settings
from empire_api.site_settings.models import FeatureFlag, Setting
from empire_api.users.models import User

runner = CliRunner()


def test_create_superadmin_prints_a_setup_link_once(db: Session) -> None:
    first = runner.invoke(app, ["create-superadmin", "--email", "Admin@EmpireBuildcon.com"])
    assert first.exit_code == 0, first.output
    assert "/admin/setup?token=" in first.output
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
    result = runner.invoke(app, ["seed", "--sample"])
    assert result.exit_code == 0
    assert "Phase 4" in result.output
    db.expire_all()
    assert db.get(FeatureFlag, "captcha").enabled is True  # type: ignore[union-attr]
    routing = db.get(Setting, "lead_routing")
    assert routing is not None and routing.value["mode"] == "single"


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
    ]
