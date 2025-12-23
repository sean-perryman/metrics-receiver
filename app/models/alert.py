from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, Enum, Boolean, Integer
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AlertType(str, enum.Enum):
    heartbeat = "heartbeat"
    low_disk = "low_disk"


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_type: Mapped[AlertType] = mapped_column(Enum(AlertType, name="alert_type"), nullable=False)
    endpoint_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)


class AlertDedup(Base):
    """Simple dedup state so we don't spam notifications."""

    __tablename__ = "alert_dedup"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_fired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
