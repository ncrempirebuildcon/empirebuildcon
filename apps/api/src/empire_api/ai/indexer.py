"""Keep `knowledge_chunk` in step with live content (task 7.1, D-059).

`reindex_source` is idempotent: it rebuilds an item's chunks from the public builders, and only
when their content hashes differ from what is stored does it delete, embed and insert. So an
outbox retry, a second event for the same change, or a full `empire-api ai reindex` costs no
neurons for unchanged items. An item that is no longer live (unpublished, archived, deleted)
builds no chunks, and its stored chunks are deleted.

Errors: `ProviderBusyError` (allocation used, timeout, 5xx) propagates, so the outbox retries
later; the daily guard raises it too, before any call, so indexing can't eat the chat's share.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from empire_api.ai import knowledge, store
from empire_api.ai.providers.base import AIProvider, ProviderBusyError
from empire_api.config import get_settings
from empire_api.content.models import Page, Post
from empire_api.projects.models import Project

MODELS: dict[str, type[Any]] = {"project": Project, "page": Page, "post": Post}
# PERF: one call for a typical item (a project is 2–6 chunks); bge-m3 takes up to 100 texts.
EMBED_BATCH = 32


@dataclass
class ReindexResult:
    indexed: int = 0  # items whose chunks were (re)written
    unchanged: int = 0
    removed: int = 0  # items no longer live whose chunks were deleted
    chunks: int = 0
    neurons: float = 0.0


def _guard(db: Session) -> None:
    if float(store.neurons_today(db)) >= get_settings().ai_daily_neuron_guard:
        raise ProviderBusyError("daily_guard")


def _embed(provider: AIProvider, texts: list[str]) -> list[list[float]]:
    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors.extend(provider.embed(texts[start : start + EMBED_BATCH]))
    return vectors


def reindex_source(
    db: Session,
    provider: AIProvider,
    source_type: str,
    source_id: uuid.UUID,
    result: ReindexResult | None = None,
) -> ReindexResult:
    """Bring one item's chunks up to date. The caller commits."""
    result = result or ReindexResult()
    # INVARIANT: one writer per item at a time (two drains, or the drain and the CLI), so a
    # stale-hash race can't insert the chunks twice. Released at commit.
    db.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"ai:{source_type}:{source_id}"},
    )
    model = MODELS.get(source_type)
    item = db.get(model, source_id) if model else None
    chunks = knowledge.chunks_for(db, source_type, item) if item is not None else []
    stored = store.hashes_for(db, source_type, source_id)
    if not chunks:
        if stored:
            store.delete_source(db, source_type, source_id)
            result.removed += 1
        return result
    if [c.content_hash for c in chunks] == stored:
        result.unchanged += 1
        return result
    _guard(db)
    vectors = _embed(provider, [c.body for c in chunks])
    store.delete_source(db, source_type, source_id)
    store.insert_chunks(db, chunks, vectors)
    tokens = sum(c.tokens for c in chunks)
    neurons = tokens * provider.embed_rate / 1_000_000
    store.add_usage(db, neurons=neurons)
    result.indexed += 1
    result.chunks += len(chunks)
    result.neurons += neurons
    return result


def reindex_all(db: Session, provider: AIProvider) -> ReindexResult:
    """Every project, page and post, committing after each item so a stop keeps what was done.

    Chunks whose item no longer exists at all are removed too.
    """
    result = ReindexResult()
    seen: set[tuple[str, uuid.UUID]] = set()
    for source_type, item in knowledge.all_sources(db):
        seen.add((source_type, item.id))
        reindex_source(db, provider, source_type, item.id, result)
        db.commit()
    for source_type, source_id in store.sources(db):
        if (source_type, source_id) not in seen:
            store.delete_source(db, source_type, source_id)
            result.removed += 1
    db.commit()
    return result
