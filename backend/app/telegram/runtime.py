from __future__ import annotations

import asyncio
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session
from telethon import events, utils
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.functions.channels import GetFullChannelRequest
from telethon.tl.functions.messages import GetFullChatRequest
from telethon.tl.types import Channel, Chat

from app.core.database import SessionLocal
from app.models import MonitorRun, TelegramAccount, TelegramTarget
from app.notifications.dispatcher import dispatch_for_message
from app.services.messages import upsert_message_from_telethon
from app.storage.sinks import export_message
from app.telegram.backfill import backfill_target as backfill_target_once
from app.telegram.backfill import backfill_targets_with_account
from app.telegram.login_flow import build_client


CLIENT_CONNECT_TIMEOUT_SECONDS = 20


async def _safe_disconnect(client) -> None:
    try:
        await client.disconnect()
    except sqlite3.OperationalError as exc:
        if "database is locked" not in str(exc).lower():
            raise


async def sync_target_metadata_with_client(client, target_id: int) -> None:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        if not target:
            raise RuntimeError("target not found")
        entity = await client.get_entity(target.normalized_target)
        metadata = await target_metadata_from_entity(client, entity, target.target_type)
        if metadata["title"]:
            target.title = str(metadata["title"])
        if metadata["target_type"]:
            target.target_type = str(metadata["target_type"])
        if metadata["participants_count"] is not None:
            target.participants_count = int(metadata["participants_count"])
        target.about = str(metadata["about"] or "")
        target.last_error = ""
        db.commit()
    finally:
        db.close()


async def target_metadata_from_entity(client, entity, fallback_type: str = "group") -> dict[str, int | str | None]:
    info = await _target_info(client, entity)
    return {
        "title": getattr(entity, "title", None) or getattr(entity, "username", None) or "",
        "target_type": _target_type_from_entity(entity, fallback_type),
        "participants_count": info["participants_count"],
        "about": info["about"],
    }


async def _target_info(client, entity) -> dict[str, int | str | None]:
    info: dict[str, int | str | None] = {
        "participants_count": getattr(entity, "participants_count", None),
        "about": "",
    }
    full_chat = None
    try:
        if isinstance(entity, Channel):
            full = await client(GetFullChannelRequest(entity))
            full_chat = full.full_chat
        elif isinstance(entity, Chat):
            full = await client(GetFullChatRequest(entity.id))
            full_chat = full.full_chat
    except Exception:
        full_chat = None
    if full_chat is not None:
        info["about"] = getattr(full_chat, "about", "") or ""
        participants_count = getattr(full_chat, "participants_count", None)
        if participants_count is not None:
            info["participants_count"] = participants_count
        elif info["participants_count"] is None:
            participants = getattr(getattr(full_chat, "participants", None), "participants", None)
            info["participants_count"] = len(participants) if participants is not None else None
    return info


def _target_type_from_entity(entity, fallback: str = "group") -> str:
    if bool(getattr(entity, "broadcast", False)) and not bool(getattr(entity, "megagroup", False)):
        return "channel"
    if bool(getattr(entity, "megagroup", False)):
        return "supergroup"
    if isinstance(entity, Chat):
        return "group"
    return fallback


@dataclass
class AccountRuntimeHandle:
    task: asyncio.Task
    account_id: int
    target_ids: set[int] = field(default_factory=set)
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    refresh_event: asyncio.Event = field(default_factory=asyncio.Event)


