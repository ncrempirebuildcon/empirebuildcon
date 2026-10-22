"""`empire-api`: admin and developer commands (run with `uv run empire-api --help`).

Commands:
  create-superadmin  One-time: create the owner's account and print a setup link (D-009).
  create-user        Development/test only: a staff account with a password from stdin.
  seed               Feature flags, default settings and the amenity catalogue (idempotent).
                     --sample also adds sample projects (development and demos; D-015).
  openapi            Write the OpenAPI spec for the typed web client (D-020).
  gen-secrets        Print fresh random values for your own local .env.

SECURITY: no command ever prints or accepts a password as an argument (shell history), and
create-superadmin prints a one-time link instead of a password (SECURITY.md §1).
"""

from __future__ import annotations

import base64
import json
import secrets
import sys
from pathlib import Path
from typing import Annotated

import typer
from cryptography.fernet import Fernet
from sqlalchemy import select

from empire_api.config import get_settings
from empire_api.db import get_sessionmaker
from empire_api.projects.seed import SampleRefusedError, seed_amenities, seed_sample
from empire_api.site_settings.defaults import seed_settings
from empire_api.site_settings.flags import seed_flags
from empire_api.users import passwords, service
from empire_api.users.models import User
from empire_api.users.roles import ROLE_KEYS

app = typer.Typer(help="Empire API admin commands.", no_args_is_help=True, add_completion=False)


def _out(message: str) -> None:
    typer.echo(message)


def _fail(message: str) -> None:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


@app.command("create-superadmin")
def create_superadmin(
    email: Annotated[str, typer.Option(help="The owner's email, e.g. admin@empirebuildcon.com")],
    name: Annotated[str, typer.Option(help="Display name in the CMS")] = "Owner",
) -> None:
    """Create the first super-admin and print a one-time setup link (valid 24 hours)."""
    with get_sessionmaker()() as db:
        exists = db.scalar(select(User.id).where(User.role == "super_admin").limit(1))
        if exists is not None:
            _fail("A super-admin already exists. Use the CMS to invite more staff.")
        _user, token = service.create_user(
            db, {"email": email, "name": name, "role": "super_admin"}, actor_id=None, meta=None
        )
    _out("Super-admin created. Open this link within 24 hours to choose a password:")
    _out(service.setup_link(token))
    _out("The link works once. Don't share it.")


@app.command("create-user")
def create_user(
    email: Annotated[str, typer.Option()],
    role: Annotated[str, typer.Option(help=f"One of: {', '.join(ROLE_KEYS)}")],
    name: Annotated[str, typer.Option()] = "Test user",
    password_stdin: Annotated[
        bool, typer.Option("--password-stdin", help="Read the password from standard input")
    ] = False,
) -> None:
    """Development/test only: create an active account with a password (browser tests)."""
    settings = get_settings()
    if settings.app_env not in ("development", "test"):
        _fail("create-user only works when APP_ENV is development or test.")
    if role not in ROLE_KEYS:
        _fail(f"Unknown role. Use one of: {', '.join(ROLE_KEYS)}")
    if not password_stdin:
        _fail("Pass --password-stdin and pipe the password in (never as an argument).")
    password = sys.stdin.readline().rstrip("\n")
    errors = passwords.policy_errors(password, email=email)
    if errors:
        _fail("Password refused: " + " ".join(errors))
    with get_sessionmaker()() as db:
        user, _token = service.create_user(
            db, {"email": email, "name": name, "role": role}, actor_id=None, meta=None
        )
        user = db.get(User, user.id) or user
        user.password_hash = passwords.hash_password(password)
        db.commit()
    _out(f"Created {role} account for {service.normalise_email(email)}.")


@app.command("seed")
def seed(
    sample: Annotated[
        bool, typer.Option("--sample", help="Also add sample projects (never in production)")
    ] = False,
) -> None:
    """Create feature flags, default settings and the amenity catalogue. Safe to run again.

    `--sample` adds "Sample City" and "Sample — Project A/B" for development and demos. They are
    marked is_sample, stay drafts, and are refused when APP_ENV is production (D-015).
    """
    if sample and get_settings().app_env == "production":
        _fail("Sample data is never added in production (D-015).")
    with get_sessionmaker()() as db:
        flags_added = seed_flags(db)
        settings_added = seed_settings(db)
        amenities_added = seed_amenities(db)
        db.commit()
    _out(
        f"Seeded: {flags_added} new flags, {settings_added} new settings groups, "
        f"{amenities_added} new amenities."
    )
    if sample:
        with get_sessionmaker()() as db:
            try:
                result = seed_sample(db)
            except SampleRefusedError as exc:
                _fail(str(exc))
                return
            db.commit()
        _out(
            f"Sample data: {result.projects_added} sample projects added, "
            f"{result.projects_skipped} already there (all marked is_sample, all drafts)."
        )


@app.command("openapi")
def openapi(
    out: Annotated[Path, typer.Option(help="Where to write the JSON spec")] = Path("openapi.json"),
) -> None:
    """Write the OpenAPI spec generated from the code (source of truth from Phase 3, D-020)."""
    from empire_api.main import create_app  # noqa: PLC0415 — only this command needs the app

    spec = create_app().openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n")
    _out(f"Wrote {out}")


@app.command("gen-secrets")
def gen_secrets() -> None:
    """Print fresh random secrets for YOUR local .env. Never paste them into chat or commits."""
    _out(f"SESSION_SECRET={secrets.token_urlsafe(48)}")
    _out(f"DATA_ENCRYPTION_KEY={Fernet.generate_key().decode()}")
    _out(f"INTERNAL_API_KEY={secrets.token_urlsafe(36)}")
    _out(f"IP_HASH_SALT={base64.urlsafe_b64encode(secrets.token_bytes(24)).decode()}")
    _out(f"REVALIDATE_SECRET={secrets.token_urlsafe(36)}")
    _out(f"EDGE_PROXY_KEY={secrets.token_urlsafe(36)}")


if __name__ == "__main__":
    app()
