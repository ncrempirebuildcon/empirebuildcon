"""The knowledge table (pgvector) and the daily neuron guard (D-059).

`knowledge_chunk` exists only where pgvector is installed (migration 0008), so it is used through
SQL and every entry point checks `available(db)` first.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from empire_api.ai.models import AiUsageDay
from empire_api.ids import new_id
from empire_api.timeutil import today_ist


@dataclass(frozen=True)
class Chunk:
    source_type: str
    source_id: uuid.UUID
    url: str
    title: str
    position: int
    body: str
    tokens: int
    content_hash: str


@dataclass(frozen=True)
class Hit:
    url: str
    title: str
    body: str
    score: float


def available(db: Session) -> bool:
    return bool(db.scalar(text("SELECT to_regclass('public.knowledge_chunk') IS NOT NULL")))


def _vector(values: list[float]) -> str:
    return "[" + ",".join(f"{v:.6f}" for v in values) + "]"


def hashes_for(db: Session, source_type: str, source_id: uuid.UUID) -> list[str]:
    return list(
        db.scalars(
            text(
                "SELECT content_hash FROM knowledge_chunk WHERE source_type = :t AND source_id = :i"
                " ORDER BY position"
            ),
            {"t": source_type, "i": source_id},
        )
    )


def delete_source(db: Session, source_type: str, source_id: uuid.UUID) -> int:
    result = db.execute(
        text("DELETE FROM knowledge_chunk WHERE source_type = :t AND source_id = :i"),
        {"t": source_type, "i": source_id},
    )
    return int(getattr(result, "rowcount", 0) or 0)


def insert_chunks(db: Session, chunks: list[Chunk], vectors: list[list[float]]) -> None:
    for chunk, vector in zip(chunks, vectors, strict=True):
        db.execute(
            text(
                "INSERT INTO knowledge_chunk (id, source_type, source_id, url, title, position,"
                " body, tokens, content_hash, embedding) VALUES (:id, :t, :i, :url, :title, :pos,"
                " :body, :tokens, :hash, CAST(:emb AS vector))"
            ),
            {
                "id": new_id(),
                "t": chunk.source_type,
                "i": chunk.source_id,
                "url": chunk.url,
                "title": chunk.title,
                "pos": chunk.position,
                "body": chunk.body,
                "tokens": chunk.tokens,
                "hash": chunk.content_hash,
                "emb": _vector(vector),
            },
        )


def search(
    db: Session, vector: list[float], *, limit: int = 4, prefer_url: str | None = None
) -> list[Hit]:
    """Nearest chunks by cosine. A chunk from the visitor's current page gets a small boost."""
    rows = db.execute(
        text(
            "SELECT url, title, body, 1 - (embedding <=> CAST(:v AS vector)) AS score"
            " FROM knowledge_chunk ORDER BY embedding <=> CAST(:v AS vector) LIMIT :k"
        ),
        {"v": _vector(vector), "k": limit * 3},
    ).all()
    hits = [
        Hit(
            url=r.url,
            title=r.title,
            body=r.body,
            score=float(r.score) + (0.05 if r.url == prefer_url else 0.0),
        )
        for r in rows
    ]
    return sorted(hits, key=lambda h: h.score, reverse=True)[:limit]


def sources(db: Session) -> list[tuple[str, uuid.UUID]]:
    rows = db.execute(text("SELECT DISTINCT source_type, source_id FROM knowledge_chunk")).all()
    return [(r.source_type, r.source_id) for r in rows]


def count_chunks(db: Session) -> int:
    return int(db.scalar(text("SELECT count(*) FROM knowledge_chunk")) or 0)


# ── Daily guard ────────────────────────────────────────────────────────────────────────────


def neurons_today(db: Session, today: date | None = None) -> Decimal:
    row = db.get(AiUsageDay, today or today_ist())
    return row.neurons if row else Decimal(0)


def add_usage(
    db: Session,
    *,
    neurons: float,
    answers: int = 0,
    no_answer: int = 0,
    busy: int = 0,
    today: date | None = None,
) -> None:
    """Add to today's counts (one row per day, created on first use; safe under concurrency)."""
    stmt = insert(AiUsageDay).values(
        day=today or today_ist(),
        answers=answers,
        no_answer=no_answer,
        busy=busy,
        neurons=Decimal(f"{neurons:.2f}"),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[AiUsageDay.day],
        set_={
            "answers": AiUsageDay.answers + stmt.excluded.answers,
            "no_answer": AiUsageDay.no_answer + stmt.excluded.no_answer,
            "busy": AiUsageDay.busy + stmt.excluded.busy,
            "neurons": AiUsageDay.neurons + stmt.excluded.neurons,
        },
    )
    db.execute(stmt)
