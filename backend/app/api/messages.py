from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import desc, or_
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import RuleHit, TelegramMessage, User
from app.schemas import MessageOut, RuleHitOut
from app.services.json_utils import loads_list


router = APIRouter(tags=["messages"])


def _message_out(row: TelegramMessage) -> MessageOut:
    return MessageOut(
        id=row.id,
        message_uid=row.message_uid,
        channel=row.channel,
        account_id=row.account_id,
        target_id=row.target_id,
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
        content_md5=row.content_md5,
        data_id=row.data_id,
        similar_id=row.similar_id,
        original_content=row.original_content,
        category=row.category,
        message_kind=row.message_kind,
        media_type=row.media_type,
        media_count=row.media_count,
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
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MessageOut]:
    query = _message_query(db, keyword, source, sender, target_id, has_links, has_media, date_from, date_to, min_risk_level)
    rows = query.order_by(desc(TelegramMessage.event_time)).limit(limit).all()
    return [_message_out(row) for row in rows]


@router.get("/messages/export")
def export_messages(
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
    rows = query.order_by(desc(TelegramMessage.event_time)).limit(limit).all()
    payload = [_message_out(row).model_dump(mode="json") for row in rows]
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
                TelegramMessage.source.like(like),
                TelegramMessage.sender_username.like(like),
                TelegramMessage.sender_name.like(like),
                TelegramMessage.links_json.like(like),
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


@router.get("/hits", response_model=list[RuleHitOut])
def list_hits(
    status: str = "",
    limit: int = Query(default=100, le=500),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RuleHitOut]:
    query = db.query(RuleHit)
    if status:
        query = query.filter(RuleHit.status == status)
    rows = query.order_by(desc(RuleHit.created_at)).limit(limit).all()
    return [
        RuleHitOut(
            id=row.id,
            message_id=row.message_id,
            rule_id=row.rule_id,
            rule_name=row.rule_name,
            matched_patterns=[str(item) for item in loads_list(row.matched_patterns_json)],
            risk_level=row.risk_level,
            status=row.status,
            created_at=row.created_at,
        )
        for row in rows
    ]
