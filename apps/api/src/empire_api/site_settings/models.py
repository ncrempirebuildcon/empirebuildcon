"""Settings groups (one JSON document per group) and feature flags."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from empire_api.db import Base


class Setting(Base):
    """One settings group: company | contacts | social | tracking | lead_routing | … (contract
    schema SettingsGroup). Keys starting with `system.` are internal bookkeeping."""

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(server_default=text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column()


class FeatureFlag(Base):
    """A switch staff can flip without a deploy (CODE_STYLE §6).

    `is_locked` flags belong to features that are not built yet; they can't be switched on.
    """

    __tablename__ = "feature_flag"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    enabled: Mapped[bool] = mapped_column(server_default=text("false"))
    description: Mapped[str] = mapped_column(Text)
    is_public: Mapped[bool] = mapped_column(server_default=text("false"))
    is_locked: Mapped[bool] = mapped_column(server_default=text("false"))
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
    updated_by: Mapped[uuid.UUID | None] = mapped_column()
