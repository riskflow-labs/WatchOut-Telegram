from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import CrawlError, MonitorRun, TelegramAccount, TelegramTarget
from app.notifications.dispatcher import dispatch_for_message
from app.services.messages import upsert_message_from_telethon
from app.storage.sinks import export_message
from app.telegram.login_flow import build_client


async def backfill_targets_with_account(
    account: TelegramAccount,
    targets: list[TelegramTarget],
    limit: int = 20,
    since_days: int | None = None,
    since_hours: int | None = None,
) -> list[MonitorRun]:
    if not targets:
        return []

    run_ids: list[int] = []
    target_by_id: dict[int, str] = {}
    since_at = None
    if since_hours:
        since_at = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    elif since_days:
        since_at = datetime.now(timezone.utc) - timedelta(days=since_days)

    db = SessionLocal()
    try:
        for target in targets:
            run = MonitorRun(account_id=account.id, target_id=target.id, mode="backfill", status="running")
            db.add(run)
            db.flush()
            run_ids.append(run.id)
            target_by_id[target.id] = target.normalized_target
        (
            db.query(TelegramTarget)
            .filter(TelegramTarget.id.in_(target_by_id))
            .update({TelegramTarget.status: "backfilling", TelegramTarget.last_error: ""}, synchronize_session=False)
        )
        db.commit()
    finally:
        db.close()

    client = build_client(account)
    runs: list[MonitorRun] = []
    try:
        await client.connect()
        if not await client.is_user_authorized():
            _mark_account_unauthorized(account.id)
            raise RuntimeError("Telegram account is not authorized")

        for run_id, target_id in zip(run_ids, target_by_id, strict=False):
            count = 0
            try:
                entity = await client.get_entity(target_by_id[target_id])
                chat = await client.get_entity(entity)
                messages = []
                async for message in client.iter_messages(chat, limit=limit):
                    message_date = message.date.astimezone(timezone.utc)
                    if since_at and message_date < since_at:
                        break
                    messages.append(message)
                for message in reversed(messages):
                    sender = await message.get_sender()
                    _write_backfill_message(
                        run_id=run_id,
                        account_id=account.id,
                        target_id=target_id,
                        message=message,
                        chat=chat,
                        sender=sender,
                    )
                    count += 1
                runs.append(_finish_backfill_run(run_id, target_id, "success", "", count))
            except Exception as exc:
                runs.append(_finish_backfill_run(run_id, target_id, "failed", str(exc), count))
                _record_crawl_error(
                    account_id=account.id,
                    target_id=target_id,
                    stage="scheduled_backfill",
                    error=exc,
                    retryable=True,
                )
        return runs
    finally:
        await client.disconnect()


async def backfill_target(
    target_id: int,
    limit: int = 20,
    since_days: int | None = None,
    since_hours: int | None = None,
) -> MonitorRun:
    account_id: int | None = None
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        if target is None:
            raise RuntimeError("target not found")
        account = _select_account(db, target)
        if account is None:
            raise RuntimeError("no authorized Telegram account available")

        run = MonitorRun(account_id=account.id, target_id=target.id, mode="backfill", status="running")
        db.add(run)
        target.status = "backfilling"
        target.last_error = ""
        db.commit()
        db.refresh(run)

        run_id = run.id
        account_id = account.id
        normalized_target = target.normalized_target
        client = build_client(account)
        since_at = None
        if since_hours:
            since_at = datetime.now(timezone.utc) - timedelta(hours=since_hours)
        elif since_days:
            since_at = datetime.now(timezone.utc) - timedelta(days=since_days)
    finally:
        db.close()

    count = 0
    try:
        await client.connect()
        if not await client.is_user_authorized():
            _mark_account_unauthorized(account_id)
            raise RuntimeError("Telegram account is not authorized")
        entity = await client.get_entity(normalized_target)
        chat = await client.get_entity(entity)
        messages = []
        async for message in client.iter_messages(chat, limit=limit):
            message_date = message.date.astimezone(timezone.utc)
            if since_at and message_date < since_at:
                break
            messages.append(message)
        for message in reversed(messages):
            sender = await message.get_sender()
            _write_backfill_message(
                run_id=run_id,
                account_id=account_id,
                target_id=target_id,
                message=message,
                chat=chat,
                sender=sender,
            )
            count += 1
        return _finish_backfill_run(run_id, target_id, "success", "", count)
    except Exception as exc:
        _finish_backfill_run(run_id, target_id, "failed", str(exc), count)
        _record_crawl_error(
            account_id=account_id,
            target_id=target_id,
            stage="manual_backfill",
            error=exc,
            retryable=True,
        )
        raise
    finally:
        await client.disconnect()


def _write_backfill_message(
    *,
    run_id: int,
    account_id: int,
    target_id: int,
    message,
    chat,
    sender,
) -> None:
    db = SessionLocal()
    try:
        row, hits = upsert_message_from_telethon(
            db,
            account_id=account_id,
            target_id=target_id,
            message=message,
            chat=chat,
            sender=sender,
        )
        if hits and row.risk_level > 0 and any(hit.status == "open" for hit in hits):
            dispatch_for_message(db, row)
        target = db.get(TelegramTarget, target_id)
        run = db.get(MonitorRun, run_id)
        try:
            export_message(db, row)
        except Exception as exc:
            if target:
                target.last_error = f"sink export failed: {exc}"
        if target:
            target.last_message_at = row.event_time
        if run:
            run.records_seen += 1
            run.records_written += 1
        db.commit()
    finally:
        db.close()


def _finish_backfill_run(
    run_id: int,
    target_id: int,
    status: str,
    error: str,
    count: int,
) -> MonitorRun:
    db = SessionLocal()
    try:
        run = db.get(MonitorRun, run_id)
        target = db.get(TelegramTarget, target_id)
        if run:
            run.records_seen = count
            run.records_written = count
            run.status = status
            run.error = error
            run.finished_at = datetime.now(timezone.utc)
        if target:
            target.status = "idle" if status == "success" else "error"
            target.last_error = "" if status == "success" else error
        db.commit()
        if not run:
            raise RuntimeError("run not found")
        db.refresh(run)
        return run
    finally:
        db.close()


def _mark_account_unauthorized(account_id: int) -> None:
    db = SessionLocal()
    try:
        account = db.get(TelegramAccount, account_id)
        if account:
            account.status = "unauthorized"
            db.commit()
    finally:
        db.close()


def _record_crawl_error(
    *,
    account_id: int | None,
    target_id: int | None,
    stage: str,
    error: Exception,
    retryable: bool,
) -> None:
    db = SessionLocal()
    try:
        db.add(
            CrawlError(
                account_id=account_id,
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


def _select_account(db: Session, target: TelegramTarget) -> TelegramAccount | None:
    if target.account_id:
        account = db.get(TelegramAccount, target.account_id)
        if account and account.status == "authorized" and account.is_active:
            return account
    return (
        db.query(TelegramAccount)
        .filter(TelegramAccount.status == "authorized", TelegramAccount.is_active == True)  # noqa: E712
        .order_by(TelegramAccount.id.asc())
        .first()
    )
