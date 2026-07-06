from __future__ import annotations

import asyncio
import re
import time
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, func, or_
from sqlalchemy.orm import Session
from telethon.errors import SessionPasswordNeededError

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import AccountEvent, CrawlError, MonitorRun, TelegramAccount, TelegramLoginFlow, TelegramMessage, TelegramTarget, User
from app.services.collection_settings import get_collection_settings
from app.schemas import (
    AccountBulkIn,
    AccountBulkItemOut,
    AccountBulkOut,
    AccountDiagnosisItem,
    AccountDiagnosisOut,
    AccountRuntimeEventOut,
    TelegramAccountCreate,
    TelegramAccountHealthOut,
    TelegramAccountPatch,
    TelegramDialogOut,
    TelegramAccountOut,
    VerifyCodeIn,
    VerifyPasswordIn,
)
from app.telegram.login_flow import build_client
from app.telegram.runtime import runtime


router = APIRouter(prefix="/telegram/accounts", tags=["telegram accounts"])


def _session_name(phone: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_-]+", "_", phone).strip("_")
    return f"account_{cleaned or 'telegram'}"


def _normalize_phone(phone: str) -> str:
    value = re.sub(r"[\s().-]+", "", phone.strip())
    if value.startswith("00"):
        value = f"+{value[2:]}"
    if not re.fullmatch(r"\+[1-9]\d{6,14}", value):
        raise HTTPException(status_code=400, detail="手机号必须包含国际区号，例如 +16513909110")
    return value


def _safe_error(error: object) -> str:
    text = str(error or "").strip()
    if not text:
        return ""
    text = re.sub(r"(api_hash=)[^,\s]+", r"\1***", text, flags=re.I)
    text = re.sub(r"(password=)[^,\s]+", r"\1***", text, flags=re.I)
    text = re.sub(r"//([^:@/\s]+):([^@/\s]+)@", r"//***:***@", text)
    return text[:240]


def _friendly_account_error(error: object) -> str:
    text = _safe_error(error)
    lowered = text.lower()
    if not text:
        return ""
    if "not authorized" in lowered:
        return "账号未授权或 Session 已失效"
    if "database is locked" in lowered:
        return "账号 Session 正在被其他任务占用，请稍后重试"
    if "proxy" in lowered and ("refused" in lowered or "connect" in lowered):
        return "代理连接失败，请检查代理地址和网络出口"
    return text


def _auth_status(account: TelegramAccount) -> str:
    status = str(account.status or "created").lower()
    if status == "code_sent":
        return "code_sent"
    if status == "password_required":
        return "password_required"
    if status == "authorized":
        return "authorized"
    if status in {"unauthorized", "error"}:
        return "unauthorized"
    return "created"


def _runtime_status(account: TelegramAccount, running_ids: set[int]) -> str:
    if account.id in running_ids:
        return "listening"
    if account.health_status == "error" and account.last_error:
        return "error"
    return "stopped"


def _proxy_status(account: TelegramAccount) -> str:
    if not account.proxy_url:
        return "none"
    return account.proxy_status or "unchecked"


def _available_actions(account: TelegramAccount, running_ids: set[int]) -> list[str]:
    auth = _auth_status(account)
    runtime_status = _runtime_status(account, running_ids)
    actions: list[str] = ["details", "edit", "diagnose"]
    if account.proxy_url:
        actions.append("test_proxy")
    if auth != "authorized":
        actions.append("authorize")
        actions.append("delete")
        return actions
    actions.append("reauthorize")
    if account.is_active and runtime_status != "listening":
        actions.append("start")
    if runtime_status == "listening":
        actions.extend(["stop", "logs"])
    actions.append("delete")
    return actions


def _last_message_times(db: Session) -> dict[int, datetime]:
    rows = (
        db.query(TelegramMessage.account_id, func.max(TelegramMessage.event_time))
        .filter(TelegramMessage.account_id.is_not(None))
        .group_by(TelegramMessage.account_id)
        .all()
    )
    return {int(account_id): last_at for account_id, last_at in rows if account_id and last_at}


