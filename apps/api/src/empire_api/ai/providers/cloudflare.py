"""Cloudflare Workers AI on the Workers Free plan (D-059).

Endpoints (developers.cloudflare.com/workers-ai, read 7 Nov 2026):
  - chat:       POST https://api.cloudflare.com/client/v4/accounts/{id}/ai/v1/chat/completions
                (OpenAI-compatible: {"model", "messages", "max_tokens"} →
                choices[0].message.content, usage.prompt_tokens / completion_tokens)
  - embeddings: POST https://api.cloudflare.com/client/v4/accounts/{id}/ai/run/@cf/baai/bge-m3
                with {"text": [...]} → result.data (one vector per text). TODO(phase-7): the live
                dry run (task 7.4, `empire-api ai smoke`) confirms the exact response shape.
  - Neuron rates from the Workers AI pricing page (7 Nov 2026): qwen3-30b-a3b-fp8 4,625 in /
    30,475 out per million tokens; bge-m3 1,075 per million input tokens.

On the Free plan the 10,000 daily neurons are a hard cap: past it, requests fail instead of
billing. Those failures, rate limits (429), timeouts and 5xx become ProviderBusyError.

SECURITY: the token goes only in the Authorization header to api.cloudflare.com; errors carry
codes only (never the prompt, the answer or the token).
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Final

import httpx

from empire_api.ai.providers.base import (
    EMBEDDING_DIMENSIONS,
    ChatResult,
    ProviderBusyError,
    ProviderError,
)
from empire_api.config import Settings

BASE: Final = "https://api.cloudflare.com/client/v4/accounts"
# WHY 7 s: the website's functions time out at 10 s by default (Netlify), and embedding plus
# retrieval take about 0.5 s more (PLAN.md, dry run).
CHAT_TIMEOUT: Final = httpx.Timeout(7.0, connect=3.0)
# PERF: an `ai.reindex` event runs inside the outbox drain, so later events in the batch wait
# behind a slow call; short, and a timeout is retried later (busy).
EMBED_TIMEOUT: Final = httpx.Timeout(6.0, connect=3.0)


def _code(response: httpx.Response) -> str:
    try:
        errors = response.json().get("errors") or []
        first = errors[0] if errors and isinstance(errors[0], dict) else {}
        code = first.get("code")
    except ValueError, AttributeError, IndexError:
        code = None
    return f"cf_{code}" if isinstance(code, int) else f"cf_http_{response.status_code}"


def _raise_for(response: httpx.Response) -> None:
    if response.status_code == 200:
        return
    code = _code(response)
    # Limits, the daily allocation, temporary faults: try later or fall back.
    if response.status_code in (408, 429) or response.status_code >= 500:
        raise ProviderBusyError(code)
    # WHY: Workers AI may report a used-up free allocation as a 4xx with an error code rather
    # than a 429. TODO(phase-7): these three codes are an unverified guess until the live dry
    # run (task 7.4) shows the real one; until then the daily guard stops us well before it.
    if code in {"cf_3036", "cf_3040", "cf_4006"}:
        raise ProviderBusyError(code)
    raise ProviderError(code)


class CloudflareProvider:
    name = "cloudflare"
    embed_rate = 1075.0
    chat_in_rate = 4625.0
    chat_out_rate = 30475.0

    def __init__(
        self,
        account_id: str,
        token: str,
        *,
        chat_model: str,
        embed_model: str,
        client_factory: Callable[[httpx.Timeout], httpx.Client] | None = None,
    ) -> None:
        self._account = account_id
        self._token = token
        self._chat_model = chat_model
        self._embed_model = embed_model
        self._factory = client_factory or (
            lambda timeout: httpx.Client(timeout=timeout, follow_redirects=False)
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> CloudflareProvider:
        return cls(
            settings.cloudflare_account_id.strip(),
            settings.cloudflare_ai_token.get_secret_value().strip(),
            chat_model=settings.ai_chat_model,
            embed_model=settings.ai_embed_model,
        )

    def __repr__(self) -> str:  # SECURITY
        return "CloudflareProvider(token=***)"

    def _post(self, path: str, body: dict[str, Any], timeout: httpx.Timeout) -> dict[str, Any]:
        try:
            with self._factory(timeout) as client:
                response = client.post(
                    f"{BASE}/{self._account}/ai/{path}",
                    json=body,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
        except httpx.TimeoutException:
            raise ProviderBusyError("cf_timeout") from None
        except httpx.HTTPError as exc:
            raise ProviderBusyError(f"cf_unreachable_{type(exc).__name__}") from None
        _raise_for(response)
        try:
            data = response.json()
        except ValueError:
            raise ProviderBusyError("cf_bad_json") from None
        return data if isinstance(data, dict) else {}

    def embed(self, texts: list[str]) -> list[list[float]]:
        data = self._post(f"run/{self._embed_model}", {"text": texts}, EMBED_TIMEOUT)
        result = data.get("result", data)
        vectors = result.get("data") if isinstance(result, dict) else None
        if (
            not isinstance(vectors, list)
            or len(vectors) != len(texts)
            or any(not isinstance(v, list) or len(v) != EMBEDDING_DIMENSIONS for v in vectors)
        ):
            raise ProviderError("cf_embedding_shape")
        return [[float(x) for x in v] for v in vectors]

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int) -> ChatResult:
        data = self._post(
            "v1/chat/completions",
            {"model": self._chat_model, "messages": messages, "max_tokens": max_tokens},
            CHAT_TIMEOUT,
        )
        try:
            text = data["choices"][0]["message"]["content"]
        except KeyError, IndexError, TypeError:
            raise ProviderError("cf_chat_shape") from None
        raw_usage = data.get("usage")
        usage: dict[str, Any] = raw_usage if isinstance(raw_usage, dict) else {}
        return ChatResult(
            text=str(text or ""),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
        )
