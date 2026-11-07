"""ORM model for the daily counts (`ai_usage_day`). `knowledge_chunk` is reached with SQL in
store.py, because it exists only where pgvector does (migration 0008)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import Date, Integer, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from empire_api.db import Base


class AiUsageDay(Base):
    """COMPLIANCE: counts only. No message text, ever (D-059)."""

    __tablename__ = "ai_usage_day"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    answers: Mapped[int] = mapped_column(Integer, server_default="0")
    no_answer: Mapped[int] = mapped_column(Integer, server_default="0")
    busy: Mapped[int] = mapped_column(Integer, server_default="0")
    neurons: Mapped[Decimal] = mapped_column(Numeric(10, 2), server_default="0")
