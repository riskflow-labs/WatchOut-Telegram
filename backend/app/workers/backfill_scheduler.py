from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import CrawlError, TelegramAccount, TelegramTarget
from app.services.collection_settings import get_collection_settings
from app.telegram.runtime import runtime


class BackfillScheduler:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        config = _collection_settings()
        if not settings.enable_scheduler or not config["backfill_enabled"]:
            return
        if self._scheduler and self._scheduler.running:
            return
        self._start_with_config(config)

    def apply_config(self, config: dict[str, object]) -> None:
        if not settings.enable_scheduler or not config["backfill_enabled"]:
            if self._scheduler and self._scheduler.running:
                self._scheduler.shutdown(wait=False)
            self._scheduler = None
            return
        if not self._scheduler or not self._scheduler.running:
            self._start_with_config(config)
            return
        job_id = "telegram_periodic_backfill"
        if not self._scheduler.get_job(job_id):
            self._start_with_config(config)
            return
        self._scheduler.reschedule_job(job_id, trigger="interval", seconds=int(config["backfill_interval_seconds"]))
        self._scheduler.modify_job(job_id, next_run_time=_next_run_time(config))

    def _start_with_config(self, config: dict[str, object]) -> None:
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scheduler.add_job(
            self.run_once,
            "interval",
            seconds=int(config["backfill_interval_seconds"]),
            next_run_time=_next_run_time(config),
            id="telegram_periodic_backfill",
            max_instances=1,
            coalesce=True,
        )
        self._scheduler.start()
        try:
            asyncio.get_running_loop().create_task(self._delayed_first_run())
        except RuntimeError:
            # Configuration can be saved from a sync worker thread during tests or
            # older deployments. The interval job is still registered; the delayed
            # first run will be skipped instead of failing the save request.
            pass

    def status(self) -> dict[str, object]:
        job = self._scheduler.get_job("telegram_periodic_backfill") if self._scheduler else None
        return {
            "running": bool(self._scheduler and self._scheduler.running),
            "locked": self._lock.locked(),
            "next_run_at": job.next_run_time.isoformat() if job and job.next_run_time else "",
        }

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
        config = _collection_settings()
        if not settings.enable_scheduler or not config["backfill_enabled"]:
            return
        async with self._lock:
            for account_id, target_ids in _enabled_targets_by_account().items():
                try:
                    await runtime.backfill_targets_for_account(
                        account_id,
                        target_ids,
                        int(config["backfill_limit_per_target"]),
                        since_hours=config["backfill_window_hours"],
                    )
                except Exception as exc:
                    _record_crawl_error(
                        account_id=account_id,
                        target_id=None,
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


def _enabled_targets_by_account() -> dict[int, list[int]]:
    db = SessionLocal()
    try:
        accounts = (
            db.query(TelegramAccount)
            .filter(TelegramAccount.status == "authorized", TelegramAccount.is_active == True)  # noqa: E712
            .order_by(TelegramAccount.id.asc())
            .all()
        )
        account_ids = [account.id for account in accounts]
        if not account_ids:
            return {}
        grouped = {account_id: [] for account_id in account_ids}
        fallback_index = 0
        targets = (
            db.query(TelegramTarget)
            .filter(TelegramTarget.enabled == True)  # noqa: E712
            .order_by(TelegramTarget.account_id.asc().nulls_last(), TelegramTarget.id.asc())
            .all()
        )
        for target in targets:
            if target.account_id in grouped:
                grouped[target.account_id].append(target.id)
                continue
            account_id = account_ids[fallback_index % len(account_ids)]
            fallback_index += 1
            target.account_id = account_id
            grouped[account_id].append(target.id)
        db.commit()
        return {account_id: target_ids for account_id, target_ids in grouped.items() if target_ids}
    finally:
        db.close()


def _collection_settings() -> dict[str, object]:
    db = SessionLocal()
    try:
        return get_collection_settings(db)
    finally:
        db.close()


def _next_run_time(config: dict[str, object]) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=int(config["backfill_interval_seconds"]))


def _record_crawl_error(
    *,
    account_id: int | None = None,
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
                account_id=account_id if account_id is not None else target.account_id if target else None,
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
