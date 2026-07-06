from __future__ import annotations

import asyncio

from app.core.database import SessionLocal
from app.models import CrawlError, TelegramTarget
from app.services.collection_settings import get_collection_settings
from app.telegram.runtime import runtime


class InitialCollectionQueue:
    def __init__(self) -> None:
        self._semaphore: asyncio.Semaphore | None = None
        self._semaphore_size = 0
        self._account_semaphores: dict[int, asyncio.Semaphore] = {}
        self._account_semaphore_size = 0

    async def submit_targets(self, target_ids: list[int]) -> None:
        if not target_ids:
            return
        config = _settings()
        global_semaphore = self._semaphore_for(int(config["max_concurrent_initial_jobs"]))
        account_limit = int(config["max_initial_jobs_per_account"])
        target_accounts = _target_accounts(target_ids)
        tasks = [
            asyncio.create_task(
                self._run_one(
                    target_id,
                    global_semaphore,
                    self._account_semaphore_for(target_accounts.get(target_id), account_limit),
                )
            )
            for target_id in target_ids
        ]
        await asyncio.gather(*tasks)

    async def _run_one(
        self,
        target_id: int,
        global_semaphore: asyncio.Semaphore,
        account_semaphore: asyncio.Semaphore | None,
    ) -> None:
        if account_semaphore is not None:
            async with account_semaphore:
                async with global_semaphore:
                    await self._execute_one(target_id)
            return
        async with global_semaphore:
            await self._execute_one(target_id)

    async def _execute_one(self, target_id: int) -> None:
        config = _settings()
        try:
            _mark_target_status(target_id, "initializing", "")
            try:
                await runtime.sync_target_metadata(target_id)
            except Exception as exc:
                _record_error(target_id, "initial_metadata", exc)
            if config["auto_backfill_on_import"] and int(config["initial_backfill_limit"]) > 0:
                await runtime.backfill_target(
                    target_id,
                    int(config["initial_backfill_limit"]),
                    since_hours=int(config["initial_backfill_window_hours"]),
                )
            if config["auto_start_listening_on_import"] and _target_enabled(target_id):
                await runtime.add_target(target_id)
        except Exception as exc:
            _record_error(target_id, "initial_collection", exc)

    def _semaphore_for(self, size: int) -> asyncio.Semaphore:
        normalized = max(1, size)
        if self._semaphore is None or self._semaphore_size != normalized:
            self._semaphore = asyncio.Semaphore(normalized)
            self._semaphore_size = normalized
        return self._semaphore

    def _account_semaphore_for(self, account_id: int | None, size: int) -> asyncio.Semaphore | None:
        if account_id is None:
            return None
        normalized = max(1, size)
        if self._account_semaphore_size != normalized:
            self._account_semaphores = {}
            self._account_semaphore_size = normalized
        semaphore = self._account_semaphores.get(account_id)
        if semaphore is None:
            semaphore = asyncio.Semaphore(normalized)
            self._account_semaphores[account_id] = semaphore
        return semaphore


def _settings() -> dict[str, object]:
    db = SessionLocal()
    try:
        return get_collection_settings(db)
    finally:
        db.close()


def _target_enabled(target_id: int) -> bool:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        return bool(target and target.enabled)
    finally:
        db.close()


def _target_accounts(target_ids: list[int]) -> dict[int, int | None]:
    db = SessionLocal()
    try:
        rows = db.query(TelegramTarget.id, TelegramTarget.account_id).filter(TelegramTarget.id.in_(target_ids)).all()
        return {int(target_id): int(account_id) if account_id is not None else None for target_id, account_id in rows}
    finally:
        db.close()


def _mark_target_status(target_id: int, status: str, error: str = "") -> None:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        if target:
            target.status = status
            target.last_error = error
            db.commit()
    finally:
        db.close()


def _record_error(target_id: int, stage: str, error: Exception) -> None:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        if target:
            target.status = "error"
            target.last_error = str(error)
        db.add(
            CrawlError(
                account_id=target.account_id if target else None,
                target_id=target_id,
                stage=stage,
                error_type=error.__class__.__name__,
                error_message=str(error),
                retryable=True,
            )
        )
        db.commit()
    finally:
        db.close()


initial_collection_queue = InitialCollectionQueue()
