"""Time helpers. Everything is stored and compared in UTC (ARCHITECTURE §6); IST is display-only."""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Timezone-aware 'now' in UTC. Never use naive datetimes (CODE_STYLE §4)."""
    return datetime.now(UTC)
