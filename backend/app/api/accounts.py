from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import TelegramAccount, TelegramLoginFlow, User
from app.schemas import (
    TelegramAccountCreate,
    TelegramDialogOut,
    TelegramAccountOut,
    VerifyCodeIn,
    VerifyPasswordIn,
)
from app.telegram.login_flow import build_client
from app.telegram.login_flow import PasswordRequired, send_login_code, verify_login_code, verify_password
from app.telegram.runtime import runtime


router = APIRouter(prefix="/telegram/accounts", tags=["telegram accounts"])


def _session_name(phone: str) -> str:
    cleaned = re.sub(r"[^0-9a-zA-Z_-]+", "_", phone).strip("_")
    return f"account_{cleaned or 'telegram'}"


@router.get("", response_model=list[TelegramAccountOut])
def list_accounts(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[TelegramAccount]:
    return db.query(TelegramAccount).order_by(TelegramAccount.id.desc()).all()


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

    client = build_client(account)
    await client.connect()
    try:
        if not await client.is_user_authorized():
            account.status = "unauthorized"
            db.commit()
            raise HTTPException(status_code=400, detail="account is not authorized")
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
    finally:
        await client.disconnect()


@router.post("", response_model=TelegramAccountOut)
def create_account(
    payload: TelegramAccountCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccount:
    account = TelegramAccount(
        label=payload.label or payload.phone,
        api_id=payload.api_id,
        api_hash=payload.api_hash,
        phone=payload.phone,
        session_name=_session_name(payload.phone),
        proxy_url=payload.proxy_url,
        status="created",
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/send-code", response_model=TelegramAccountOut)
async def send_code(
    account_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccount:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    try:
        phone_code_hash = await send_login_code(account)
        account.status = "code_sent"
        account.last_error = ""
        db.add(TelegramLoginFlow(account_id=account.id, phone_code_hash=phone_code_hash, status="pending_code"))
    except Exception as exc:
        account.status = "error"
        account.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/verify-code", response_model=TelegramAccountOut)
async def verify_code(
    account_id: int,
    payload: VerifyCodeIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccount:
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
        await verify_login_code(account, payload.code, flow.phone_code_hash)
        account.status = "authorized"
        flow.status = "authorized"
        account.last_error = ""
    except PasswordRequired:
        account.status = "password_required"
        flow.status = "password_required"
    except Exception as exc:
        account.status = "error"
        account.last_error = str(exc)
        flow.status = "error"
        flow.error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return account


@router.post("/{account_id}/verify-password", response_model=TelegramAccountOut)
async def verify_two_factor_password(
    account_id: int,
    payload: VerifyPasswordIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TelegramAccount:
    account = db.get(TelegramAccount, account_id)
    if not account:
        raise HTTPException(status_code=404, detail="account not found")
    try:
        await verify_password(account, payload.password)
        account.status = "authorized"
        account.last_error = ""
    except Exception as exc:
        account.status = "error"
        account.last_error = str(exc)
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    db.refresh(account)
    return account


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
        target_ids = await runtime.start_account(account.id)
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "listening", "account_id": account.id, "targets": target_ids}


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
    return {"status": "stopped", "account_id": account.id, "targets": target_ids}
