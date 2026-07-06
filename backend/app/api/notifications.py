from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import case, desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import MonitorRuleNotificationChannel, NotificationChannel, NotificationDelivery, TelegramMessage, User
from app.notifications.message_format import content_excerpt, plain_notification_text
from app.notifications.telegram_bot import send_telegram_bot
from app.notifications.webhook import send_dingtalk, send_feishu, send_webhook, send_wecom
from app.schemas import NotificationChannelCreate, NotificationChannelOut, NotificationDeliveryOut, NotificationDeliveryPageOut, NotificationPreviewOut
from app.services.json_utils import dumps, loads_dict


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(
    channel: NotificationChannel,
    delivery_count: int = 0,
    delivered_count: int = 0,
    failed_count: int = 0,
    last_delivery_status: str = "",
    last_delivery_at=None,
) -> NotificationChannelOut:
    return NotificationChannelOut(
        id=channel.id,
        name=channel.name,
        type=channel.type,
        enabled=channel.enabled,
        min_risk_level=channel.min_risk_level,
        config=loads_dict(channel.config_json),
        created_at=channel.created_at,
        updated_at=channel.updated_at,
        delivery_count=delivery_count,
        delivered_count=delivered_count,
        failed_count=failed_count,
        last_delivery_status=last_delivery_status,
        last_delivery_at=last_delivery_at,
    )


def _delivery_out(
    delivery: NotificationDelivery,
    channel: NotificationChannel | None = None,
    message: TelegramMessage | None = None,
) -> NotificationDeliveryOut:
    return NotificationDeliveryOut(
        id=delivery.id,
        channel_id=delivery.channel_id,
        channel_name=channel.name if channel else "",
        channel_type=channel.type if channel else "",
        message_id=delivery.message_id,
        message_source=message.source if message else "",
        message_source_id=message.source_id if message else "",
        message_tg_id=message.message_id if message else "",
        message_event_time=message.event_time if message else None,
        message_rule=message.keyword_source if message else "",
        message_risk_level=message.risk_level if message else 0,
        message_summary=content_excerpt(message, 260) if message else "",
        status=delivery.status,
        attempts=delivery.attempts,
        error=delivery.error,
        created_at=delivery.created_at,
        delivered_at=delivery.delivered_at,
    )


def _sample_notification_message(risk_level: int = 3) -> TelegramMessage:
    return TelegramMessage(
        id=0,
        source="测试来源",
        source_id="0",
        message_id="test",
        event_time=datetime.now(timezone.utc),
        sender_id="system",
        sender_username="watchout",
        sender_name="WatchOut Telegram",
        content="这是一条推送渠道连通性测试消息，不包含真实业务数据。",
        message_kind="text",
        media_type="",
        links_json="[]",
        risk_level=risk_level,
        score=0,
        hit=0,
        keyword_type="test",
        keyword_source="测试规则",
        status="test",
    )


@router.get("", response_model=list[NotificationChannelOut])
def list_channels(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationChannelOut]:
    rows = db.query(NotificationChannel).order_by(NotificationChannel.id.desc()).all()
    channel_ids = [row.id for row in rows]
    stat_map: dict[int, dict[str, object]] = {}
    if channel_ids:
        totals = (
            db.query(
                NotificationDelivery.channel_id,
                func.count(NotificationDelivery.id),
                func.sum(case((NotificationDelivery.status == "delivered", 1), else_=0)),
                func.sum(case((NotificationDelivery.status == "failed", 1), else_=0)),
            )
            .filter(NotificationDelivery.channel_id.in_(channel_ids))
            .group_by(NotificationDelivery.channel_id)
            .all()
        )
        for channel_id, total, delivered, failed in totals:
            stat_map[channel_id] = {
                "delivery_count": int(total or 0),
                "delivered_count": int(delivered or 0),
                "failed_count": int(failed or 0),
            }
        latest = (
            db.query(NotificationDelivery)
            .filter(NotificationDelivery.channel_id.in_(channel_ids))
            .order_by(desc(NotificationDelivery.created_at))
            .all()
        )
        seen: set[int] = set()
        for delivery in latest:
            if not delivery.channel_id or delivery.channel_id in seen:
                continue
            seen.add(delivery.channel_id)
            stat_map.setdefault(delivery.channel_id, {})
            stat_map[delivery.channel_id]["last_delivery_status"] = delivery.status
            stat_map[delivery.channel_id]["last_delivery_at"] = delivery.created_at
    return [_out(row, **stat_map.get(row.id, {})) for row in rows]


