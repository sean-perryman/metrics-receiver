from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.services.alerts import check_alerts_once

SCHEDULER: AsyncIOScheduler | None = None


def start_scheduler(app) -> None:
    global SCHEDULER
    if not settings.scheduler_enabled:
        return

    if SCHEDULER:
        return

    scheduler = AsyncIOScheduler()
    scheduler.add_job(check_alerts_once, "interval", seconds=settings.scheduler_interval_seconds, id="alerts")
    scheduler.start()
    SCHEDULER = scheduler
