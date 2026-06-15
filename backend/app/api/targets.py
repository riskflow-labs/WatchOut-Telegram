from __future__ import annotations

import csv
import io
import json
import re
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from telethon.errors import FloodWaitError, RPCError, UserAlreadyParticipantError
from telethon.tl.functions.messages import CheckChatInviteRequest, ImportChatInviteRequest

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import TelegramAccount, TelegramTarget, User
from app.schemas import (
    BackfillIn,
    MonitorRunOut,
    TargetBulkCreateIn,
    TargetBulkCreateOut,
    TargetCheckIn,
    TargetCheckItem,
    TargetCheckOut,
    TargetImportDialogsIn,
    TargetParseIn,
    TargetParseItem,
    TargetParseOut,
    TelegramTargetCreate,
    TelegramTargetOut,
    TelegramTargetPatch,
)
from app.telegram.login_flow import build_client
from app.telegram.runtime import runtime
from app.telegram.utils import normalize_target


router = APIRouter(prefix="/targets", tags=["targets"])


USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


@router.get("", response_model=list[TelegramTargetOut])
def list_targets(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TelegramTarget]:
    return db.query(TelegramTarget).order_by(TelegramTarget.id.desc()).all()


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
    for line_no, raw in _iter_input_lines(payload.text):
        item = _parse_target_line(line_no, raw, payload.account_id, payload.target_type)
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
        items.append(item)
    return _parse_out(items)


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
            target=dialog.target,
            normalized_target=dialog.normalized_target,
            title=dialog.title,
            account_id=payload.account_id,
        )
        for index, dialog in enumerate(payload.dialogs, start=1)
    ]
    return _bulk_create(items, db)


@router.post("/check-bulk", response_model=TargetCheckOut)
async def check_targets(
    payload: TargetCheckIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetCheckOut:
    account = _select_authorized_account(db, payload.account_id)
    if not account:
        raise HTTPException(status_code=400, detail="no authorized Telegram account available")

    client = build_client(account)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            account.status = "unauthorized"
            db.commit()
            raise HTTPException(status_code=400, detail="account is not authorized")
        results: list[TargetCheckItem] = []
        for item in payload.items:
            results.append(await _check_target_item(client, item, payload.auto_join_invites))
        return TargetCheckOut(
            items=results,
            total=len(results),
            accessible=sum(1 for item in results if item.status == "accessible"),
            failed=sum(1 for item in results if item.status != "accessible"),
        )
    finally:
        await client.disconnect()


@router.post("/bulk", response_model=TargetBulkCreateOut)
def bulk_create_targets(
    payload: TargetBulkCreateIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TargetBulkCreateOut:
    return _bulk_create(payload.items, db)


@router.post("", response_model=TelegramTargetOut)
def create_target(
    payload: TelegramTargetCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramTarget:
    target = TelegramTarget(
        account_id=payload.account_id,
        title=payload.title or payload.target,
        target=payload.target,
        normalized_target=normalize_target(payload.target),
        target_type=payload.target_type,
        enabled=payload.enabled,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return target


def _bulk_create(items: list[TargetParseItem], db: Session) -> TargetBulkCreateOut:
    existing = {
        row.normalized_target: row.id
        for row in db.query(TelegramTarget.id, TelegramTarget.normalized_target).all()
    }
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
        target = TelegramTarget(
            account_id=item.account_id,
            title=item.title or item.target,
            target=item.target,
            normalized_target=item.normalized_target,
            target_type=item.target_type,
            enabled=True,
        )
        db.add(target)
        created.append(target)
        seen.add(item.normalized_target)
    db.commit()
    for target in created:
        db.refresh(target)
    return TargetBulkCreateOut(
        created=created,
        skipped=skipped,
        created_count=len(created),
        skipped_count=len(skipped),
    )


def _target_payload(row: TelegramTarget) -> dict[str, object]:
    return {
        "id": row.id,
        "account_id": row.account_id,
        "title": row.title,
        "target": row.target,
        "normalized_target": row.normalized_target,
        "target_type": row.target_type,
        "enabled": row.enabled,
        "status": row.status,
        "last_message_at": row.last_message_at.isoformat() if row.last_message_at else "",
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
        title = getattr(entity, "title", None) or getattr(entity, "username", None) or item.title
        target_type = "channel" if bool(getattr(entity, "broadcast", False)) and not bool(getattr(entity, "megagroup", False)) else item.target_type
        return _check_result(item, "accessible", "", "目标可访问", title=str(title or item.title), target_type=target_type)
    except FloodWaitError as exc:
        return _check_result(item, "failed", "flood_wait", f"Telegram 限流，等待 {getattr(exc, 'seconds', '?')} 秒")
    except ValueError as exc:
        return _check_result(item, "failed", "not_found", str(exc))
    except RPCError as exc:
        return _check_result(item, "failed", exc.__class__.__name__, str(exc))
    except Exception as exc:
        return _check_result(item, "failed", exc.__class__.__name__, str(exc))


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


def _parse_target_line(line: int, raw: str, account_id: int | None, target_type: str) -> TargetParseItem:
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


def _parse_out(items: list[TargetParseItem]) -> TargetParseOut:
    return TargetParseOut(
        items=items,
        total=len(items),
        importable=sum(1 for item in items if item.status == "ready"),
        duplicated=sum(1 for item in items if item.status == "duplicate"),
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
    if payload.account_id is not None:
        target.account_id = payload.account_id
    if payload.title is not None:
        target.title = payload.title
    if payload.enabled is not None:
        target.enabled = payload.enabled
    db.commit()
    db.refresh(target)
    return target


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
        await runtime.add_target(target_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "listening", "target_id": target_id}


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
        return await runtime.backfill_target(target_id, payload.limit, since_days=payload.since_days)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
