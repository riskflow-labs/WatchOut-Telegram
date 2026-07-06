from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.database import SessionLocal
from app.models import TelegramAccount
from app.telegram.login_flow import build_client
from app.telegram.runtime import runtime


class AccountHealthScheduler:
    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._lock = asyncio.Lock()

    def start(self) -> None:
        if not settings.enable_scheduler or not settings.account_health_enabled:
            return
        if self._scheduler and self._scheduler.running:
            return
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scheduler.add_job(
            self.run_once,
            "interval",
            seconds=settings.account_health_interval_seconds,
            next_run_time=None,
            id="telegram_account_health",
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
        await asyncio.sleep(max(0, settings.account_health_startup_delay_seconds))
        await self.run_once()

    async def run_once(self) -> None:
        if self._lock.locked():
            return
        async with self._lock:
            for account_id in _due_account_ids():
                await check_account_health_snapshot(account_id)


async def check_account_health_snapshot(account_id: int) -> None:
    db = SessionLocal()
    try:
        account = db.get(TelegramAccount, account_id)
        if not account:
            return
        running_ids = runtime.running_account_ids()
        target_count = len(account.targets)
        listening_target_count = sum(1 for target in account.targets if target.status == "listening")
        listening = account.id in running_ids
        authorized = False
        me = ""
        message = "账号未授权"

        client = build_client(account)
        try:
            await client.connect()
            authorized = await client.is_user_authorized()
            if authorized:
                user = await client.get_me()
                username = getattr(user, "username", None) or ""
                phone = getattr(user, "phone", None) or account.phone
                me = f"@{username}" if username else str(phone or getattr(user, "id", ""))
                message = "账号可用，Session 有效"
                account.status = "authorized"
                account.last_error = ""
            else:
                account.status = "unauthorized"
                account.last_error = "Session 未授权或已失效"
        except Exception as exc:
            account.status = "error"
            account.last_error = str(exc)
            message = str(exc)
        finally:
            await client.disconnect()

        account.health_status = "listening" if authorized and listening else "available" if authorized else "error"
        account.health_message = message
        account.health_me = me
        account.health_target_count = target_count
        account.health_listening_target_count = listening_target_count
        account.health_checked_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()


def _due_account_ids() -> list[int]:
    db = SessionLocal()
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.account_health_interval_seconds)
        rows = (
            db.query(TelegramAccount.id)
            .filter(
                TelegramAccount.status == "authorized",
                TelegramAccount.is_active == True,  # noqa: E712
                (TelegramAccount.health_checked_at.is_(None)) | (TelegramAccount.health_checked_at <= cutoff),
            )
            .order_by(TelegramAccount.id.asc())
            .all()
        )
        return [row.id for row in rows]
    finally:
        db.close()


account_health_scheduler = AccountHealthScheduler()
