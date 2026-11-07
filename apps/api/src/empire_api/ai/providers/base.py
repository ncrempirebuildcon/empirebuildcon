"""The provider interface (D-059). A new provider is one class with these two methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Protocol

EMBEDDING_DIMENSIONS: Final = 1024  # bge-m3; knowledge_chunk.embedding is vector(1024)


class ProviderBusyError(Exception):
    """The provider can't answer now: daily allocation used, rate limited, timeout, 5xx.
    The caller falls back (the chat's "busy" reply; the indexer retries via the outbox).
    The message is a code only, never content."""


class ProviderError(Exception):
    """The provider refused the request as sent (4xx other than limits). Code-only message."""


@dataclass(frozen=True)
class ChatResult:
    text: str
    prompt_tokens: int
    completion_tokens: int


class AIProvider(Protocol):
    name: str
    #: Neurons per million tokens, for the daily guard (ai.store.add_usage).
    embed_rate: float
    chat_in_rate: float
    chat_out_rate: float
    # Below this cosine similarity a chunk isn't about the question (depends on the embedder).
    min_score: float

    def embed(self, texts: list[str]) -> list[list[float]]:
        """One 1024-number vector per text, in order."""
        ...

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int) -> ChatResult:
        """`messages` in the OpenAI shape: [{"role": "system"|"user"|"assistant", "content": …}]."""
        ...