def _target_counts(db: Session) -> tuple[dict[int, int], dict[int, int]]:
    rows = (
        db.query(
            TelegramTarget.account_id,
            func.count(TelegramTarget.id),
            func.sum(case((TelegramTarget.status == "listening", 1), else_=0)),
        )
        .filter(TelegramTarget.account_id.is_not(None))
        .group_by(TelegramTarget.account_id)
        .all()
    )
    bound: dict[int, int] = {}
    listening: dict[int, int] = {}
    for account_id, total, running_count in rows:
        if account_id:
            bound[int(account_id)] = int(total or 0)
            listening[int(account_id)] = int(running_count or 0)
    return bound, listening


def _account_out(account: TelegramAccount, running_ids: set[int], bound_counts: dict[int, int], listening_counts: dict[int, int], last_messages: dict[int, datetime]) -> TelegramAccountOut:
    bound = bound_counts.get(account.id, account.health_target_count or 0)
    listening_count = listening_counts.get(account.id, account.health_listening_target_count or 0)
    last_checked_at = account.health_checked_at or account.proxy_checked_at
    return TelegramAccountOut(
        id=account.id,
        label=account.label,
        phone=account.phone,
        session_name="",
        proxy_url="",
        status=account.status,
        is_active=account.is_active,
        last_error=_safe_error(account.last_error),
        health_status=account.health_status or "unchecked",
        health_message=_safe_error(account.health_message),
        health_me=account.health_me or "",
        health_target_count=bound,
        health_listening_target_count=listening_count,
        health_checked_at=account.health_checked_at,
        proxy_status=_proxy_status(account),
        proxy_latency_ms=account.proxy_latency_ms,
        proxy_message=_safe_error(account.proxy_message),
        proxy_checked_at=account.proxy_checked_at,
        authorization_status=_auth_status(account),
        runtime_status=_runtime_status(account, running_ids),
        bound_target_count=bound,
        listening_target_count=listening_count,
        last_message_at=last_messages.get(account.id),
        last_checked_at=last_checked_at,
        available_actions=_available_actions(account, running_ids),
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def _single_account_out(db: Session, account: TelegramAccount) -> TelegramAccountOut:
    running_ids = runtime.running_account_ids()
    bound_counts, listening_counts = _target_counts(db)
    last_messages = _last_message_times(db)
    return _account_out(account, running_ids, bound_counts, listening_counts, last_messages)


def _record_account_event(db: Session, account_id: int | None, event_type: str, status: str, summary: str, detail: str = "") -> None:
    db.add(AccountEvent(account_id=account_id, event_type=event_type, status=status, summary=summary[:255], detail=_safe_error(detail)))


async def _probe_proxy_url(proxy_url: str) -> tuple[str, int | None, str]:
    if not proxy_url:
        return "none", None, "未配置代理"
    parsed = urlparse(proxy_url)
    if parsed.scheme.lower() not in {"socks5", "socks4", "http"} or not parsed.hostname or not parsed.port:
        return "failed", None, "代理地址不完整或协议不支持"
    started = time.perf_counter()
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(parsed.hostname, parsed.port), timeout=6)
        writer.close()
        await writer.wait_closed()
    except Exception as exc:
        return "failed", None, _safe_error(exc) or "代理端口不可连接"
    latency = int((time.perf_counter() - started) * 1000)
    if latency > 1500:
        return "slow", latency, f"代理端口可连接，延迟 {latency}ms"
    return "ok", latency, f"代理端口可连接，延迟 {latency}ms"


async def _run_proxy_probe(account: TelegramAccount, db: Session) -> AccountDiagnosisItem:
    started = time.perf_counter()
    status, latency, message = await _probe_proxy_url(account.proxy_url)
    account.proxy_status = status
    account.proxy_latency_ms = latency
    account.proxy_message = message
    account.proxy_checked_at = datetime.now(timezone.utc)
    _record_account_event(
        db,
        account.id,
        "proxy_check",
        "success" if status in {"none", "ok", "slow"} else "failed",
        "代理检测完成",
        message,
    )
    return AccountDiagnosisItem(
        key="proxy",
        label="代理连接",
        status=status,
        duration_ms=int((time.perf_counter() - started) * 1000),
        result=message,
        suggestion="未配置代理时依赖服务器直连 Telegram。" if status == "none" else "代理可用。" if status in {"ok", "slow"} else "检查代理类型、主机、端口和认证信息。",
    )


