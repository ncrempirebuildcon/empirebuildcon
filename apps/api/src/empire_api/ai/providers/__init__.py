"""Model providers for the assistant (D-059). `get_provider()` returns None while AI is off."""

from __future__ import annotations

from functools import lru_cache

from empire_api.ai.providers.base import AIProvider
from empire_api.ai.providers.cloudflare import CloudflareProvider
from empire_api.ai.providers.fake import FakeProvider
from empire_api.config import get_settings


@lru_cache(maxsize=1)
def get_provider() -> AIProvider | None:
    settings = get_settings()
    kind = settings.ai_provider.strip().lower()
    if kind == "fake":
        return FakeProvider()
    if kind == "cloudflare" and settings.cloudflare_ai_ready:
        return CloudflareProvider.from_settings(settings)
    return None
