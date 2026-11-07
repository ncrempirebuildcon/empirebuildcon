"""`empire-api`: admin and developer commands (run with `uv run empire-api --help`).

Commands:
  create-superadmin  One-time: create the owner's account and print a setup link (D-009).
  create-user        Development/test only: a staff account with a password from stdin.
  reset-two-factor   Break-glass: remove an account's two-factor when nobody can sign in to
                     reset it in the CMS (lost phone and recovery codes). Audited, emailed.
  seed               Feature flags, default settings, the amenity catalogue, and the system and
                     legal pages as drafts (legal text: the D-017 placeholder) (idempotent);
                     in development and test also the draft consent texts (D-017).
                     --sample also adds sample projects (development and demos; D-015),
                     with the fake media store SAMPLE placeholder tiles in their photos,
                     twelve sample leads with a few site visits, a sample post, offer and
                     FAQs (no testimonials, ever), and four "Sample …" staff accounts in
                     development and test (invited: no password, can't sign in).
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

from empire_api.ai import indexer, store
from empire_api.ai.providers import get_provider
from empire_api.ai.providers.base import ProviderBusyError, ProviderError
from empire_api.config import Settings, get_settings
from empire_api.content.consent import seed_consent_texts
from empire_api.content.seed import (
    SampleContentRefusedError,
    seed_pages,
    seed_sample_content,
)
from empire_api.db import get_sessionmaker
from empire_api.leads.seed import SampleLeadsRefusedError, seed_sample_leads
from empire_api.media.seed import seed_sample_media
from empire_api.projects.seed import SampleRefusedError, seed_amenities, seed_sample
from empire_api.site_settings.defaults import seed_settings
from empire_api.site_settings.flags import seed_flags
from empire_api.users import passwords, service
from empire_api.users.models import User
from empire_api.users.roles import ROLE_KEYS
from empire_api.users.seed import SampleUsersRefusedError, seed_sample_users

app = typer.Typer(help="Empire API admin commands.", no_args_is_help=True, add_completion=False)
ai_app = typer.Typer(help="The AI assistant's knowledge index (D-059).", no_args_is_help=True)
app.add_typer(ai_app, name="ai")


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


@app.command("reset-two-factor")
def reset_two_factor(
    email: Annotated[str, typer.Option(help="The account whose authenticator is lost")],
) -> None:
    """Break-glass: remove an account's two-factor and sign it out everywhere.

    For when the only super-admin lost both their phone and their recovery codes, so nobody can
    use the CMS's "Reset two-factor". Needs shell access to the server (the same trust as
    create-superadmin). Audited with no actor, and the person gets the security email. With the
    admin_2fa flag on, their next sign-in asks them to set two-factor up again.
    """
    with get_sessionmaker()() as db:
        user = service.find_user_by_email(db, email)
        if user is None:
            _fail("No staff account with this email.")
            return
        service.admin_reset_two_factor(db, user, actor_id=None, meta=None)
    _out(
        "Two-factor removed and every session signed out. The security email goes out with the "
        "next outbox run."
    )


@app.command("seed")
def seed(
    sample: Annotated[
        bool, typer.Option("--sample", help="Also add sample projects (never in production)")
    ] = False,
) -> None:
    """Create feature flags, default settings and the amenity catalogue. Safe to run again.

    In development and test it also adds the draft consent texts, current, so the forms work
    (D-017). Staging and production get none: the owner publishes approved wording, and until
    then public intake answers 503.

    It also adds the system pages (home, projects, about, contact) and the legal pages (privacy,
    terms, disclaimer) as drafts; the legal pages hold only the D-017 placeholder.

    `--sample` adds "Sample City" and "Sample — Project A/B" for development and demos, twelve
    "Sample Lead N" leads with site visits, and a SAMPLE post, offer and FAQs. They are marked
    is_sample, stay drafts (or switched off), and all of it is refused when APP_ENV is
    production (D-015). It never adds a testimonial. In development and test it also adds four
    "Sample …" staff accounts with no password (they can't sign in, and no email is queued).
    """
    if sample and get_settings().app_env == "production":
        _fail("Sample data is never added in production (D-015).")
    with get_sessionmaker()() as db:
        flags_added = seed_flags(db)
        settings_added = seed_settings(db)
        amenities_added = seed_amenities(db)
        texts_added = seed_consent_texts(db)
        pages_added = seed_pages(db)
        db.commit()
    _out(
        f"Seeded: {flags_added} new flags, {settings_added} new settings groups, "
        f"{amenities_added} new amenities, {texts_added} draft consent texts, "
        f"{pages_added} system and legal pages (drafts)."
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
        _seed_sample_media()
        _seed_sample_leads()
        _seed_sample_content()
        _seed_sample_users()


def _seed_sample_users() -> None:
    with get_sessionmaker()() as db:
        try:
            result = seed_sample_users(db)
        except SampleUsersRefusedError as exc:
            _out(f"Sample accounts skipped: {exc}")
            return
        db.commit()
    _out(
        f"Sample accounts: {result.added} added, {result.skipped} already there (invited, no "
        "password, can't sign in)."
    )


def _seed_sample_content() -> None:
    with get_sessionmaker()() as db:
        try:
            content = seed_sample_content(db)
        except SampleContentRefusedError as exc:
            _fail(str(exc))
            return
        db.commit()
    _out(
        f"Sample content: {content.posts} post, {content.offers} offer and {content.faqs} FAQs "
        "added (all marked is_sample; no testimonials)."
    )


def _seed_sample_leads() -> None:
    with get_sessionmaker()() as db:
        try:
            leads = seed_sample_leads(db)
        except SampleLeadsRefusedError as exc:
            _fail(str(exc))
            return
        db.commit()
    _out(
        f"Sample leads: {leads.added} added, {leads.skipped} already there or skipped, "
        f"{leads.visits} site visits (all marked is_sample)."
    )


def _seed_sample_media() -> None:
    with get_sessionmaker()() as db:
        media = seed_sample_media(db)
        db.commit()
    if media.store != "fake":
        _out("Sample media skipped: placeholder tiles are only made with the fake media store.")
    else:
        _out(
            f"Sample media: {media.added} SAMPLE placeholder tiles added, "
            f"{media.skipped_projects} projects already had photos."
        )


@app.command("openapi")
def openapi(
    out: Annotated[Path, typer.Option(help="Where to write the JSON spec")] = Path("openapi.json"),
) -> None:
    """Write the OpenAPI spec generated from the code (source of truth from Phase 3, D-020).

    WHY the fake media store, the dev email transport and APP_ENV=development are forced: the
    spec then always lists the development-only dev-media and dev-mail routes, whatever
    CLOUDINARY_URL, EMAIL_API_KEY or APP_ENV a developer has set, so the committed client never
    changes with someone's local settings.
    """
    from empire_api.main import create_app  # noqa: PLC0415 — only this command needs the app

    forced = {"media_store": "fake", "email_transport": "dev", "app_env": "development"}
    settings = Settings(**{**get_settings().model_dump(), **forced})
    spec = create_app(settings).openapi()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
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


@ai_app.command("reindex")
def ai_reindex() -> None:
    """Bring the knowledge index up to date with live content. Safe to run again: unchanged
    items cost nothing. Needs AI_PROVIDER and pgvector (SETUP, RUNBOOK §6d)."""
    provider = get_provider()
    if provider is None:
        _fail("AI is off: set AI_PROVIDER (and its credentials) first.")
        return
    with get_sessionmaker()() as db:
        if not store.available(db):
            _fail("knowledge_chunk is missing: pgvector isn't installed in this database.")
            return
        try:
            result = indexer.reindex_all(db, provider)
        except (ProviderBusyError, ProviderError) as exc:
            _fail(f"Stopped: the provider answered {exc}. Items done so far are kept.")
            return
        _out(
            f"Indexed {result.indexed} items ({result.chunks} chunks, about "
            f"{result.neurons:.1f} neurons); {result.unchanged} unchanged; "
            f"{result.removed} removed. Chunks now: {store.count_chunks(db)}."
        )


@ai_app.command("status")
def ai_status() -> None:
    """The provider in use, the number of chunks and today's estimated neurons."""
    provider = get_provider()
    with get_sessionmaker()() as db:
        if not store.available(db):
            _fail("knowledge_chunk is missing: pgvector isn't installed in this database.")
            return
        _out(
            f"Provider: {provider.name if provider else 'off'}. Chunks: {store.count_chunks(db)}. "
            f"Neurons today: {store.neurons_today(db)} of a "
            f"{get_settings().ai_daily_neuron_guard} guard."
        )
