from __future__ import annotations

import csv
import io
import json
import re
import asyncio
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import delete, func, update
from sqlalchemy.orm import Session
from telethon.errors import FloodWaitError, RPCError, UserAlreadyParticipantError
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CrawlError, MessageMedia, MonitorRun, NotificationDelivery, RuleHit, TelegramAccount, TelegramMessage, TelegramTarget, User
from app.services.collection_settings import get_collection_settings
from app.schemas import (
    BackfillIn,
    DeleteOut,
    MonitorRunOut,
    TargetBulkCreateIn,
    TargetBulkCreateOut,
    TargetBulkDeleteIn,
    TargetCheckIn,
    TargetCheckItem,
    TargetCheckOut,
    TargetDeleteIn,
    TargetImportDialogsIn,
    TargetMetadataSyncItem,
    TargetMetadataSyncOut,
    TargetParseIn,
    TargetParseItem,
    TargetParseOut,
    TelegramTargetCreate,
    TelegramTargetOut,
    TelegramTargetPatch,
)
from app.telegram.runtime import runtime, target_metadata_from_entity
from app.telegram.utils import normalize_target
from app.workers.initial_collection import initial_collection_queue


router = APIRouter(prefix="/targets", tags=["targets"])

METADATA_SYNC_BATCH_BUDGET_SECONDS = 45
METADATA_SYNC_TARGET_TIMEOUT_SECONDS = 8


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


@router.get("", response_model=list[TelegramTargetOut])
def list_targets(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TelegramTarget]:
    rows = db.query(TelegramTarget).order_by(TelegramTarget.id.desc()).all()
    counts = dict(
        db.query(TelegramMessage.target_id, func.count(TelegramMessage.id))
        .filter(TelegramMessage.target_id.isnot(None))
        .group_by(TelegramMessage.target_id)
        .all()
    )
    for row in rows:
        row.message_count = int(counts.get(row.id, 0))
    _attach_last_runs(rows, db)
    return rows