@router.get("/deliveries", response_model=NotificationDeliveryPageOut)
def list_deliveries(
    message_id: int | None = None,
    channel_id: int | None = None,
    status: str = "",
    sort: str = "created_at",
    direction: str = "desc",
    page: int = 1,
    page_size: int = 50,
    limit: int = 50,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationDeliveryPageOut:
    query = db.query(NotificationDelivery)
    if message_id:
        query = query.filter(NotificationDelivery.message_id == message_id)
    if channel_id:
        query = query.filter(NotificationDelivery.channel_id == channel_id)
    if status:
        query = query.filter(NotificationDelivery.status == status)
    total = query.count()
    page_size = min(max(int(page_size or limit or 50), 1), 200)
    page = max(int(page or 1), 1)
    sort_columns = {
        "id": NotificationDelivery.id,
        "channel": NotificationDelivery.channel_id,
        "status": NotificationDelivery.status,
        "message": NotificationDelivery.message_id,
        "attempts": NotificationDelivery.attempts,
        "created_at": NotificationDelivery.created_at,
        "delivered_at": NotificationDelivery.delivered_at,
    }
    sort_column = sort_columns.get(sort, NotificationDelivery.created_at)
    order_expr = sort_column.asc() if direction == "asc" else sort_column.desc()
    rows = query.order_by(order_expr, NotificationDelivery.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    channel_ids = sorted({row.channel_id for row in rows if row.channel_id})
    message_ids = sorted({row.message_id for row in rows if row.message_id})
    channels = {}
    if channel_ids:
        channels = {channel.id: channel for channel in db.query(NotificationChannel).filter(NotificationChannel.id.in_(channel_ids)).all()}
    messages = {}
    if message_ids:
        messages = {message.id: message for message in db.query(TelegramMessage).filter(TelegramMessage.id.in_(message_ids)).all()}
    return NotificationDeliveryPageOut(
        items=[_delivery_out(row, channels.get(row.channel_id), messages.get(row.message_id)) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/preview", response_model=NotificationPreviewOut)
def preview_notification(
    risk_level: int = 3,
    _user: User = Depends(get_current_user),
) -> NotificationPreviewOut:
    message = _sample_notification_message(risk_level)
    return NotificationPreviewOut(
        title="WatchOut 推送测试",
        text=plain_notification_text(message),
        risk_level=message.risk_level,
        rule_name=message.keyword_source,
    )


@router.post("", response_model=NotificationChannelOut)
def create_channel(
    payload: NotificationChannelCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationChannelOut:
    channel = NotificationChannel(
        name=payload.name,
        type=payload.type,
        enabled=payload.enabled,
        min_risk_level=payload.min_risk_level,
        config_json=dumps(payload.config),
    )
    db.add(channel)
    db.commit()
    db.refresh(channel)
    return _out(channel)


@router.patch("/{channel_id}", response_model=NotificationChannelOut)
def patch_channel(
    channel_id: int,
    payload: NotificationChannelCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationChannelOut:
    channel = db.get(NotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="notification channel not found")
    channel.name = payload.name
    channel.type = payload.type
    channel.enabled = payload.enabled
    channel.min_risk_level = payload.min_risk_level
    channel.config_json = dumps(payload.config)
    db.commit()
    db.refresh(channel)
    return _out(channel)


@router.delete("/{channel_id}")
def delete_channel(
    channel_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    channel = db.get(NotificationChannel, channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="notification channel not found")
    db.query(MonitorRuleNotificationChannel).filter(MonitorRuleNotificationChannel.channel_id == channel.id).delete(synchronize_session=False)
    db.query(NotificationDelivery).filter(NotificationDelivery.channel_id == channel.id).update({NotificationDelivery.channel_id: None})
    db.delete(channel)
    db.commit()
    return {"ok": True}


@router.post("/{channel_id}/test")
def test_channel(
    channel_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    channel = db.get(NotificationChannel, channel_id)
    if not channel:
        return {"status": "failed", "message": "notification channel not found"}
    sample = _sample_notification_message(channel.min_risk_level)
    delivery = NotificationDelivery(channel_id=channel.id, message_id=None, status="pending")
    db.add(delivery)
    db.flush()
    try:
        if channel.type == "telegram_bot":
            send_telegram_bot(channel, sample)
        elif channel.type == "webhook":
            send_webhook(channel, sample)
        elif channel.type == "feishu":
            send_feishu(channel, sample)
        elif channel.type == "wecom":
            send_wecom(channel, sample)
        elif channel.type == "dingtalk":
            send_dingtalk(channel, sample)
        else:
            raise NotImplementedError(f"{channel.type} test is not implemented")
    except Exception as exc:
        delivery.status = "failed"
        delivery.error = str(exc)
        delivery.attempts += 1
        db.commit()
        return {"status": "failed", "message": str(exc)}
    delivery.status = "delivered"
    delivery.delivered_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "delivered", "message": "test notification delivered"}


@router.post("/retry-failed")
def retry_failed(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    deliveries = db.query(NotificationDelivery).filter(NotificationDelivery.status == "failed").limit(50).all()
    retried = 0
    delivered = 0
    for delivery in deliveries:
        channel = db.get(NotificationChannel, delivery.channel_id) if delivery.channel_id else None
        message = db.get(TelegramMessage, delivery.message_id) if delivery.message_id else None
        if not channel or not message:
            continue
        retried += 1
        try:
            if channel.type == "telegram_bot":
                send_telegram_bot(channel, message)
            elif channel.type == "webhook":
                send_webhook(channel, message)
            elif channel.type == "feishu":
                send_feishu(channel, message)
            elif channel.type == "wecom":
                send_wecom(channel, message)
            elif channel.type == "dingtalk":
                send_dingtalk(channel, message)
            else:
                raise NotImplementedError(f"{channel.type} retry is not implemented")
            delivery.status = "delivered"
            delivery.error = ""
            delivered += 1
        except Exception as exc:
            delivery.status = "failed"
            delivery.error = str(exc)
            delivery.attempts += 1
    db.commit()
    return {"retried": retried, "delivered": delivered}
