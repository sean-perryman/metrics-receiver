from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.core.config import settings as app_settings
from app.db.session import AsyncSessionLocal
from app.models.endpoint import Endpoint
from app.models.alert import AlertEvent, AlertType, AlertDedup
from app.models.setting import Setting
from app.models.snapshot import Snapshot, DiskVolume


DEFAULTS = {
    "alerts": {
        "enabled": True,
        "dedup_minutes": 15,
        "low_disk_free_pct_threshold": 10.0,
        "heartbeat_grace_multiplier": 3,
        "heartbeat_min_grace_seconds": 120,
        "notify": {
            "email": {"enabled": False, "to": []},
            "webhook": {"enabled": False, "url": None},
            "discord": {"enabled": False, "webhook_url": None},
        },
    }
}


async def _get_settings(db: AsyncSession) -> dict:
    q = await db.execute(select(Setting).where(Setting.key == "global"))
    row = q.scalars().first()
    merged = json.loads(json.dumps(DEFAULTS))
    if row:
        # shallow merge
        merged.update(row.value or {})
    return merged


async def _should_fire(db: AsyncSession, key: str, dedup_minutes: int) -> bool:
    q = await db.execute(select(AlertDedup).where(AlertDedup.key == key))
    state = q.scalars().first()
    now = datetime.now(timezone.utc)
    if not state:
        db.add(AlertDedup(key=key, last_fired_at=now, is_active=True))
        await db.commit()
        return True

    if now - state.last_fired_at >= timedelta(minutes=dedup_minutes):
        state.last_fired_at = now
        await db.commit()
        return True
    return False


async def _send_notifications(cfg: dict, subject: str, message: str) -> None:
    notify = cfg["alerts"]["notify"]

    # Email
    if notify.get("email", {}).get("enabled") and notify["email"].get("to"):
        try:
            import smtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["Subject"] = subject
            msg["From"] = app_settings.smtp_from or app_settings.smtp_user or "metrics@localhost"
            msg["To"] = ", ".join(notify["email"]["to"])
            msg.set_content(message)

            host = app_settings.smtp_host
            if host:
                with smtplib.SMTP(host, app_settings.smtp_port) as smtp:
                    smtp.starttls()
                    if app_settings.smtp_user and app_settings.smtp_password:
                        smtp.login(app_settings.smtp_user, app_settings.smtp_password)
                    smtp.send_message(msg)
        except Exception:
            # Avoid crashing scheduler for bad mail config
            pass

    # Generic webhook
    if notify.get("webhook", {}).get("enabled") and notify["webhook"].get("url"):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(notify["webhook"]["url"], json={"subject": subject, "message": message})
        except Exception:
            pass

    # Discord webhook
    if notify.get("discord", {}).get("enabled") and notify["discord"].get("webhook_url"):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(notify["discord"]["webhook_url"], json={"content": f"**{subject}**\n{message}"})
        except Exception:
            pass


async def check_alerts_once() -> None:
    async with AsyncSessionLocal() as db:
        cfg = await _get_settings(db)
        if not cfg["alerts"].get("enabled", True):
            return

        dedup_minutes = int(cfg["alerts"].get("dedup_minutes", 15))

        # 1) Heartbeats
        grace_mult = int(cfg["alerts"].get("heartbeat_grace_multiplier", 3))
        min_grace = int(cfg["alerts"].get("heartbeat_min_grace_seconds", 120))
        now = datetime.now(timezone.utc)

        q = await db.execute(select(Endpoint).where(Endpoint.is_active.is_(True)))
        endpoints = q.scalars().all()
        for ep in endpoints:
            if not ep.last_seen or not ep.last_interval_seconds:
                continue
            grace = max(min_grace, grace_mult * int(ep.last_interval_seconds))
            if (now - ep.last_seen) > timedelta(seconds=grace):
                key = f"heartbeat:{ep.id}"
                if await _should_fire(db, key, dedup_minutes):
                    details = {"endpoint_id": ep.id, "hostname": ep.hostname, "machine_id": ep.machine_id, "last_seen": ep.last_seen.isoformat(), "grace_seconds": grace}
                    db.add(AlertEvent(alert_type=AlertType.heartbeat, endpoint_id=ep.id, details=details))
                    await db.commit()
                    await _send_notifications(cfg, f"Heartbeat missing: {ep.hostname}", json.dumps(details, indent=2))

        # 2) Low disk across all volumes/hosts (latest snapshot per endpoint)
        threshold = float(cfg["alerts"].get("low_disk_free_pct_threshold", 10.0))

        # Latest snapshot per endpoint via subquery
        subq = select(Snapshot.endpoint_id, func.max(Snapshot.timestamp_utc).label("max_ts")).group_by(Snapshot.endpoint_id).subquery()

        q = await db.execute(
            select(DiskVolume, Snapshot.endpoint_id)
            .join(Snapshot, DiskVolume.snapshot_id == Snapshot.id)
            .join(subq, and_(Snapshot.endpoint_id == subq.c.endpoint_id, Snapshot.timestamp_utc == subq.c.max_ts))
            .where(DiskVolume.free_pct < threshold)
        )
        rows = q.all()
        if rows:
            key = f"lowdisk:global:{int(threshold*10)}"
            if await _should_fire(db, key, dedup_minutes):
                items = []
                for vol, endpoint_id in rows:
                    ep = next((e for e in endpoints if e.id == endpoint_id), None)
                    items.append(
                        {
                            "endpoint_id": endpoint_id,
                            "hostname": ep.hostname if ep else None,
                            "machine_id": ep.machine_id if ep else None,
                            "mount": vol.mount,
                            "free_pct": vol.free_pct,
                            "free_bytes": vol.free_bytes,
                            "total_bytes": vol.total_bytes,
                        }
                    )
                details = {"threshold_free_pct": threshold, "volumes": items}
                db.add(AlertEvent(alert_type=AlertType.low_disk, endpoint_id=None, details=details))
                await db.commit()
                await _send_notifications(cfg, "Low disk space detected", json.dumps(details, indent=2))