@router.post("/parse", response_model=TargetParseOut)
def parse_targets(
    payload: TargetParseIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetParseOut:
    existing = {
        row.normalized_target: row.id
        for row in db.query(TelegramTarget.id, TelegramTarget.normalized_target).all()
    }
    seen: dict[str, int] = {}
    items: list[TargetParseItem] = []
    raw_total = 0
    for line_no, raw in _iter_input_lines(payload.text):
        raw_total += 1
        item = _parse_target_line(line_no, raw, payload.account_id, payload.target_type, payload.target_group)
        if item.normalized_target:
            if item.normalized_target in existing:
                item.status = "duplicate"
                item.reason = "目标已存在"
                item.duplicate_of = existing[item.normalized_target]
            elif item.normalized_target in seen:
                item.status = "duplicate"
                item.reason = f"与第 {seen[item.normalized_target]} 行重复"
            else:
                seen[item.normalized_target] = line_no
        if item.status != "duplicate":
            items.append(item)
    return _parse_out(items, raw_total=raw_total)


@router.get("/export")
def export_targets(
    format: str = "csv",
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    rows = db.query(TelegramTarget).order_by(TelegramTarget.id.desc()).all()
    payload = [_target_payload(row) for row in rows]
    if format.lower() == "json":
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=watchout-telegram-targets.json"},
        )

    buffer = io.StringIO()
    fieldnames = [
        "id",
        "title",
        "target",
        "normalized_target",
        "target_type",
        "participants_count",
        "about",
        "account_id",
        "enabled",
        "status",
        "last_message_at",
        "last_error",
        "created_at",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for item in payload:
        writer.writerow({key: item.get(key, "") for key in fieldnames})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=watchout-telegram-targets.csv"},
    )


@router.post("/import-dialogs", response_model=TargetBulkCreateOut)
def import_dialogs(
    payload: TargetImportDialogsIn,
    background_tasks: BackgroundTasks,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetBulkCreateOut:
    items = [
        TargetParseItem(
            line=index,
            raw=dialog.target,
            status=dialog.status,
            reason=dialog.reason,
            detected_type="dialog",
        target_type=dialog.target_type,
        target_group=payload.target_group,
        target=dialog.target,
            normalized_target=dialog.normalized_target,
            title=dialog.title,
            account_id=payload.account_id,
            participants_count=dialog.participants_count,
            about="",
        )
        for index, dialog in enumerate(payload.dialogs, start=1)
    ]
    return _bulk_create(items, db, background_tasks)


@router.post("/check-bulk", response_model=TargetCheckOut)
async def check_targets(
    payload: TargetCheckIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetCheckOut:
    account = _select_authorized_account(db, payload.account_id)
    if not account:
        raise HTTPException(status_code=400, detail="no authorized Telegram account available")

    try:
        async def check_with_client(client):
            results: list[TargetCheckItem] = []
            for item in payload.items:
                try:
                    results.append(await asyncio.wait_for(_check_target_item(client, item, payload.auto_join_invites), timeout=20))
                except TimeoutError:
                    results.append(_check_result(item, "failed", "timeout", "检测超时：Telegram 未及时响应"))
            return TargetCheckOut(
                items=results,
                total=len(results),
                accessible=sum(1 for item in results if item.status == "accessible"),
                failed=sum(1 for item in results if item.status != "accessible"),
            )

        return await runtime.with_account_client(account.id, check_with_client)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/bulk", response_model=TargetBulkCreateOut)
def bulk_create_targets(
    payload: TargetBulkCreateIn,
    background_tasks: BackgroundTasks,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetBulkCreateOut:
    return _bulk_create(payload.items, db, background_tasks)


@router.delete("/bulk", response_model=DeleteOut)
async def bulk_delete_targets(
    payload: TargetBulkDeleteIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeleteOut:
    target_ids = [int(item) for item in dict.fromkeys(payload.target_ids) if item]
    return await _delete_targets(target_ids, payload.delete_messages, db)


@router.post("", response_model=TelegramTargetOut)
def create_target(
    payload: TelegramTargetCreate,
    background_tasks: BackgroundTasks,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramTarget:
    config = get_collection_settings(db)
    account_id = payload.account_id or _select_balanced_account_id(db, config)
    target = TelegramTarget(
        account_id=account_id,
        title=payload.title or payload.target,
        target=payload.target,
        normalized_target=normalize_target(payload.target),
        target_type=payload.target_type,
        target_group=payload.target_group.strip(),
        about=payload.about,
        enabled=payload.enabled,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    _schedule_initial_collection(background_tasks, [target.id], db)
    return target


def _bulk_create(items: list[TargetParseItem], db: Session, background_tasks: BackgroundTasks) -> TargetBulkCreateOut:
    existing = {
        row.normalized_target: row.id
        for row in db.query(TelegramTarget.id, TelegramTarget.normalized_target).all()
    }
    config = get_collection_settings(db)
    account_loads = _account_loads(db)
    created: list[TelegramTarget] = []
    skipped: list[TargetParseItem] = []
    seen: set[str] = set()
    for item in items:
        if item.status not in {"ready", "accessible"} or not item.normalized_target:
            skipped.append(item)
            continue
        if item.normalized_target in existing or item.normalized_target in seen:
            skipped.append(item.model_copy(update={"status": "duplicate", "reason": "目标已存在或本次重复"}))
            continue
        account_id = item.account_id or _select_balanced_account_id(db, config, account_loads)
        target = TelegramTarget(
            account_id=account_id,
            title=item.title or item.target,
            target=item.target,
            normalized_target=item.normalized_target,
            target_type=item.target_type,
            target_group=item.target_group.strip(),
            participants_count=item.participants_count,
            about=item.about,
            enabled=True,
        )
        db.add(target)
        created.append(target)
        seen.add(item.normalized_target)
        if account_id:
            account_loads[account_id] = account_loads.get(account_id, 0) + 1
    db.commit()
    for target in created:
        db.refresh(target)
    _schedule_initial_collection(background_tasks, [target.id for target in created], db)
    return TargetBulkCreateOut(
        created=created,
        skipped=skipped,
        created_count=len(created),
        skipped_count=len(skipped),
    )


def _schedule_initial_collection(background_tasks: BackgroundTasks, target_ids: list[int], db: Session) -> None:
    if not target_ids:
        return
    config = get_collection_settings(db)
    if not config["auto_backfill_on_import"] and not config["auto_start_listening_on_import"]:
        return
    db.query(TelegramTarget).filter(TelegramTarget.id.in_(target_ids)).update(
        {TelegramTarget.status: "initializing", TelegramTarget.last_error: ""},
        synchronize_session=False,
    )
    db.commit()
    background_tasks.add_task(initial_collection_queue.submit_targets, target_ids)


def _account_loads(db: Session) -> dict[int, int]:
    rows = (
        db.query(TelegramTarget.account_id, func.count(TelegramTarget.id))
        .filter(TelegramTarget.account_id.isnot(None), TelegramTarget.enabled == True)  # noqa: E712
        .group_by(TelegramTarget.account_id)
        .all()
    )
    return {int(account_id): int(count) for account_id, count in rows if account_id is not None}


def _select_balanced_account_id(
    db: Session,
    config: dict[str, object],
    loads: dict[int, int] | None = None,
) -> int | None:
    account_loads = loads if loads is not None else _account_loads(db)
    max_targets = int(config.get("max_targets_per_account") or 0)
    accounts = (
        db.query(TelegramAccount.id)
        .filter(TelegramAccount.status == "authorized", TelegramAccount.is_active == True)  # noqa: E712
        .order_by(TelegramAccount.id.asc())
        .all()
    )
    candidates: list[tuple[int, int]] = []
    for row in accounts:
        load = account_loads.get(row.id, 0)
        if max_targets <= 0 or load < max_targets:
            candidates.append((load, row.id))
    if not candidates:
        return None
    return min(candidates)[1]


def _attach_last_runs(targets: list[TelegramTarget], db: Session) -> None:
    target_ids = [target.id for target in targets]
    if not target_ids:
        return
    rows = (
        db.query(MonitorRun)
        .filter(MonitorRun.target_id.in_(target_ids), MonitorRun.mode == "backfill")
        .order_by(MonitorRun.started_at.desc(), MonitorRun.id.desc())
        .all()
    )
    seen: set[int] = set()
    targets_by_id = {target.id: target for target in targets}
    for run in rows:
        if not run.target_id or run.target_id in seen:
            continue
        target = targets_by_id.get(run.target_id)
        if not target:
            continue
        seen.add(run.target_id)
        target.last_run_id = run.id
        target.last_run_at = run.finished_at or run.started_at
        target.last_run_records = int(run.records_written or run.records_seen or 0)
        if run.status == "running":
            target.status = "backfilling"


async def _delete_targets(target_ids: list[int], delete_messages: bool, db: Session) -> DeleteOut:
    if not target_ids:
        return DeleteOut(deleted=0)
    existing_ids = [row.id for row in db.query(TelegramTarget.id).filter(TelegramTarget.id.in_(target_ids)).all()]
    if not existing_ids:
        return DeleteOut(deleted=0)
    for target_id in existing_ids:
        try:
            await runtime.remove_target(target_id)
        except Exception:
            pass
    deleted_messages = deleted_hits = deleted_media = 0
    if delete_messages:
        deleted_messages, deleted_hits, deleted_media = _delete_messages_for_targets(db, existing_ids)
    else:
        db.query(TelegramMessage).filter(TelegramMessage.target_id.in_(existing_ids)).update(
            {TelegramMessage.target_id: None},
            synchronize_session=False,
        )
    db.query(MonitorRun).filter(MonitorRun.target_id.in_(existing_ids)).update(
        {MonitorRun.target_id: None},
        synchronize_session=False,
    )
    db.query(CrawlError).filter(CrawlError.target_id.in_(existing_ids)).update(
        {CrawlError.target_id: None},
        synchronize_session=False,
    )
    deleted = db.query(TelegramTarget).filter(TelegramTarget.id.in_(existing_ids)).delete(synchronize_session=False)
    db.commit()
    return DeleteOut(deleted=deleted, deleted_messages=deleted_messages, deleted_hits=deleted_hits, deleted_media=deleted_media)


def _delete_messages_for_targets(db: Session, target_ids: list[int]) -> tuple[int, int, int]:
    message_filter = TelegramMessage.target_id.in_(target_ids)
    message_count = db.query(func.count(TelegramMessage.id)).filter(message_filter).scalar() or 0
    if not message_count:
        return 0, 0, 0
    message_ids = db.query(TelegramMessage.id).filter(message_filter).subquery()
    db.execute(
        update(NotificationDelivery)
        .where(NotificationDelivery.message_id.in_(message_ids))
        .values(message_id=None)
    )
    deleted_hits = db.execute(
        delete(RuleHit).where(RuleHit.message_id.in_(message_ids))
    ).rowcount or 0
    deleted_media = db.execute(
        delete(MessageMedia).where(MessageMedia.message_id.in_(message_ids))
    ).rowcount or 0
    deleted_messages = db.query(TelegramMessage).filter(message_filter).delete(
        synchronize_session=False,
    )
    return int(deleted_messages), int(deleted_hits), int(deleted_media)


def _target_payload(row: TelegramTarget) -> dict[str, object]:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "title": row.title,
        "target": row.target,
        "normalized_target": row.normalized_target,
        "target_type": row.target_type,
        "target_group": row.target_group,
        "participants_count": row.participants_count,
        "message_count": getattr(row, "message_count", 0),
        "about": row.about,
        "enabled": row.enabled,
        "status": row.status,
        "last_message_at": row.last_message_at.isoformat() if row.last_message_at else "",
        "last_run_id": getattr(row, "last_run_id", None),
        "last_run_at": getattr(row, "last_run_at", None).isoformat() if getattr(row, "last_run_at", None) else "",
        "last_run_records": getattr(row, "last_run_records", 0),
        "last_error": row.last_error,
        "created_at": row.created_at.isoformat() if row.created_at else "",
        "updated_at": row.updated_at.isoformat() if row.updated_at else "",
    }


def _select_authorized_account(db: Session, account_id: int | None) -> TelegramAccount | None:
    if account_id:
        account = db.get(TelegramAccount, account_id)
        if account and account.status == "authorized" and account.is_active:
            return account
        return None
    return (
        db.query(TelegramAccount)
        .filter(TelegramAccount.status == "authorized", TelegramAccount.is_active == True)  # noqa: E712
        .order_by(TelegramAccount.id.asc())
        .first()
    )


async def _check_target_item(client, item: TargetParseItem, auto_join_invites: bool) -> TargetCheckItem:
    if item.status not in {"ready", "accessible"}:
        return _check_result(item, "failed", "format", item.reason or "格式不可导入")
    if item.detected_type == "private_message":
        return _check_result(item, "failed", "private_message", "私有消息链接需要先同步账号 dialogs 后确认目标")
    try:
        if item.detected_type == "invite" or item.normalized_target.startswith("+") or item.normalized_target.startswith("joinchat/"):
            invite_hash = _invite_hash(item.normalized_target)
            if auto_join_invites:
                try:
                    await client(ImportChatInviteRequest(invite_hash))
                except UserAlreadyParticipantError:
                    pass
            else:
                await client(CheckChatInviteRequest(invite_hash))
            return _check_result(item, "accessible", "", "邀请链接可访问")
        entity = await client.get_entity(item.normalized_target)
        metadata = await target_metadata_from_entity(client, entity, item.target_type)
        return _check_result(
            item,
            "accessible",
            "",
            "目标可访问",
            title=str(metadata["title"] or item.title),
            target_type=str(metadata["target_type"] or item.target_type),
            participants_count=metadata["participants_count"],
            about=metadata["about"],
        )
    except FloodWaitError as exc:
        return _check_result(item, "failed", "flood_wait", f"Telegram 限流，等待 {getattr(exc, 'seconds', '?')} 秒")
    except ValueError as exc:
        return _check_result(item, "failed", "not_found", str(exc))
    except RPCError as exc:
        return _check_result(item, "failed", exc.__class__.__name__, str(exc))
    except Exception as exc:
        return _check_result(item, "failed", exc.__class__.__name__, str(exc))


async def _sync_target_metadata(client, target: TelegramTarget) -> None:
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


def _invite_hash(normalized_target: str) -> str:
    value = normalized_target.strip()
    if value.startswith("+"):
        return value[1:]
    if value.startswith("joinchat/"):
        return value.split("/", 1)[1]
    return value


def _check_result(
    item: TargetParseItem,
    status: str,
    category: str,
    reason: str,
    title: str | None = None,
    target_type: str | None = None,
    participants_count: int | None = None,
    about: str | None = None,
) -> TargetCheckItem:
    return TargetCheckItem(
        line=item.line,
        raw=item.raw,
        target=item.target,
        normalized_target=item.normalized_target,
        status=status,
        category=category,
        reason=reason,
        title=title or item.title,
        target_type=target_type or item.target_type,
        target_group=item.target_group,
        participants_count=participants_count if participants_count is not None else item.participants_count,
        about=about if about is not None else item.about,
    )


def _iter_input_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    raw_text = (text or "").strip()
    if not raw_text:
        return lines
    candidates: list[str] = []
    if raw_text.startswith("["):
        try:
            parsed = json.loads(raw_text)
            candidates.extend(_targets_from_json_value(parsed))
        except json.JSONDecodeError:
            candidates = raw_text.splitlines()
    else:
        for line in raw_text.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("[") or line.startswith("{"):
                try:
                    candidates.extend(_targets_from_json_value(json.loads(line)))
                    continue
                except json.JSONDecodeError:
                    pass
            for row in csv.reader(io.StringIO(line)):
                if len(row) > 1:
                    candidates.extend(row)
                elif row:
                    candidates.append(row[0])
    for index, raw in enumerate(candidates, start=1):
        value = raw.strip()
        if not value:
            continue
        lines.append((index, value))
    return lines


def _targets_from_json_value(value) -> list[str]:
    items = value if isinstance(value, list) else [value]
    targets: list[str] = []
    for item in items:
        if isinstance(item, str):
            targets.append(item)
        elif isinstance(item, dict):
            targets.append(str(item.get("target") or item.get("url") or item.get("username") or ""))
    return targets


def _parse_target_line(line: int, raw: str, account_id: int | None, target_type: str, target_group: str = "") -> TargetParseItem:
    value = _strip_wrappers(raw)
    detected = "unknown"
    normalized = ""
    display_target = value
    reason = ""
    status = "ready"

    parsed = urlparse(value)
    if parsed.scheme == "tg":
        query = parse_qs(parsed.query)
        invite = (query.get("invite") or [""])[0].strip()
        domain = (query.get("domain") or [""])[0].strip().lstrip("@")
        if parsed.netloc == "join" and invite:
            detected = "invite"
            normalized = f"+{invite}"
            display_target = f"tg://join?invite={invite}"
        elif parsed.netloc == "resolve" and domain:
            detected = "username"
            normalized = domain
            display_target = f"https://t.me/{domain}"
        else:
            status, reason = "invalid", "暂不支持的 tg:// 链接"
    else:
        if not parsed.scheme and re.match(r"^(t\.me|telegram\.me)/", value, re.I):
            parsed = urlparse(f"https://{value}")
        host = (parsed.netloc or "").lower()
        if host in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
            path = parsed.path.strip("/")
            parts = [part for part in path.split("/") if part]
            if not parts:
                status, reason = "invalid", "Telegram 链接缺少目标"
            elif parts[0] == "joinchat" and len(parts) >= 2:
                detected = "invite"
                normalized = f"joinchat/{parts[1]}"
                display_target = f"https://t.me/joinchat/{parts[1]}"
            elif parts[0].startswith("+"):
                detected = "invite"
                normalized = parts[0]
                display_target = f"https://t.me/{parts[0]}"
            elif parts[0] == "c":
                detected = "private_message"
                normalized = "/".join(parts[:3])
                display_target = f"https://t.me/{normalized}"
                status, reason = "invalid", "私有消息链接需要先同步账号 dialogs 后确认目标"
            elif parts[0] == "s" and len(parts) >= 2:
                detected = "username"
                normalized = parts[1].lstrip("@")
                display_target = f"https://t.me/{normalized}"
            else:
                detected = "message_link" if len(parts) > 1 and parts[1].isdigit() else "username"
                normalized = parts[0].lstrip("@")
                display_target = f"https://t.me/{normalized}"
        elif value.startswith("@"):
            candidate = value[1:].strip("/")
            detected = "username"
            normalized = candidate
            display_target = f"https://t.me/{candidate}"
        elif USERNAME_RE.match(value):
            detected = "username"
            normalized = value
            display_target = f"https://t.me/{value}"
        else:
            status, reason = "invalid", "无法识别为 Telegram 目标"

    if normalized and detected == "username" and not USERNAME_RE.match(normalized):
        status, reason = "invalid", "公开用户名格式不合法"

    resolved_type = target_type if target_type != "auto" else _default_target_type(detected)
    title = _title_from_target(normalized, detected)
    return TargetParseItem(
        line=line,
        raw=raw,
        status=status,
        reason=reason,
        detected_type=detected,
        target_type=resolved_type,
        target=display_target,
        normalized_target=normalized,
        title=title,
        account_id=account_id,
        target_group=target_group.strip(),
    )


def _strip_wrappers(value: str) -> str:
    text = value.strip().strip(",;")
    if text.startswith("<") and text.endswith(">"):
        text = text[1:-1].strip()
    return text


def _default_target_type(detected_type: str) -> str:
    if detected_type in {"invite", "private_message"}:
        return "group"
    return "group"


def _title_from_target(normalized: str, detected_type: str) -> str:
    if not normalized:
        return ""
    if detected_type == "invite":
        return f"Invite / {normalized}"
    if detected_type == "private_message":
        return f"Private / {normalized}"
    return f"Telegram / {normalized}"


def _parse_out(items: list[TargetParseItem], raw_total: int | None = None) -> TargetParseOut:
    total = raw_total if raw_total is not None else len(items)
    return TargetParseOut(
        items=items,
        total=len(items),
        raw_total=total,
        importable=sum(1 for item in items if item.status == "ready"),
        duplicated=max(0, total - len(items)) + sum(1 for item in items if item.status == "duplicate"),
        invalid=sum(1 for item in items if item.status == "invalid"),
    )


@router.patch("/{target_id}", response_model=TelegramTargetOut)
def patch_target(
    target_id: int,
    payload: TelegramTargetPatch,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramTarget:
    target = db.get(TelegramTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="target not found")
    if payload.account_id_set:
        target.account_id = payload.account_id
    if payload.title is not None:
        target.title = payload.title
    if payload.target_group is not None:
        target.target_group = payload.target_group.strip()
    if payload.enabled is not None:
        target.enabled = payload.enabled
    db.commit()
    db.refresh(target)
    return target


@router.delete("/{target_id}", response_model=DeleteOut)
async def delete_target(
    target_id: int,
    payload: TargetDeleteIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeleteOut:
    return await _delete_targets([target_id], payload.delete_messages, db)


@router.post("/sync-metadata", response_model=TargetMetadataSyncOut)
async def sync_targets_metadata(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetMetadataSyncOut:
    targets = db.query(TelegramTarget).order_by(TelegramTarget.id.asc()).all()
    accounts = (
        db.query(TelegramAccount)
        .filter(TelegramAccount.status == "authorized", TelegramAccount.is_active == True)  # noqa: E712
        .order_by(TelegramAccount.id.asc())
        .all()
    )
    if not accounts:
        raise HTTPException(status_code=400, detail="no authorized Telegram account available")
    accounts_by_id = {account.id: account for account in accounts}
    fallback_account = accounts[0]
    targets_by_account: dict[int, list[TelegramTarget]] = {account.id: [] for account in accounts}
    for target in targets:
        account_id = target.account_id if target.account_id in accounts_by_id else fallback_account.id
        targets_by_account.setdefault(account_id, []).append(target)

    items: list[TargetMetadataSyncItem] = []
    deadline = asyncio.get_running_loop().time() + METADATA_SYNC_BATCH_BUDGET_SECONDS
    budget_message = "本次同步达到时间预算，剩余目标留到下一次同步"

    def mark_budget_skipped(account_targets: list[TelegramTarget]) -> None:
        for target in account_targets:
            target.last_error = budget_message
            items.append(TargetMetadataSyncItem(id=target.id, title=target.title, status="failed", message=budget_message))

    for account_id, account_targets in targets_by_account.items():
        if not account_targets:
            continue
        if asyncio.get_running_loop().time() >= deadline:
            mark_budget_skipped(account_targets)
            db.commit()
            continue
        try:
            async def sync_with_client(client):
                for index, target in enumerate(account_targets):
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        mark_budget_skipped(account_targets[index:])
                        break
                    try:
                        timeout = max(1, min(METADATA_SYNC_TARGET_TIMEOUT_SECONDS, remaining))
                        await asyncio.wait_for(_sync_target_metadata(client, target), timeout=timeout)
                        items.append(TargetMetadataSyncItem(id=target.id, title=target.title, status="updated", message="已刷新"))
                    except (TimeoutError, asyncio.TimeoutError):
                        target.last_error = "同步超时：Telegram 未及时响应"
                        items.append(TargetMetadataSyncItem(id=target.id, title=target.title, status="failed", message=target.last_error))
                    except FloodWaitError as exc:
                        target.last_error = f"Telegram 限流，等待 {getattr(exc, 'seconds', '?')} 秒"
                        items.append(TargetMetadataSyncItem(id=target.id, title=target.title, status="failed", message=target.last_error))
                    except Exception as exc:
                        target.last_error = str(exc)
                        items.append(TargetMetadataSyncItem(id=target.id, title=target.title, status="failed", message=str(exc)))
                    db.commit()
                return None

            await runtime.with_account_client(account_id, sync_with_client)
        except Exception as exc:
            for target in account_targets:
                message = str(exc)
                target.last_error = message
                items.append(TargetMetadataSyncItem(id=target.id, title=target.title, status="failed", message=message))
            db.commit()
    updated = sum(1 for item in items if item.status == "updated")
    failed = len(items) - updated
    return TargetMetadataSyncOut(total=len(items), updated=updated, failed=failed, items=items)


@router.post("/{target_id}/sync-title", response_model=TelegramTargetOut)
async def sync_target_title(
    target_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramTarget:
    target = db.get(TelegramTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="target not found")
    account = _select_authorized_account(db, target.account_id)
    if not account:
        raise HTTPException(status_code=400, detail="no authorized Telegram account available")
    try:
        async def sync_with_client(client):
            await _sync_target_metadata(client, target)
            db.commit()
            db.refresh(target)
            return None

        await runtime.with_account_client(account.id, sync_with_client)
        return target
    except FloodWaitError as exc:
        target.last_error = f"Telegram 限流，等待 {getattr(exc, 'seconds', '?')} 秒"
        db.commit()
        raise HTTPException(status_code=400, detail=target.last_error) from exc
    except RuntimeError as exc:
        target.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        target.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{target_id}/start")
async def start_target(
    target_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str | int]:
    target = db.get(TelegramTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="target not found")
    if not target.enabled:
        raise HTTPException(status_code=400, detail="target disabled")
    try:
        collection_config = get_collection_settings(db)
        if int(collection_config["initial_backfill_limit"]) > 0:
            await runtime.backfill_target(
                target_id,
                int(collection_config["initial_backfill_limit"]),
                since_hours=int(collection_config["initial_backfill_window_hours"]),
            )
        await runtime.add_target(target_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "status": "listening",
        "target_id": target_id,
        "backfilled": int(collection_config["initial_backfill_limit"]),
        "backfill_window_hours": int(collection_config["initial_backfill_window_hours"]),
    }


@router.post("/{target_id}/stop")
async def stop_target(
    target_id: int,
    _user: User = Depends(get_current_user),
) -> dict[str, str | int]:
    await runtime.remove_target(target_id)
    return {"status": "stopped", "target_id": target_id}


@router.post("/{target_id}/backfill", response_model=MonitorRunOut)
async def backfill(
    target_id: int,
    payload: BackfillIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    target = db.get(TelegramTarget, target_id)
    if not target:
        raise HTTPException(status_code=404, detail="target not found")
    if not target.enabled:
        raise HTTPException(status_code=400, detail="target disabled")
    try:
        return await runtime.backfill_target(
            target_id,
            payload.limit,
            since_days=payload.since_days,
            since_hours=payload.since_hours,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
