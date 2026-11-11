"""A deterministic provider for tests, CI and local runs (no network, no key). D-059."""

from __future__ import annotations

import hashlib
import math
import re

from empire_api.ai.providers.base import EMBEDDING_DIMENSIONS, ChatResult

_WORD = re.compile(r"\w+", re.UNICODE)


def _vector(text: str) -> list[float]:
    """Bag of hashed words, normalised: texts sharing words point the same way."""
    values = [0.0] * EMBEDDING_DIMENSIONS
    for word in _WORD.findall(text.lower()):
        if len(word) < 4 or word in _COMMON:
            continue  # WHY: short and common words would make every chunk look alike
        values[int(hashlib.sha256(word.encode()).hexdigest(), 16) % EMBEDDING_DIMENSIONS] = 1.0
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


_COMMON = frozenset(
    {
        "does",
        "have",
        "with",
        "what",
        "where",
        "which",
        "there",
        "this",
        "that",
        "your",
        "from",
        "about",
        "sample",
        "page",
        "project",
        "e2e",
    }
)


class FakeProvider:
    name = "fake"
    embed_rate = 1075.0
    chat_in_rate = 4625.0
    chat_out_rate = 30475.0
    min_score = 0.05  # bag of words: one shared word in a long chunk scores about 0.1

    def __init__(self) -> None:
        self.calls: list[str] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(f"embed:{len(texts)}")
        return [_vector(t) for t in texts]

    def chat(self, messages: list[dict[str, str]], *, max_tokens: int) -> ChatResult:
        """Answers with the first source line it was given, cited as [1] (shape only)."""
        self.calls.append("chat")
        system = messages[0]["content"] if messages else ""
        match = re.search(r"^\[1\] [^\n]*", system, re.MULTILINE)
        text = f"{match.group(0)[4:200]} [1]" if match else "NO_ANSWER"
        prompt = sum(len(m["content"]) for m in messages) // 4
        return ChatResult(text=text, prompt_tokens=prompt, completion_tokens=len(text) // 4)
