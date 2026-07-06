from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel
from sqlalchemy import delete, desc, or_, update
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import MessageMedia, NotificationDelivery, RuleHit, TelegramMessage, TelegramTarget, User
from app.notifications.dispatcher import dispatch_for_message
from app.schemas import MessageMediaOut, MessageOut, RuleHitOut, RuleHitPatch
from app.services.enrichment import translate_message_text
from app.services.intelligence_settings import effective_translation_target, get_intelligence_settings
from app.services.json_utils import loads_list


router = APIRouter(tags=["messages"])


class MessageTranslateIn(BaseModel):
    target_language: str = ""


class MessageBulkDeleteIn(BaseModel):
    message_ids: list[int] = []
    target_id: int | None = None


class MessageDeleteOut(BaseModel):
    deleted: int
    deleted_hits: int = 0
    deleted_media: int = 0


def _message_out(row: TelegramMessage, target_title: str = "", translation_target: str = "") -> MessageOut:
    return MessageOut(
        id=row.id,
        message_uid=row.message_uid,
        channel=row.channel,
        account_id=row.account_id,
        target_id=row.target_id,
        target_title=target_title,
        source=row.source,
        source_id=row.source_id,
        source_type=row.source_type,
        sub_channel=row.sub_channel,
        message_id=row.message_id,
        event_time=row.event_time,
        insert_time=row.insert_time,
        sender_id=row.sender_id,
        sender_username=row.sender_username,
        sender_name=row.sender_name,
        content=row.content,
        language=row.language,
        translated_content=row.translated_content,
        translation_status=row.translation_status,
        translation_engine=row.translation_engine,
        translation_target=translation_target,
        ocr_text=row.ocr_text,
        ocr_status=row.ocr_status,
        ocr_engine=row.ocr_engine,
        content_md5=row.content_md5,
        data_id=row.data_id,
        similar_id=row.similar_id,
        original_content=row.original_content,
        desc=row.desc,
        category=row.category,
        message_kind=row.message_kind,
        media_type=row.media_type,
        media_name=_media_name(row.raw_payload),
        raw_name=_raw_name(row.raw_payload),
        media_count=row.media_count,
        media_items=[
            MessageMediaOut(
                id=item.id,
                media_index=item.media_index,
                media_kind=item.media_kind,
                file_name=item.file_name,
                mime_type=item.mime_type,
                size=item.size,
                download_status=item.download_status,
                ocr_status=item.ocr_status,
                ocr_engine=item.ocr_engine,
                ocr_text=item.ocr_text,
                error=item.error,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in sorted(row.media_items, key=lambda media: media.media_index)
        ],
        links=[str(item) for item in loads_list(row.links_json)],
        views_count=row.views_count,
        replies_count=row.replies_count,
        forwards_count=row.forwards_count,
        risk_level=row.risk_level,
        score=row.score,
        hit=row.hit,
        keyword_type=row.keyword_type,
        keyword_source=row.keyword_source,
        status=row.status,
        created_at=row.created_at,
    )


def _media_name(raw_payload: str) -> str:
    try:
        payload = json.loads(raw_payload or "{}")
    except json.JSONDecodeError:
        return ""
    webpage = ((payload.get("media") or {}).get("webpage") or {})
    webpage_title = webpage.get("title") or webpage.get("site_name")
    if webpage_title:
        return str(webpage_title)
    document = ((payload.get("media") or {}).get("document") or {})
    attributes = document.get("attributes") or []
    for attribute in attributes:
        if not isinstance(attribute, dict):
            continue
        file_name = attribute.get("file_name") or attribute.get("filename")
        if file_name:
            return str(file_name)
    return _fallback_media_name(document)


def _raw_name(raw_payload: str) -> str:
    try:
        payload = json.loads(raw_payload or "{}")
    except json.JSONDecodeError:
        return ""
    action_name = (payload.get("action") or {}).get("_")
    if action_name:
        return str(action_name)
    media_name = (payload.get("media") or {}).get("_")
    if media_name:
        return str(media_name)
    return str(payload.get("_") or "")


def _fallback_media_name(document: dict[str, Any]) -> str:
    mime_type = str(document.get("mime_type") or "")
    document_id = str(document.get("id") or "")
    if not document_id:
        return ""
    extension = {
        "text/plain": ".txt",
        "application/pdf": ".pdf",
        "application/zip": ".zip",
        "application/vnd.android.package-archive": ".apk",
    }.get(mime_type, "")
    return f"{document_id}{extension}" if extension else document_id


@router.get("/messages", response_model=list[MessageOut])
def list_messages(
    keyword: str = "",
    source: str = "",
    sender: str = "",
    target_id: int | None = None,
    has_links: bool | None = None,
    has_media: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_risk_level: int = 0,
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    query = _message_query(db, keyword, source, sender, target_id, has_links, has_media, date_from, date_to, min_risk_level)
    rows = query.order_by(desc(TelegramMessage.event_time)).offset(offset).limit(limit).all()
    target_titles = _target_titles(db, rows)
    translation_target = effective_translation_target(get_intelligence_settings(db))
    return [_message_out(row, target_titles.get(row.target_id, ""), translation_target) for row in rows]


@router.get("/messages/count")
def count_messages(
    keyword: str = "",
    source: str = "",
    sender: str = "",
    target_id: int | None = None,
    has_links: bool | None = None,
    has_media: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_risk_level: int = 0,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    query = _message_query(db, keyword, source, sender, target_id, has_links, has_media, date_from, date_to, min_risk_level)
    return {"total": query.count()}


@router.get("/messages/export")
def export_messages(
    ids: str = "",
    keyword: str = "",
    source: str = "",
    sender: str = "",
    target_id: int | None = None,
    has_links: bool | None = None,
    has_media: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_risk_level: int = 0,
    format: str = "csv",
    limit: int = Query(default=1000, le=5000),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    query = _message_query(db, keyword, source, sender, target_id, has_links, has_media, date_from, date_to, min_risk_level)
    selected_ids = [int(item) for item in ids.split(",") if item.strip().isdigit()]
    if selected_ids:
        query = query.filter(TelegramMessage.id.in_(selected_ids))
    rows = query.order_by(desc(TelegramMessage.event_time)).limit(limit).all()
    target_titles = _target_titles(db, rows)
    translation_target = effective_translation_target(get_intelligence_settings(db))
    payload = [_message_out(row, target_titles.get(row.target_id, ""), translation_target).model_dump(mode="json") for row in rows]
    if format.lower() == "json":
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": "attachment; filename=watchout-telegram-messages.json"},
        )

    buffer = io.StringIO()
    fieldnames = [
        "id",
        "message_uid",
        "content_md5",
        "data_id",
        "target_title",
        "source",
        "source_id",
        "message_id",
        "event_time",
        "insert_time",
        "sender_username",
        "sender_name",
        "content",
        "message_kind",
        "media_type",
        "media_name",
        "raw_name",
        "links",
        "risk_level",
        "status",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for item in payload:
        writer.writerow({key: ",".join(item[key]) if key == "links" else item.get(key, "") for key in fieldnames})
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=watchout-telegram-messages.csv"},
    )


@router.post("/messages/{message_id}/translate", response_model=MessageOut)
def translate_message(
    message_id: int,
    payload: MessageTranslateIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageOut:
    row = db.get(TelegramMessage, message_id)
    if not row:
        raise HTTPException(status_code=404, detail="message not found")
    settings = get_intelligence_settings(db)
    target_language = payload.target_language or effective_translation_target(settings)
    translate_message_text(row, settings, target_language=target_language)
    db.commit()
    db.refresh(row)
    target_title = ""
    if row.target_id:
        target = db.get(TelegramTarget, row.target_id)
        target_title = target.title if target else ""
    return _message_out(row, target_title, target_language)


@router.delete("/messages/bulk", response_model=MessageDeleteOut)
def bulk_delete_messages(
    payload: MessageBulkDeleteIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageDeleteOut:
    selected_ids = [int(item) for item in dict.fromkeys(payload.message_ids) if item]
    if selected_ids:
        return _delete_messages(db, selected_ids)
    if payload.target_id:
        return _delete_messages_by_target(db, payload.target_id)
    raise HTTPException(status_code=400, detail="message_ids or target_id is required")


@router.delete("/messages/{message_id}", response_model=MessageDeleteOut)
def delete_message(
    message_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MessageDeleteOut:
    return _delete_messages(db, [message_id])


def _message_query(
    db: Session,
    keyword: str = "",
    source: str = "",
    sender: str = "",
    target_id: int | None = None,
    has_links: bool | None = None,
    has_media: bool | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_risk_level: int = 0,
):
    query = db.query(TelegramMessage)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            or_(
                TelegramMessage.content.like(like),
                TelegramMessage.translated_content.like(like),
                TelegramMessage.ocr_text.like(like),
                TelegramMessage.source.like(like),
                TelegramMessage.sender_username.like(like),
                TelegramMessage.sender_name.like(like),
                TelegramMessage.links_json.like(like),
                TelegramMessage.raw_payload.like(like),
            )
        )
    if source:
        query = query.filter(TelegramMessage.source.like(f"%{source}%"))
    if sender:
        like = f"%{sender}%"
        query = query.filter(or_(TelegramMessage.sender_username.like(like), TelegramMessage.sender_name.like(like), TelegramMessage.sender_id.like(like)))
    if target_id:
        query = query.filter(TelegramMessage.target_id == target_id)
    if has_links is not None:
        query = query.filter(TelegramMessage.links_json != "[]" if has_links else TelegramMessage.links_json == "[]")
    if has_media is not None:
        query = query.filter(TelegramMessage.media_count > 0 if has_media else TelegramMessage.media_count == 0)
    if date_from:
        query = query.filter(TelegramMessage.event_time >= date_from)
    if date_to:
        query = query.filter(TelegramMessage.event_time <= date_to)
    if min_risk_level:
        query = query.filter(TelegramMessage.risk_level >= min_risk_level)
    return query


def _delete_messages(db: Session, message_ids: list[int]) -> MessageDeleteOut:
    ids = [int(item) for item in dict.fromkeys(message_ids) if item]
    if not ids:
        return MessageDeleteOut(deleted=0)
    existing_ids = [row.id for row in db.query(TelegramMessage.id).filter(TelegramMessage.id.in_(ids)).all()]
    if not existing_ids:
        return MessageDeleteOut(deleted=0)
    db.query(NotificationDelivery).filter(NotificationDelivery.message_id.in_(existing_ids)).update(
        {NotificationDelivery.message_id: None},
        synchronize_session=False,
    )
    deleted_hits = db.query(RuleHit).filter(RuleHit.message_id.in_(existing_ids)).delete(synchronize_session=False)
    deleted_media = db.query(MessageMedia).filter(MessageMedia.message_id.in_(existing_ids)).delete(synchronize_session=False)
    deleted = db.query(TelegramMessage).filter(TelegramMessage.id.in_(existing_ids)).delete(synchronize_session=False)
    db.commit()
    return MessageDeleteOut(deleted=int(deleted), deleted_hits=int(deleted_hits), deleted_media=int(deleted_media))


def _delete_messages_by_target(db: Session, target_id: int) -> MessageDeleteOut:
    message_filter = TelegramMessage.target_id == target_id
    message_count = db.query(TelegramMessage.id).filter(message_filter).limit(1).first()
    if not message_count:
        return MessageDeleteOut(deleted=0)
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
    deleted = db.query(TelegramMessage).filter(message_filter).delete(synchronize_session=False)
    db.commit()
    return MessageDeleteOut(deleted=int(deleted), deleted_hits=int(deleted_hits), deleted_media=int(deleted_media))


def _target_titles(db: Session, rows: list[TelegramMessage]) -> dict[int | None, str]:
    target_ids = sorted({row.target_id for row in rows if row.target_id})
    if not target_ids:
        return {}
    targets = db.query(TelegramTarget.id, TelegramTarget.title).filter(TelegramTarget.id.in_(target_ids)).all()
    return {target_id: title or "" for target_id, title in targets}


def _hit_query(
    db: Session,
    status: str = "",
    rule_id: int | None = None,
    min_risk_level: int = 0,
    keyword: str = "",
):
    query = db.query(RuleHit)
    if status:
        query = query.filter(RuleHit.status == status)
    if rule_id:
        query = query.filter(RuleHit.rule_id == rule_id)
    if min_risk_level:
        query = query.filter(RuleHit.risk_level >= min_risk_level)
    if keyword:
        like = f"%{keyword}%"
        query = query.join(TelegramMessage, RuleHit.message_id == TelegramMessage.id).filter(
            or_(
                RuleHit.rule_name.like(like),
                RuleHit.matched_patterns_json.like(like),
                TelegramMessage.content.like(like),
                TelegramMessage.translated_content.like(like),
                TelegramMessage.ocr_text.like(like),
                TelegramMessage.source.like(like),
                TelegramMessage.sender_username.like(like),
                TelegramMessage.sender_name.like(like),
            )
        )
    return query


def _hit_out(
    row: RuleHit,
    target_title: str = "",
    translation_target: str = "",
    include_message: bool = True,
) -> RuleHitOut:
    return RuleHitOut(
        id=row.id,
        message_id=row.message_id,
        rule_id=row.rule_id,
        rule_name=row.rule_name,
        matched_patterns=[str(item) for item in loads_list(row.matched_patterns_json)],
        risk_level=row.risk_level,
        status=row.status,
        created_at=row.created_at,
        message=_message_out(row.message, target_title, translation_target) if include_message and row.message else None,
    )


@router.get("/hits", response_model=list[RuleHitOut])
def list_hits(
    status: str = "",
    rule_id: int | None = None,
    min_risk_level: int = 0,
    keyword: str = "",
    limit: int = Query(default=100, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RuleHitOut]:
    query = _hit_query(db, status, rule_id, min_risk_level, keyword)
    rows = query.order_by(desc(RuleHit.created_at)).offset(offset).limit(limit).all()
    target_titles = _target_titles(db, [row.message for row in rows if row.message])
    translation_target = effective_translation_target(get_intelligence_settings(db))
    return [_hit_out(row, target_titles.get(row.message.target_id if row.message else None, ""), translation_target) for row in rows]


@router.get("/hits/count")
def count_hits(
    status: str = "",
    rule_id: int | None = None,
    min_risk_level: int = 0,
    keyword: str = "",
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    query = _hit_query(db, status, rule_id, min_risk_level, keyword)
    return {"total": query.count()}


@router.patch("/hits/{hit_id}", response_model=RuleHitOut)
def patch_hit(
    hit_id: int,
    payload: RuleHitPatch,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleHitOut:
    allowed = {"open", "confirmed", "ignored", "archived", "notified", "muted"}
    if payload.status not in allowed:
        raise HTTPException(status_code=400, detail=f"unsupported hit status: {payload.status}")
    row = db.get(RuleHit, hit_id)
    if not row:
        raise HTTPException(status_code=404, detail="hit not found")
    row.status = payload.status
    db.commit()
    db.refresh(row)
    target_title = ""
    if row.message and row.message.target_id:
        target = db.get(TelegramTarget, row.message.target_id)
        target_title = target.title if target else ""
    translation_target = effective_translation_target(get_intelligence_settings(db))
    return _hit_out(row, target_title, translation_target)


@router.post("/hits/{hit_id}/notify", response_model=RuleHitOut)
def notify_hit(
    hit_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleHitOut:
    row = db.get(RuleHit, hit_id)
    if not row:
        raise HTTPException(status_code=404, detail="hit not found")
    if not row.message:
        raise HTTPException(status_code=404, detail="message not found")
    dispatch_for_message(db, row.message)
    row.status = "notified"
    db.commit()
    db.refresh(row)
    target_title = ""
    if row.message and row.message.target_id:
        target = db.get(TelegramTarget, row.message.target_id)
        target_title = target.title if target else ""
    translation_target = effective_translation_target(get_intelligence_settings(db))
    return _hit_out(row, target_title, translation_target)
