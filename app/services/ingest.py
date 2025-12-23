from __future__ import annotations

from datetime import datetime
from dateutil import parser as dtparser

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.endpoint import Endpoint
from app.models.snapshot import Snapshot, DiskPhysical, DiskVolume, NetworkInterface, LoggedInUser
from app.services.validation import validate_snapshot


async def get_endpoint_by_token(db: AsyncSession, token: str) -> Endpoint | None:
    # Token hashes are bcrypt; need to scan active endpoints and verify.
    # Given modest fleet sizes, this is ok; later we can add a separate HMAC key index.
    q = await db.execute(select(Endpoint).where(Endpoint.is_active.is_(True)))
    endpoints = q.scalars().all()
    from app.core.security import verify_token

    for ep in endpoints:
        if verify_token(token, ep.token_hash):
            return ep
    return None


async def ingest_snapshot(db: AsyncSession, endpoint: Endpoint, payload: dict) -> int:
    validate_snapshot(payload)

    ts = dtparser.isoparse(payload["timestamp_utc"])
    interval_seconds = int(payload["interval_seconds"])

    cpu = payload.get("cpu")
    mem = payload.get("memory")
    users = payload.get("users")

    snap = Snapshot(
        endpoint_id=endpoint.id,
        schema_version=str(payload.get("schema_version")),
        timestamp_utc=ts,
        interval_seconds=interval_seconds,
        cpu_utilization_pct=cpu.get("utilization_pct") if cpu else None,
        cpu_idle_pct=cpu.get("idle_pct") if cpu else None,
        mem_total_bytes=mem.get("total_bytes") if mem else None,
        mem_used_bytes=mem.get("used_bytes") if mem else None,
        mem_free_bytes=mem.get("free_bytes") if mem else None,
        mem_used_pct=mem.get("used_pct") if mem else None,
        users_count=users.get("count") if users else None,
        raw_payload=payload,
    )

    db.add(snap)
    await db.flush()  # assigns snap.id

    disk = payload.get("disk") or {}
    for p in disk.get("physical", []) or []:
        db.add(
            DiskPhysical(
                snapshot_id=snap.id,
                instance=p["instance"],
                reads_per_sec=float(p["reads_per_sec"]),
                writes_per_sec=float(p["writes_per_sec"]),
                avg_queue_length=float(p["avg_queue_length"]),
                read_latency_ms=float(p["read_latency_ms"]),
                write_latency_ms=float(p["write_latency_ms"]),
                utilization_pct=float(p["utilization_pct"]),
            )
        )

    for v in disk.get("volumes", []) or []:
        db.add(
            DiskVolume(
                snapshot_id=snap.id,
                mount=v["mount"],
                filesystem=v.get("filesystem"),
                total_bytes=int(v["total_bytes"]),
                free_bytes=int(v["free_bytes"]),
                free_pct=float(v["free_pct"]),
            )
        )

    net = payload.get("network") or {}
    for iface in net.get("interfaces", []) or []:
        db.add(
            NetworkInterface(
                snapshot_id=snap.id,
                name=iface["name"],
                bytes_total_per_sec=float(iface["bytes_total_per_sec"]),
                bits_total_per_sec=float(iface["bits_total_per_sec"]),
                utilization_pct=iface.get("utilization_pct"),
                packets_in_errors=int(iface["packets_in_errors"]),
                packets_out_errors=int(iface["packets_out_errors"]),
            )
        )

    if users:
        for u in users.get("logged_in", []) or []:
            db.add(
                LoggedInUser(
                    snapshot_id=snap.id,
                    username=u["username"],
                    session_type=u.get("session_type"),
                )
            )

    endpoint.last_seen = datetime.now(ts.tzinfo)
    endpoint.last_interval_seconds = interval_seconds
    endpoint.hostname = payload["host"]["hostname"]
    endpoint.machine_id = payload["host"]["machine_id"]

    await db.commit()
    return snap.id
