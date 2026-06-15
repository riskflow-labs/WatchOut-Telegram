from __future__ import annotations

import asyncio

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import CrawlError, TelegramTarget
from app.telegram.runtime import runtime


class BackfillScheduler:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        if not settings.enable_scheduler or not settings.backfill_enabled:
            return
        if self._scheduler and self._scheduler.running:
            return
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scheduler.add_job(
            self.run_once,
            "interval",
            seconds=settings.backfill_interval_seconds,
            next_run_time=None,
            id="telegram_periodic_backfill",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        asyncio.create_task(self._delayed_first_run())

    async def shutdown(self) -> None:
        if self._scheduler and self._scheduler.running:
            self._scheduler.shutdown(wait=False)
        self._scheduler = None

    async def _delayed_first_run(self) -> None:
        await asyncio.sleep(max(0, settings.backfill_startup_delay_seconds))
        await self.run_once()

    async def run_once(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            for target_id in _enabled_target_ids():
                try:
                    await runtime.backfill_target(target_id, settings.backfill_limit_per_target)
                except Exception as exc:
                    _record_crawl_error(
                        target_id=target_id,
                        stage="scheduled_backfill",
                        error=exc,
                        retryable=True,
                    )


def _enabled_target_ids() -> list[int]:
    db = SessionLocal()
    try:
        rows = (
            db.query(TelegramTarget.id)
            .filter(TelegramTarget.enabled == True)  # noqa: E712
            .order_by(TelegramTarget.id.asc())
            .all()
        )
        return [row.id for row in rows]
    finally:
        db.close()


def _record_crawl_error(
    *,
    target_id: int | None,
    stage: str,
    error: Exception,
    retryable: bool,
) -> None:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id) if target_id else None
        db.add(
            CrawlError(
                account_id=target.account_id if target else None,
                target_id=target_id,
                stage=stage,
                error_type=error.__class__.__name__,
                error_message=str(error),
                retryable=retryable,
            )
        )
        db.commit()
    finally:
        db.close()


backfill_scheduler = BackfillScheduler()
