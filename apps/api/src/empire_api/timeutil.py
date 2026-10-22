"""Time helpers. Everything is stored and compared in UTC (ARCHITECTURE §6); IST is display-only,
except for calendar rules staff see in IST ("today", "this month")."""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Final
from zoneinfo import ZoneInfo

IST: Final = ZoneInfo("Asia/Kolkata")


def utcnow() -> datetime:
    """Timezone-aware 'now' in UTC. Never use naive datetimes (CODE_STYLE §4)."""
    return datetime.now(UTC)


def today_ist() -> date:
    """Today's date in India, for rules like "an update can't be dated in the future"."""
    return datetime.now(IST).date()