def _runtime_diagnosis(account: TelegramAccount, running_ids: set[int]) -> AccountDiagnosisItem:
    status = _runtime_status(account, running_ids)
    return AccountDiagnosisItem(
        key="runtime",
        label="Runtime 状态",
        status=status,
        result="账号正在监听" if status == "listening" else "账号未监听" if status == "stopped" else "运行异常",
        suggestion="可在运行页签停止监听。" if status == "listening" else "已授权且启用后可以启动监听。",
    )


def _target_diagnosis(account: TelegramAccount) -> AccountDiagnosisItem:
    target_count = len(account.targets)
    listening_count = sum(1 for target in account.targets if target.status == "listening")
    status = "ok" if target_count else "warning"
    return AccountDiagnosisItem(
        key="targets",
        label="目标绑定",
        status=status,
        result=f"{target_count} 个绑定目标，{listening_count} 个监听中",
        suggestion="暂无绑定目标，建议分配监控目标。" if not target_count else "目标负载可继续在目标页调整。",
    )


@router.get("", response_model=list[TelegramAccountOut])
def list_accounts(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TelegramAccountOut]:
    accounts = db.query(TelegramAccount).order_by(TelegramAccount.id.desc()).all()
    running_ids = runtime.running_account_ids()
    bound_counts, listening_counts = _target_counts(db)
    last_messages = _last_message_times(db)
    return [_account_out(account, running_ids, bound_counts, listening_counts, last_messages) for account in accounts]


