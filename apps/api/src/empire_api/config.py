"""Runtime settings, read once from environment variables (and a local .env file in development).

Collaborators: every module reads settings through `get_settings()`; tests clear its cache.
Implements: SECURITY.md §7 (secrets only in the environment), D-009 (session secret), D-019,
D-033 (media store).

SECURITY: in staging and production the app refuses to start when a secret is missing, too short
or still a `change-me` placeholder from `.env.example`, without CLOUDINARY_URL, or with the fake
media store. Development and test fall back to fixed, clearly-named insecure values (and the
fake media store) so a new developer can run the app with no setup at all.
"""

from __future__ import annotations

import base64
import hashlib
from functools import lru_cache
from typing import Literal, Self

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from empire_api import __version__
from empire_api.media.credentials import parse_cloudinary_url

AppEnv = Literal["development", "test", "staging", "production"]

# WHY: these defaults exist only so `uv run empire-api …` and the test suite work on a fresh clone.
# They are refused in staging and production by `_check_secrets` below.
_DEV_SECRETS = {
    "session_secret": "dev-only-insecure-session-secret-do-not-use-anywhere",
    "data_encryption_key": "dev-only-insecure-data-key",
    "internal_api_key": "dev-only-insecure-internal-key",
    "ip_hash_salt": "dev-only-insecure-ip-salt",
}
_MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    """All configuration in one validated object. Field names map to UPPER_CASE env vars."""

    model_config = SettingsConfigDict(
        env_file=(".env", "../../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        # SECURITY: pydantic otherwise appends `input_value=` (the raw environment, secrets
        # included, truncated) to validation errors, and start-up errors end up in logs.
        hide_input_in_errors=True,
    )

    app_env: AppEnv = "development"
    database_url: str = "postgresql+psycopg://empire:empire@localhost:5432/empire_dev"
    site_url: str = "http://localhost:3000"

    session_secret: SecretStr = SecretStr(_DEV_SECRETS["session_secret"])
    data_encryption_key: SecretStr = SecretStr(_DEV_SECRETS["data_encryption_key"])
    internal_api_key: SecretStr = SecretStr(_DEV_SECRETS["internal_api_key"])
    ip_hash_salt: SecretStr = SecretStr(_DEV_SECRETS["ip_hash_salt"])

    # Comma-separated. Development only: production is same-origin through the web app's proxy.
    cors_allowed_origins: str = ""
    sentry_dsn_api: str = ""

    # SECURITY: shared secret between the web app's proxy (apps/web/src/proxy.ts) and the API.
    # When set, every request except health checks and internal calls must carry it in
    # `X-Empire-Edge-Key`, so nobody can call the API host (e.g. *.run.app) directly, and only
    # then is the client IP read from `X-Empire-Client-IP` (set by our proxy, never the visitor).
    # Empty = local development: no edge check, client IP = socket address. Required in
    # staging/production (see `_check_secrets`).
    edge_proxy_key: SecretStr = SecretStr("")

    db_pool_size: int = Field(default=5, ge=1, le=50)
    worker_drain_interval_seconds: int = Field(default=30, ge=5, le=3600)

    # Media (D-033, media/store.py). SECURITY: CLOUDINARY_URL holds the API secret; it stays on
    # the server. MEDIA_STORE picks the store: "cloudinary", or "fake" (no network, files in
    # MEDIA_DEV_DIR, default apps/api/.media-dev/) for development, tests and the browser suite.
    # Left empty: cloudinary when CLOUDINARY_URL is set, otherwise fake. Staging and production
    # refuse to start without CLOUDINARY_URL or with the fake store.
    cloudinary_url: SecretStr = SecretStr("")
    media_store: Literal["cloudinary", "fake"] | None = None
    media_dev_dir: str = ""

    @property
    def is_production_like(self) -> bool:
        """Staging and production get the strict checks, HSTS and hidden API docs."""
        return self.app_env in ("staging", "production")

    @field_validator("media_store", mode="before")
    @classmethod
    def _blank_store_is_unset(cls, value: object) -> object:
        # WHY: `.env.example` lists `MEDIA_STORE=` empty; that means "choose for me".
        return None if isinstance(value, str) and not value.strip() else value

    @property
    def media_store_kind(self) -> Literal["cloudinary", "fake"]:
        """The active media store (validated in `_check_media`)."""
        if self.media_store is not None:
            return self.media_store
        return "cloudinary" if self.cloudinary_url.get_secret_value().strip() else "fake"

    @property
    def version(self) -> str:
        return __version__

    @property
    def cors_origins(self) -> list[str]:
        if self.is_production_like:
            return []  # INVARIANT: CORS stays closed outside development (SECURITY.md §3)
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    def fernet(self) -> Fernet:
        """Fernet cipher for secrets we must be able to read back (webhook signing keys, links).

        WHY: a developer's placeholder key is not valid Fernet; in development/test we derive a
        valid key from it so the app still runs. Staging/production require a real key.
        """
        raw = self.data_encryption_key.get_secret_value()
        try:
            return Fernet(raw.encode())
        except ValueError:
            if self.is_production_like:
                raise
            derived = base64.urlsafe_b64encode(hashlib.sha256(raw.encode()).digest())
            return Fernet(derived)

    def _media_problems(self) -> list[str]:
        """SECURITY: a live site uses the real store with real credentials (D-033)."""
        problems: list[str] = []
        url = self.cloudinary_url.get_secret_value().strip()
        if url:
            try:
                parse_cloudinary_url(url)
            except ValueError as exc:
                problems.append(str(exc))  # the message names the shape, never the value
        if self.media_store == "cloudinary" and not url:
            problems.append("MEDIA_STORE=cloudinary needs CLOUDINARY_URL")
        if self.is_production_like:
            if not url:
                problems.append("CLOUDINARY_URL must be set")
            if self.media_store == "fake":
                problems.append("MEDIA_STORE=fake is for development and tests only")
        return problems

    def _secret_problems(self) -> list[str]:
        problems: list[str] = []
        if len(self.edge_proxy_key.get_secret_value().encode()) < _MIN_SECRET_BYTES:
            problems.append(f"EDGE_PROXY_KEY must be set (at least {_MIN_SECRET_BYTES} bytes)")
        for name in ("session_secret", "internal_api_key", "ip_hash_salt", "data_encryption_key"):
            value = getattr(self, name).get_secret_value()
            if value == _DEV_SECRETS[name] or value.startswith("change-me"):
                problems.append(f"{name.upper()} is a placeholder")
            elif name != "data_encryption_key" and len(value.encode()) < _MIN_SECRET_BYTES:
                problems.append(f"{name.upper()} must be at least {_MIN_SECRET_BYTES} bytes")
        try:
            Fernet(self.data_encryption_key.get_secret_value().encode())
        except ValueError:
            problems.append("DATA_ENCRYPTION_KEY must be a Fernet key (empire-api gen-secrets)")
        return problems

    @model_validator(mode="after")
    def _check_secrets(self) -> Self:
        problems = self._media_problems()
        if self.is_production_like:
            problems += self._secret_problems()
        if problems:
            # SECURITY: names only, never values, so the message is safe to log.
            raise ValueError("Unsafe configuration: " + "; ".join(sorted(set(problems))))
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """The process-wide settings. Tests call `get_settings.cache_clear()` after changing env."""
    return Settings()
