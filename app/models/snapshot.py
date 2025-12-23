from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, Float, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Snapshot(Base):
    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)

    endpoint_id: Mapped[int] = mapped_column(ForeignKey("endpoints.id", ondelete="CASCADE"), index=True, nullable=False)
    schema_version: Mapped[str] = mapped_column(String(16), nullable=False)

    timestamp_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True, nullable=False)
    interval_seconds: Mapped[int] = mapped_column(Integer, nullable=False)

    cpu_utilization_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_idle_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    mem_total_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mem_used_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mem_free_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mem_used_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    users_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    endpoint = relationship("Endpoint", backref="snapshots")


class DiskPhysical(Base):
    __tablename__ = "disk_physical"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True, nullable=False)

    instance: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    reads_per_sec: Mapped[float] = mapped_column(Float, nullable=False)
    writes_per_sec: Mapped[float] = mapped_column(Float, nullable=False)
    avg_queue_length: Mapped[float] = mapped_column(Float, nullable=False)
    read_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    write_latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    utilization_pct: Mapped[float] = mapped_column(Float, nullable=False)


class DiskVolume(Base):
    __tablename__ = "disk_volumes"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True, nullable=False)

    mount: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    filesystem: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    free_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    free_pct: Mapped[float] = mapped_column(Float, nullable=False)


class NetworkInterface(Base):
    __tablename__ = "network_interfaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True, nullable=False)

    name: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    bytes_total_per_sec: Mapped[float] = mapped_column(Float, nullable=False)
    bits_total_per_sec: Mapped[float] = mapped_column(Float, nullable=False)
    utilization_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    packets_in_errors: Mapped[int] = mapped_column(Integer, nullable=False)
    packets_out_errors: Mapped[int] = mapped_column(Integer, nullable=False)


class LoggedInUser(Base):
    __tablename__ = "logged_in_users"

    id: Mapped[int] = mapped_column(primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(ForeignKey("snapshots.id", ondelete="CASCADE"), index=True, nullable=False)

    username: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    session_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