class MonitorRuntime:
    def __init__(self) -> None:
        self._accounts: dict[int, AccountRuntimeHandle] = {}
        self._target_accounts: dict[int, int] = {}
        self._backfill_locks: dict[int, asyncio.Lock] = {}
        self._state_lock = asyncio.Lock()

    def running_target_ids(self) -> set[int]:
        return {target_id for handle in self._accounts.values() for target_id in handle.target_ids}

    def running_account_ids(self) -> set[int]:
        return set(self._accounts)

    def busy_target_for(self, target_id: int) -> int | None:
        account_id = _resolve_target_account_id(target_id)
        if account_id is None:
            return None
        handle = self._accounts.get(account_id)
        if not handle:
            return None
        return target_id if target_id in handle.target_ids else next(iter(handle.target_ids), None)

    async def start_target(self, target_id: int) -> None:
        await self.add_target(target_id)

    async def stop_target(self, target_id: int) -> None:
        await self.remove_target(target_id)

    async def restore_enabled_targets(self) -> list[int]:
        target_ids = _load_enabled_target_ids()
        restored: list[int] = []
        for target_id in target_ids:
            try:
                await self.add_target(target_id)
                restored.append(target_id)
            except Exception as exc:
                _update_target_error(target_id, f"restore listener failed: {exc}", status="idle")
        return restored

    async def add_target(self, target_id: int) -> None:
        account_id = _prepare_target_for_listener(target_id)
        async with self._state_lock:
            handle = self._accounts.get(account_id)
            if handle is None or handle.task.done():
                handle = AccountRuntimeHandle(
                    task=asyncio.create_task(self._run_account(account_id)),
                    account_id=account_id,
                    target_ids=set(),
                )
                self._accounts[account_id] = handle
            handle.target_ids.add(target_id)
            self._target_accounts[target_id] = account_id
            handle.refresh_event.set()
        _mark_targets_listening({target_id})

    async def remove_target(self, target_id: int) -> None:
        account_id = self._target_accounts.pop(target_id, None) or _resolve_target_account_id(target_id)
        if account_id is None:
            _mark_targets_idle({target_id})
            return
        async with self._state_lock:
            handle = self._accounts.get(account_id)
            if not handle:
                _mark_targets_idle({target_id})
                return
            handle.target_ids.discard(target_id)
            handle.refresh_event.set()
            should_stop = not handle.target_ids
        _mark_targets_idle({target_id})
        if should_stop:
            await self.stop_account(account_id)

    async def start_account(self, account_id: int) -> list[int]:
        target_ids = _load_enabled_target_ids_for_account(account_id)
        if not target_ids:
            return []
        _ensure_account_authorized(account_id)
        async with self._state_lock:
            handle = self._accounts.get(account_id)
            if handle is None or handle.task.done():
                handle = AccountRuntimeHandle(
                    task=asyncio.create_task(self._run_account(account_id)),
                    account_id=account_id,
                    target_ids=set(),
                )
                self._accounts[account_id] = handle
            handle.target_ids.update(target_ids)
            for target_id in target_ids:
                self._target_accounts[target_id] = account_id
            handle.refresh_event.set()
        _bind_targets_to_account(target_ids, account_id)
        _mark_targets_listening(set(target_ids))
        return target_ids

    async def stop_account(self, account_id: int) -> list[int]:
        async with self._state_lock:
            handle = self._accounts.pop(account_id, None)
            if not handle:
                return []
            target_ids = set(handle.target_ids)
            handle.target_ids.clear()
            handle.stop_event.set()
            for target_id in target_ids:
                self._target_accounts.pop(target_id, None)
        try:
            await handle.task
        except Exception:
            pass
        _mark_targets_idle(target_ids)
        return sorted(target_ids)

    async def backfill_target(
        self,
        target_id: int,
        limit: int,
        since_days: int | None = None,
        since_hours: int | None = None,
    ) -> MonitorRun:
        account_id = _resolve_target_account_id(target_id)
        if account_id is None:
            raise RuntimeError("no authorized Telegram account available")
        lock = self._backfill_locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            async with self._state_lock:
                handle = self._accounts.get(account_id)
                listening_ids = set(handle.target_ids) if handle else set()
            if listening_ids:
                await self.stop_account(account_id)
            try:
                return await backfill_target_once(target_id, limit, since_days=since_days, since_hours=since_hours)
            finally:
                if listening_ids:
                    await self._restart_account_targets(account_id, listening_ids)

    async def backfill_targets_for_account(
        self,
        account_id: int,
        target_ids: list[int],
        limit: int,
        since_days: int | None = None,
        since_hours: int | None = None,
    ) -> list[MonitorRun]:
        if not target_ids:
            return []
        _ensure_account_authorized(account_id)
        lock = self._backfill_locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            async with self._state_lock:
                handle = self._accounts.get(account_id)
                listening_ids = set(handle.target_ids) if handle else set()
            if listening_ids:
                await self.stop_account(account_id)
            try:
                account = _load_account(account_id)
                targets = _load_targets_for_account(account_id, set(target_ids))
                if not targets:
                    return []
                _bind_targets_to_account({target.id for target in targets}, account_id)
                return await backfill_targets_with_account(
                    account,
                    targets,
                    limit=limit,
                    since_days=since_days,
                    since_hours=since_hours,
                )
            finally:
                if listening_ids:
                    await self._restart_account_targets(account_id, listening_ids)

    async def with_account_session_client(self, account_id: int, callback, *, require_authorized: bool = True):
        if require_authorized:
            _ensure_account_authorized(account_id)
        lock = self._backfill_locks.setdefault(account_id, asyncio.Lock())
        async with lock:
            async with self._state_lock:
                handle = self._accounts.get(account_id)
                listening_ids = set(handle.target_ids) if handle else set()
            if listening_ids:
                await self.stop_account(account_id)
            account = _load_account(account_id, require_authorized=require_authorized)
            client = build_client(account)
            try:
                await asyncio.wait_for(client.connect(), timeout=CLIENT_CONNECT_TIMEOUT_SECONDS)
                if not client.is_connected():
                    raise RuntimeError("Telegram 连接已断开，请检查代理或网络出口")
                if require_authorized and not await client.is_user_authorized():
                    _mark_account_unauthorized(account_id)
                    raise RuntimeError("account is not authorized")
                return await callback(client)
            finally:
                await _safe_disconnect(client)
                if listening_ids:
                    await self._restart_account_targets(account_id, listening_ids)

    async def with_account_client(self, account_id: int, callback):
        return await self.with_account_session_client(account_id, callback, require_authorized=True)

    async def sync_target_metadata(self, target_id: int) -> None:
        account_id = _resolve_target_account_id(target_id)
        if account_id is None:
            raise RuntimeError("no authorized Telegram account available")

        async def sync_with_client(client):
            await sync_target_metadata_with_client(client, target_id)

        await self.with_account_client(account_id, sync_with_client)

    async def _restart_account_targets(self, account_id: int, target_ids: set[int]) -> None:
        _ensure_account_authorized(account_id)
        async with self._state_lock:
            handle = self._accounts.get(account_id)
            if handle is None or handle.task.done():
                handle = AccountRuntimeHandle(
                    task=asyncio.create_task(self._run_account(account_id)),
                    account_id=account_id,
                    target_ids=set(),
                )
                self._accounts[account_id] = handle
            handle.target_ids.update(target_ids)
            for target_id in target_ids:
                self._target_accounts[target_id] = account_id
            handle.refresh_event.set()
        _mark_targets_listening(target_ids)

    async def _rebalance_targets_after_account_failure(self, failed_account_id: int, target_ids: set[int]) -> None:
        remaining_ids = _clear_failed_account_binding(failed_account_id, target_ids)
        for target_id in remaining_ids:
            try:
                await self.add_target(target_id)
            except Exception as exc:
                _update_target_error(target_id, f"account failover failed: {exc}", status="error")

    async def _run_account(self, account_id: int) -> None:
        run_id = _create_live_run(account_id)
        failed_target_ids: set[int] = set()
        should_failover = False
        try:
            account = _load_account(account_id)
            client = build_client(account)
            await asyncio.wait_for(client.connect(), timeout=CLIENT_CONNECT_TIMEOUT_SECONDS)
            if not await client.is_user_authorized():
                _mark_account_unauthorized(account_id)
                raise RuntimeError("Telegram account is not authorized")

            try:
                while True:
                    handle = self._accounts.get(account_id)
                    if handle is None or handle.stop_event.is_set():
                        break
                    handle.refresh_event.clear()
                    target_ids = set(handle.target_ids)
                    targets = _load_targets(target_ids)
                    if not targets:
                        await self._wait_for_refresh_or_stop(handle)
                        continue
                    await self._listen_account_once(client, run_id, account_id, handle, targets)
            finally:
                await _safe_disconnect(client)
            _finish_run(run_id, "stopped", "")
        except asyncio.CancelledError:
            _finish_run(run_id, "stopped", "")
            raise
        except FloodWaitError as exc:
            delay = int(getattr(exc, "seconds", 60)) + 30
            _mark_account_targets_error(account_id, f"FloodWait: sleeping {delay}s", status="listening")
            _finish_run(run_id, "failed", f"FloodWait: {delay}s")
        except RPCError as exc:
            error = f"Telegram RPC error: {exc.__class__.__name__}"
            _mark_account_targets_error(account_id, error, status="error")
            _finish_run(run_id, "failed", error)
            should_failover = not _is_account_available(account_id)
            if should_failover:
                failed_target_ids = _load_enabled_target_ids_for_failed_account(account_id)
        except Exception as exc:
            _mark_account_targets_error(account_id, str(exc), status="error")
            _finish_run(run_id, "failed", str(exc))
            should_failover = not _is_account_available(account_id)
            if should_failover:
                failed_target_ids = _load_enabled_target_ids_for_failed_account(account_id)
        finally:
            async with self._state_lock:
                handle = self._accounts.get(account_id)
                if handle and handle.task is asyncio.current_task():
                    self._accounts.pop(account_id, None)
                    if should_failover:
                        failed_target_ids.update(handle.target_ids)
                    for target_id in handle.target_ids:
                        self._target_accounts.pop(target_id, None)
            if should_failover and failed_target_ids:
                await self._rebalance_targets_after_account_failure(account_id, failed_target_ids)

    async def _listen_account_once(
        self,
        client,
        run_id: int,
        account_id: int,
        handle: AccountRuntimeHandle,
        targets: list[TelegramTarget],
    ) -> None:
        entities = []
        target_by_peer_id: dict[int, int] = {}
        chat_by_target: dict[int, object] = {}
        for target in targets:
            try:
                entity = await client.get_entity(target.normalized_target)
                chat = await client.get_entity(entity)
            except Exception as exc:
                _update_target_error(target.id, f"resolve target failed: {exc}", status="error")
                continue
            entities.append(entity)
            peer_id = utils.get_peer_id(entity)
            target_by_peer_id[peer_id] = target.id
            chat_by_target[target.id] = chat

        if not entities:
            await self._wait_for_refresh_or_stop(handle)
            return

        _mark_targets_listening(set(target_by_peer_id.values()))

        async def handle_new_message(event: events.NewMessage.Event) -> None:
            chat = await event.get_chat()
            peer_id = utils.get_peer_id(chat)
            target_id = target_by_peer_id.get(peer_id)
            if target_id is None:
                return
            await _write_live_message(
                run_id=run_id,
                account_id=account_id,
                target_id=target_id,
                message=event.message,
                chat=chat_by_target.get(target_id) or chat,
            )

        client.add_event_handler(handle_new_message, events.NewMessage(chats=entities))
        try:
            await self._wait_for_refresh_or_stop(handle)
        finally:
            client.remove_event_handler(handle_new_message)

    async def _wait_for_refresh_or_stop(self, handle: AccountRuntimeHandle) -> None:
        stop_task = asyncio.create_task(handle.stop_event.wait())
        refresh_task = asyncio.create_task(handle.refresh_event.wait())
        done, pending = await asyncio.wait(
            {stop_task, refresh_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        for task in done:
            task.result()


async def _write_live_message(
    *,
    run_id: int,
    account_id: int,
    target_id: int,
    message,
    chat,
) -> None:
    sender = await message.get_sender()
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
        try:
            export_message(db, row)
        except Exception:
            pass
        target = db.get(TelegramTarget, target_id)
        run = db.get(MonitorRun, run_id)
        if target:
            target.last_message_at = row.event_time
            target.status = "listening"
            target.last_error = ""
        if run:
            run.records_seen += 1
            run.records_written += 1
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


def _resolve_target_account_id(target_id: int) -> int | None:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        if target is None:
            raise RuntimeError("target not found")
        account = _select_account(db, target)
        return account.id if account else None
    finally:
        db.close()


def _ensure_account_authorized(account_id: int) -> None:
    db = SessionLocal()
    try:
        account = db.get(TelegramAccount, account_id)
        if not account:
            raise RuntimeError("account not found")
        if account.status != "authorized" or not account.is_active:
            raise RuntimeError("account is not authorized")
    finally:
        db.close()


def _is_account_available(account_id: int) -> bool:
    db = SessionLocal()
    try:
        account = db.get(TelegramAccount, account_id)
        return bool(account and account.status == "authorized" and account.is_active)
    finally:
        db.close()


def _prepare_target_for_listener(target_id: int) -> int:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        if target is None:
            raise RuntimeError("target not found")
        if not target.enabled:
            raise RuntimeError("target disabled")
        account = _select_account(db, target)
        if account is None:
            raise RuntimeError("no authorized Telegram account available")
        target.account_id = account.id
        target.status = "listening"
        target.last_error = ""
        db.commit()
        return account.id
    finally:
        db.close()


def _load_account(account_id: int, *, require_authorized: bool = True) -> TelegramAccount:
    db = SessionLocal()
    try:
        account = db.get(TelegramAccount, account_id)
        if account is None:
            raise RuntimeError("account not found")
        if require_authorized and account.status != "authorized":
            raise RuntimeError("account is not authorized")
        db.expunge(account)
        return account
    finally:
        db.close()


def _load_targets(target_ids: set[int]) -> list[TelegramTarget]:
    if not target_ids:
        return []
    db = SessionLocal()
    try:
        targets = (
            db.query(TelegramTarget)
            .filter(TelegramTarget.id.in_(target_ids), TelegramTarget.enabled == True)  # noqa: E712
            .order_by(TelegramTarget.id.asc())
            .all()
        )
        for target in targets:
            db.expunge(target)
        return targets
    finally:
        db.close()


def _load_targets_for_account(account_id: int, target_ids: set[int]) -> list[TelegramTarget]:
    if not target_ids:
        return []
    db = SessionLocal()
    try:
        (
            db.query(TelegramTarget)
            .filter(
                TelegramTarget.id.in_(target_ids),
                TelegramTarget.enabled == True,  # noqa: E712
                or_(TelegramTarget.account_id == account_id, TelegramTarget.account_id.is_(None)),
            )
            .update({TelegramTarget.account_id: account_id}, synchronize_session=False)
        )
        db.commit()
        targets = (
            db.query(TelegramTarget)
            .filter(
                TelegramTarget.id.in_(target_ids),
                TelegramTarget.enabled == True,  # noqa: E712
                or_(TelegramTarget.account_id == account_id, TelegramTarget.account_id.is_(None)),
            )
            .order_by(TelegramTarget.id.asc())
            .all()
        )
        db.commit()
        for target in targets:
            db.expunge(target)
        return targets
    finally:
        db.close()


def _load_enabled_target_ids_for_account(account_id: int) -> list[int]:
    db = SessionLocal()
    try:
        account = db.get(TelegramAccount, account_id)
        if not account:
            raise RuntimeError("account not found")
        if account.status != "authorized":
            raise RuntimeError("account is not authorized")
        rows = (
            db.query(TelegramTarget.id)
            .filter(
                TelegramTarget.enabled == True,  # noqa: E712
                or_(TelegramTarget.account_id == account_id, TelegramTarget.account_id.is_(None)),
            )
            .order_by(TelegramTarget.id.asc())
            .all()
        )
        return [row.id for row in rows]
    finally:
        db.close()


def _load_enabled_target_ids_for_failed_account(account_id: int) -> set[int]:
    db = SessionLocal()
    try:
        rows = (
            db.query(TelegramTarget.id)
            .filter(
                TelegramTarget.enabled == True,  # noqa: E712
                TelegramTarget.account_id == account_id,
            )
            .all()
        )
        return {row.id for row in rows}
    finally:
        db.close()


def _load_enabled_target_ids() -> list[int]:
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


def _clear_failed_account_binding(account_id: int, target_ids: set[int]) -> set[int]:
    if not target_ids:
        return set()
    db = SessionLocal()
    try:
        rows = (
            db.query(TelegramTarget)
            .filter(
                TelegramTarget.id.in_(target_ids),
                TelegramTarget.enabled == True,  # noqa: E712
                TelegramTarget.account_id == account_id,
            )
            .all()
        )
        remaining_ids = {target.id for target in rows}
        for target in rows:
            target.account_id = None
            target.status = "idle"
            target.last_error = ""
        db.commit()
        return remaining_ids
    finally:
        db.close()


def _bind_targets_to_account(target_ids: list[int] | set[int], account_id: int) -> None:
    if not target_ids:
        return
    db = SessionLocal()
    try:
        db.query(TelegramTarget).filter(TelegramTarget.id.in_(target_ids)).update(
            {TelegramTarget.account_id: account_id},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()


def _mark_targets_listening(target_ids: set[int]) -> None:
    if not target_ids:
        return
    db = SessionLocal()
    try:
        (
            db.query(TelegramTarget)
            .filter(TelegramTarget.id.in_(target_ids))
            .update(
                {TelegramTarget.status: "listening", TelegramTarget.last_error: ""},
                synchronize_session=False,
            )
        )
        db.commit()
    finally:
        db.close()


def _mark_targets_idle(target_ids: set[int]) -> None:
    if not target_ids:
        return
    db = SessionLocal()
    try:
        (
            db.query(TelegramTarget)
            .filter(TelegramTarget.id.in_(target_ids), TelegramTarget.status == "listening")
            .update({TelegramTarget.status: "idle"}, synchronize_session=False)
        )
        db.commit()
    finally:
        db.close()


def _mark_account_targets_error(account_id: int, error: str, status: str = "error") -> None:
    db = SessionLocal()
    try:
        (
            db.query(TelegramTarget)
            .filter(TelegramTarget.account_id == account_id, TelegramTarget.status == "listening")
            .update(
                {TelegramTarget.status: status, TelegramTarget.last_error: error},
                synchronize_session=False,
            )
        )
        db.commit()
    finally:
        db.close()


def _update_target_error(target_id: int, error: str, status: str = "error") -> None:
    db = SessionLocal()
    try:
        target = db.get(TelegramTarget, target_id)
        if target:
            target.status = status
            target.last_error = error
            db.commit()
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


def _create_live_run(account_id: int) -> int:
    db = SessionLocal()
    try:
        run = MonitorRun(account_id=account_id, target_id=None, mode="live", status="running")
        db.add(run)
        db.commit()
        db.refresh(run)
        return run.id
    finally:
        db.close()


def _finish_run(run_id: int, status: str, error: str) -> None:
    db = SessionLocal()
    try:
        run = db.get(MonitorRun, run_id)
        if run:
            run.status = status
            run.error = error
            run.finished_at = datetime.now(timezone.utc)
            db.commit()
    finally:
        db.close()


runtime = MonitorRuntime()