@router.post("/bulk", response_model=AccountBulkOut)
async def bulk_account_action(
    payload: AccountBulkIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountBulkOut:
    allowed = {"check", "start", "stop", "enable", "disable"}
    if payload.action not in allowed:
        raise HTTPException(status_code=400, detail="unsupported bulk action")
    ids = list(dict.fromkeys(payload.account_ids))
    accounts = db.query(TelegramAccount).filter(TelegramAccount.id.in_(ids)).all() if ids else []
    by_id = {account.id: account for account in accounts}
    running_ids = runtime.running_account_ids()
    items: list[AccountBulkItemOut] = []

    def eligible(account: TelegramAccount) -> tuple[bool, str]:
        if payload.action == "check":
            return account.is_active, "账号已禁用"
        if payload.action == "start":
            if _auth_status(account) != "authorized":
                return False, "未授权"
            if not account.is_active:
                return False, "已禁用"
            if account.id in running_ids:
                return False, "已在监听"
            return True, ""
        if payload.action == "stop":
            return account.id in running_ids, "未在监听"
        if payload.action in {"enable", "disable"}:
            desired = payload.action == "enable"
            return account.is_active != desired, "状态无需变更"
        return False, "不支持"

    for account_id in ids:
        account = by_id.get(account_id)
        if not account:
            items.append(AccountBulkItemOut(account_id=account_id, eligible=False, status="skipped", message="账号不存在"))
            continue
        ok, reason = eligible(account)
        if not ok:
            items.append(AccountBulkItemOut(account_id=account.id, label=account.label, eligible=False, status="skipped", message=reason))
            continue
        try:
            if payload.action == "check":
                await diagnose_account(account.id, _user, db)
                message = "检测完成"
            elif payload.action == "start":
                await runtime.start_account(account.id)
                account.health_status = "listening"
                _record_account_event(db, account.id, "start_listener", "success", "批量启动监听成功")
                message = "监听已启动"
            elif payload.action == "stop":
                await runtime.stop_account(account.id)
                account.health_status = "available" if account.status == "authorized" else account.health_status
                account.health_listening_target_count = 0
                _record_account_event(db, account.id, "stop_listener", "success", "批量停止监听成功")
                message = "监听已停止"
            elif payload.action == "enable":
                account.is_active = True
                _record_account_event(db, account.id, "account_enable", "success", "批量启用账号")
                message = "已启用"
            else:
                account.is_active = False
                _record_account_event(db, account.id, "account_disable", "success", "批量禁用账号")
                message = "已禁用"
            db.commit()
            items.append(AccountBulkItemOut(account_id=account.id, label=account.label, eligible=True, status="success", message=message))
        except Exception as exc:
            db.rollback()
            items.append(AccountBulkItemOut(account_id=account.id, label=account.label, eligible=True, status="failed", message=_safe_error(exc)))

    executable = sum(1 for item in items if item.eligible)
    succeeded = sum(1 for item in items if item.status == "success")
    failed = sum(1 for item in items if item.status == "failed")
    skipped = sum(1 for item in items if item.status == "skipped")
    return AccountBulkOut(
        action=payload.action,
        selected=len(ids),
        executable=executable,
        skipped=skipped,
        succeeded=succeeded,
        failed=failed,
        items=items,
    )


@router.get("/{account_id}/dialogs", response_model=list[TelegramDialogOut])
async def list_account_dialogs(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TelegramDialogOut]:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    if account.status != "authorized":
        raise HTTPException(status_code=400, detail="account is not authorized")

    async def load_dialogs(client):
        rows: list[TelegramDialogOut] = []
        async for dialog in client.iter_dialogs():
            if not (dialog.is_group or dialog.is_channel):
                continue
            entity = dialog.entity
            username = str(getattr(entity, "username", "") or "")
            chat_id = str(getattr(entity, "id", "") or "")
            is_channel = bool(getattr(entity, "broadcast", False))
            is_megagroup = bool(getattr(entity, "megagroup", False))
            target_type = "channel" if is_channel and not is_megagroup else "group"
            normalized = username or chat_id
            target = f"https://t.me/{username}" if username else chat_id
            last_message_at = getattr(dialog.message, "date", None) if dialog.message else None
            rows.append(
                TelegramDialogOut(
                    account_id=account.id,
                    title=dialog.name or username or chat_id,
                    target=target,
                    normalized_target=normalized,
                    target_type=target_type,
                    dialog_type="channel" if is_channel else "supergroup" if is_megagroup else "group",
                    username=username,
                    chat_id=chat_id,
                    participants_count=getattr(entity, "participants_count", None),
                    last_message_at=last_message_at,
                    status="ready" if normalized else "invalid",
                    reason="" if normalized else "无法识别目标 ID",
                )
            )
        return rows

    try:
        return await runtime.with_account_client(account.id, load_dialogs)
    except RuntimeError as exc:
        account.status = "unauthorized"
        account.last_error = _friendly_account_error(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=account.last_error) from exc
    except Exception as exc:
        account.last_error = _friendly_account_error(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=account.last_error) from exc


@router.post("", response_model=TelegramAccountOut)
def create_account(
    payload: TelegramAccountCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccountOut:
    label = payload.label.strip()
    phone = _normalize_phone(payload.phone)
    if db.query(TelegramAccount).filter(TelegramAccount.phone == phone).first():
        raise HTTPException(status_code=400, detail="该手机号账号已存在")
    account = TelegramAccount(
        label=label,
        api_id=payload.api_id,
        api_hash=payload.api_hash,
        phone=phone,
        session_name=_session_name(phone),
        proxy_url=payload.proxy_url.strip(),
        status="created",
    )
    db.add(account)
    db.flush()
    _record_account_event(db, account.id, "account_create", "success", f"新增账号 {label}")
    db.commit()
    db.refresh(account)
    return _single_account_out(db, account)


@router.delete("/{account_id}")
async def delete_account(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    stopped_targets = await runtime.stop_account(account.id)
    db.query(TelegramTarget).filter(TelegramTarget.account_id == account.id).update(
        {TelegramTarget.account_id: None, TelegramTarget.status: "idle"},
        synchronize_session=False,
    )
    db.query(TelegramMessage).filter(TelegramMessage.account_id == account.id).update(
        {TelegramMessage.account_id: None},
        synchronize_session=False,
    )
    db.query(MonitorRun).filter(MonitorRun.account_id == account.id).update(
        {MonitorRun.account_id: None},
        synchronize_session=False,
    )
    db.query(CrawlError).filter(CrawlError.account_id == account.id).update(
        {CrawlError.account_id: None},
        synchronize_session=False,
    )
    db.query(TelegramLoginFlow).filter(TelegramLoginFlow.account_id == account.id).delete(synchronize_session=False)
    db.delete(account)
    db.commit()
    return {"deleted": True, "account_id": account_id, "stopped_targets": stopped_targets}


@router.patch("/{account_id}", response_model=TelegramAccountOut)
def patch_account(
    account_id: int,
    payload: TelegramAccountPatch,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccountOut:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    if payload.label is not None:
        label = payload.label.strip()
        if not label:
            raise HTTPException(status_code=400, detail="账号名称不能为空")
        account.label = label
    if payload.proxy_url is not None:
        account.proxy_url = payload.proxy_url.strip()
        account.proxy_status = "unchecked" if account.proxy_url else "none"
        account.proxy_latency_ms = None
        account.proxy_message = ""
        account.proxy_checked_at = None
    if payload.is_active is not None:
        account.is_active = payload.is_active
        _record_account_event(db, account.id, "account_enable" if payload.is_active else "account_disable", "success", "账号已启用" if payload.is_active else "账号已禁用")
    else:
        _record_account_event(db, account.id, "account_update", "success", "账号配置已更新")
    db.commit()
    db.refresh(account)
    return _single_account_out(db, account)


@router.post("/{account_id}/send-code", response_model=TelegramAccountOut)
async def send_code(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccountOut:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    try:
        async def request_code(client):
            sent = await client.send_code_request(account.phone)
            return sent.phone_code_hash

        phone_code_hash = await runtime.with_account_session_client(account.id, request_code, require_authorized=False)
        account.status = "code_sent"
        account.last_error = ""
        db.add(TelegramLoginFlow(account_id=account.id, phone_code_hash=phone_code_hash, status="pending_code"))
        _record_account_event(db, account.id, "send_code", "success", "验证码已发送")
    except Exception as exc:
        account.status = "error"
        account.last_error = _friendly_account_error(exc)
        _record_account_event(db, account.id, "send_code", "failed", "验证码发送失败", str(exc))
        db.commit()
        raise HTTPException(status_code=400, detail=account.last_error) from exc
    db.commit()
    db.refresh(account)
    return _single_account_out(db, account)


@router.post("/{account_id}/verify-code", response_model=TelegramAccountOut)
async def verify_code(
    account_id: int,
    payload: VerifyCodeIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccountOut:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    flow = (
        db.query(TelegramLoginFlow)
        .filter(TelegramLoginFlow.account_id == account.id)
        .order_by(TelegramLoginFlow.id.desc())
        .first()
    )
    if not flow:
        raise HTTPException(status_code=400, detail="send code first")
    try:
        async def sign_in_with_code(client):
            await client.sign_in(account.phone, code=payload.code, phone_code_hash=flow.phone_code_hash)

        await runtime.with_account_session_client(account.id, sign_in_with_code, require_authorized=False)
        account.status = "authorized"
        flow.status = "authorized"
        account.last_error = ""
        _record_account_event(db, account.id, "verify_code", "success", "验证码验证成功")
    except SessionPasswordNeededError:
        account.status = "password_required"
        flow.status = "password_required"
        _record_account_event(db, account.id, "verify_code", "pending", "需要二步验证")
    except Exception as exc:
        account.status = "error"
        account.last_error = _friendly_account_error(exc)
        flow.status = "error"
        flow.error = account.last_error
        _record_account_event(db, account.id, "verify_code", "failed", "验证码验证失败", str(exc))
        db.commit()
        raise HTTPException(status_code=400, detail=account.last_error) from exc
    db.commit()
    db.refresh(account)
    return _single_account_out(db, account)


@router.post("/{account_id}/verify-password", response_model=TelegramAccountOut)
async def verify_two_factor_password(
    account_id: int,
    payload: VerifyPasswordIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccountOut:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    try:
        async def sign_in_with_password(client):
            await client.sign_in(password=payload.password)

        await runtime.with_account_session_client(account.id, sign_in_with_password, require_authorized=False)
        account.status = "authorized"
        account.last_error = ""
        _record_account_event(db, account.id, "verify_password", "success", "二步验证成功")
    except Exception as exc:
        account.status = "error"
        account.last_error = _friendly_account_error(exc)
        _record_account_event(db, account.id, "verify_password", "failed", "二步验证失败", str(exc))
        db.commit()
        raise HTTPException(status_code=400, detail=account.last_error) from exc
    db.commit()
    db.refresh(account)
    return _single_account_out(db, account)


@router.post("/{account_id}/start")
async def start_account_targets(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    if account.status != "authorized":
        raise HTTPException(status_code=400, detail="account is not authorized")
    try:
        target_ids = [
            row.id
            for row in db.query(TelegramTarget.id)
            .filter(
                TelegramTarget.enabled == True,  # noqa: E712
                or_(TelegramTarget.account_id == account.id, TelegramTarget.account_id.is_(None)),
            )
            .order_by(TelegramTarget.id.asc())
            .all()
        ]
        collection_config = get_collection_settings(db)
        for target_id in target_ids:
            if int(collection_config["initial_backfill_limit"]) > 0:
                await runtime.backfill_target(
                    target_id,
                    int(collection_config["initial_backfill_limit"]),
                    since_hours=int(collection_config["initial_backfill_window_hours"]),
                )
        target_ids = await runtime.start_account(account.id)
    except RuntimeError as exc:
        _record_account_event(db, account.id, "start_listener", "failed", "启动监听失败", str(exc))
        db.commit()
        raise HTTPException(status_code=400, detail=_safe_error(exc)) from exc
    _record_account_event(db, account.id, "start_listener", "success", f"监听已启动，目标 {len(target_ids)} 个")
    account.health_status = "listening"
    account.health_listening_target_count = len(target_ids)
    account.health_target_count = max(account.health_target_count or 0, len(target_ids))
    account.health_checked_at = datetime.now(timezone.utc)
    db.commit()
    return {
        "status": "listening",
        "account_id": account.id,
        "targets": target_ids,
        "backfilled": int(collection_config["initial_backfill_limit"]),
        "backfill_window_hours": int(collection_config["initial_backfill_window_hours"]),
    }


@router.post("/{account_id}/stop")
async def stop_account_targets(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    target_ids = await runtime.stop_account(account.id)
    _record_account_event(db, account.id, "stop_listener", "success", f"监听已停止，目标 {len(target_ids)} 个")
    account.health_status = "available" if account.status == "authorized" else account.health_status
    account.health_listening_target_count = 0
    account.health_checked_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "stopped", "account_id": account.id, "targets": target_ids}


@router.post("/{account_id}/health", response_model=TelegramAccountHealthOut)
async def check_account_health(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccountHealthOut:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")

    running_ids = runtime.running_account_ids()
    target_count = len(account.targets)
    listening_target_count = sum(1 for target in account.targets if target.status == "listening")
    listening = account.id in running_ids
    authorized = False
    me = ""
    message = "账号未授权"
    severity = "error"

    try:
        async def probe(client):
            user = await client.get_me()
            username = getattr(user, "username", None) or ""
            phone = getattr(user, "phone", None) or account.phone
            return f"@{username}" if username else str(phone or getattr(user, "id", ""))

        me = await runtime.with_account_client(account.id, probe)
        authorized = True
        message = "账号可用，Session 有效"
        severity = "ok" if listening else "warning"
        if account.status != "authorized":
            account.status = "authorized"
        account.last_error = ""
    except RuntimeError as exc:
        account.status = "unauthorized"
        account.last_error = _friendly_account_error(exc) or "Session 未授权或已失效"
        message = account.last_error
    except Exception as exc:
        account.status = "error"
        account.last_error = _friendly_account_error(exc)
        message = account.last_error

    health_status = "listening" if authorized and listening else "available" if authorized else "error"
    account.health_status = health_status
    account.health_message = message
    account.health_me = me
    account.health_target_count = target_count
    account.health_listening_target_count = listening_target_count
    account.health_checked_at = datetime.now(timezone.utc)
    _record_account_event(
        db,
        account.id,
        "health_check",
        "success" if authorized else "failed",
        message,
        account.last_error,
    )
    db.commit()
    return TelegramAccountHealthOut(
        account_id=account.id,
        status=account.status,
        listening=listening,
        authorized=authorized,
        healthy=authorized and not account.last_error,
        severity=severity if authorized else "error",
        target_count=target_count,
        listening_target_count=listening_target_count,
        proxy_configured=bool(account.proxy_url),
        me=me,
        message=message,
        last_error=account.last_error,
    )


@router.post("/{account_id}/proxy-check", response_model=AccountDiagnosisItem)
async def check_account_proxy(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountDiagnosisItem:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    item = await _run_proxy_probe(account, db)
    db.commit()
    return item


@router.post("/{account_id}/diagnostics", response_model=AccountDiagnosisOut)
async def diagnose_account(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AccountDiagnosisOut:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    checked_at = datetime.now(timezone.utc)
    items: list[AccountDiagnosisItem] = []
    items.append(await _run_proxy_probe(account, db))

    started = time.perf_counter()
    telegram_status = "failed"
    telegram_result = "未连接"
    session_status = "failed"
    session_result = "Session 未授权"
    identity_result = ""
    try:
        async def probe(client):
            user = await client.get_me()
            username = getattr(user, "username", None) or ""
            phone = getattr(user, "phone", None) or account.phone
            return f"@{username}" if username else str(phone or getattr(user, "id", ""))

        identity_result = await runtime.with_account_client(account.id, probe)
        telegram_status = "ok"
        telegram_result = "Telegram 连接成功"
        session_status = "ok"
        session_result = "Session 有效"
        account.status = "authorized"
        account.health_status = "listening" if account.id in runtime.running_account_ids() else "available"
        account.health_me = identity_result
        account.health_message = "账号可用，Session 有效"
        account.last_error = ""
    except RuntimeError as exc:
        telegram_result = _friendly_account_error(exc) or "Session 未授权或已失效"
        session_result = telegram_result
        account.status = "unauthorized"
        account.health_status = "error"
        account.health_message = telegram_result
        account.last_error = telegram_result
    except Exception as exc:
        telegram_result = _friendly_account_error(exc) or "Telegram 连接失败"
        session_result = telegram_result
        account.status = "error"
        account.health_status = "error"
        account.health_message = telegram_result
        account.last_error = telegram_result
    duration_ms = int((time.perf_counter() - started) * 1000)
    account.health_target_count = len(account.targets)
    account.health_listening_target_count = sum(1 for target in account.targets if target.status == "listening")
    account.health_checked_at = checked_at
    items.extend(
        [
            AccountDiagnosisItem(
                key="telegram",
                label="Telegram 连接",
                status=telegram_status,
                duration_ms=duration_ms,
                result=telegram_result,
                suggestion="连接成功。" if telegram_status == "ok" else "优先检查代理与网络出口。",
            ),
            AccountDiagnosisItem(
                key="session",
                label="Session 有效性",
                status=session_status,
                result=session_result,
                suggestion="Session 可用。" if session_status == "ok" else "重新发送验证码完成授权。",
            ),
            AccountDiagnosisItem(
                key="identity",
                label="账号身份读取",
                status="ok" if identity_result else "warning",
                result=identity_result or "未读取到账号身份",
                suggestion="能读取身份说明授权链路基本正常。" if identity_result else "授权后再次检测。",
            ),
            _runtime_diagnosis(account, runtime.running_account_ids()),
            _target_diagnosis(account),
        ]
    )
    _record_account_event(db, account.id, "diagnostics", "success" if session_status == "ok" else "failed", "账号诊断完成")
    db.commit()
    return AccountDiagnosisOut(
        account_id=account.id,
        authorization_status=_auth_status(account),
        health_status=account.health_status or "unchecked",
        proxy_status=_proxy_status(account),
        runtime_status=_runtime_status(account, runtime.running_account_ids()),
        checked_at=checked_at,
        items=items,
    )


@router.get("/{account_id}/events", response_model=list[AccountRuntimeEventOut])
def account_events(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AccountRuntimeEventOut]:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    rows = (
        db.query(AccountEvent)
        .filter(AccountEvent.account_id == account.id)
        .order_by(AccountEvent.created_at.desc())
        .limit(50)
        .all()
    )
    return rows
