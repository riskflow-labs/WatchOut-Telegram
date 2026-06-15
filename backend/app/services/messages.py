from __future__ import annotations

import hashlib
from datetime import timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models import MonitorRule, RuleHit, TelegramMessage
from app.rules.engine import evaluate_rules
from app.services.json_utils import dumps
from app.telegram.utils import extract_links, raw_payload, sender_name


def upsert_message_from_telethon(
    db: Session,
    *,
    account_id: int | None,
    target_id: int | None,
    message: Any,
    chat: Any,
    sender: Any,
) -> tuple[TelegramMessage, list[RuleHit]]:
    source = getattr(chat, "username", None) or getattr(chat, "title", None) or str(getattr(chat, "id", ""))
    source_id = str(getattr(chat, "id", ""))
    message_id = str(message.id)
    message_uid = _md5(f"tg:{source_id}:{message_id}")
    existing = (
        db.query(TelegramMessage)
        .filter(
            (TelegramMessage.message_uid == message_uid)
            | ((TelegramMessage.source_id == source_id) & (TelegramMessage.message_id == message_id))
        )
        .one_or_none()
    )
    text = message.raw_text or ""
    content_md5 = _md5(text)
    sender_id = str(getattr(sender, "id", "") or "") if sender is not None else ""
    sender_username = getattr(sender, "username", None) or ""
    message_kind, media_type = _message_type(message)
    action_type = type(message.action).__name__ if getattr(message, "action", None) else ""
    views_count = int(getattr(message, "views", 0) or 0)
    forwards_count = int(getattr(message, "forwards", 0) or 0)
    replies = getattr(message, "replies", None)
    replies_count = int(getattr(replies, "replies", 0) or 0) if replies else 0
    payload = {
        "message_uid": message_uid,
        "channel": "tg",
        "account_id": account_id,
        "target_id": target_id,
        "source": source,
        "source_id": source_id,
        "source_type": _source_type(chat),
        "sub_channel": _sub_channel(chat),
        "message_id": message_id,
        "event_time": message.date.astimezone(timezone.utc),
        "sender_id": sender_id,
        "sender_username": sender_username,
        "sender_name": sender_name(sender),
        "content": text,
        "content_md5": content_md5,
        "data_id": content_md5,
        "similar_id": content_md5,
        "original_content": text,
        "category": "开源",
        "message_kind": "service" if action_type else message_kind,
        "media_type": media_type or action_type,
        "media_count": 1 if media_type and media_type != "none" else 0,
        "links_json": dumps(extract_links(text)),
        "raw_payload": raw_payload(message),
        "views_count": views_count,
        "replies_count": replies_count,
        "forwards_count": forwards_count,
    }
    if existing:
        for key, value in payload.items():
            setattr(existing, key, value)
        row = existing
    else:
        row = TelegramMessage(**payload)
        db.add(row)
        db.flush()

    db.query(RuleHit).filter(RuleHit.message_id == row.id).delete()
    rules = db.query(MonitorRule).filter(MonitorRule.enabled == True).all()  # noqa: E712
    matches = evaluate_rules(row, rules)
    hits: list[RuleHit] = []
    if matches:
        row.risk_level = max(match.rule.risk_level for match in matches)
        row.score = min(100, sum(20 + 10 * len(match.matched_patterns) for match in matches))
        row.hit = 1
        row.keyword_type = "rule"
        row.keyword_source = ",".join(match.rule.name for match in matches[:5])
        for match in matches:
            hit = RuleHit(
                message_id=row.id,
                rule_id=match.rule.id,
                rule_name=match.rule.name,
                matched_patterns_json=dumps(match.matched_patterns),
                risk_level=match.rule.risk_level,
                status="open" if match.rule.notify else "muted",
            )
            db.add(hit)
            hits.append(hit)
    else:
        row.risk_level = 0
        row.score = 0
        row.hit = 0
        row.keyword_type = ""
        row.keyword_source = ""

    db.flush()
    return row, hits


def _md5(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def _source_type(chat: Any) -> str:
    if bool(getattr(chat, "broadcast", False)):
        return "channel"
    if bool(getattr(chat, "megagroup", False)) or getattr(chat, "title", None):
        return "group"
    if getattr(chat, "bot", False):
        return "bot"
    if getattr(chat, "first_name", None) or getattr(chat, "last_name", None):
        return "private"
    return "unknown"


def _sub_channel(chat: Any) -> str:
    source_type = _source_type(chat)
    return {
        "channel": "Tg_Channel",
        "group": "Tg_Group",
        "private": "Tg_Private",
        "bot": "Tg_Bot",
    }.get(source_type, "Tg_Unknown")


def _message_type(message: Any) -> tuple[str, str]:
    if getattr(message, "photo", None):
        return "photo", "image"
    if getattr(message, "video", None):
        return "video", "video"
    if getattr(message, "audio", None) or getattr(message, "voice", None):
        return "audio", "audio"
    if getattr(message, "sticker", None):
        return "sticker", "sticker"
    if getattr(message, "poll", None):
        return "poll", "poll"
    if getattr(message, "document", None):
        return "document", "file"
    if getattr(message, "media", None):
        return "media", type(message.media).__name__
    if message.raw_text:
        return "text", "none"
    return "empty", "none"
