from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import NotificationChannel, NotificationDelivery, TelegramMessage, User
from app.notifications.telegram_bot import send_telegram_bot
from app.notifications.webhook import send_feishu, send_webhook
from app.schemas import NotificationChannelCreate, NotificationChannelOut
from app.services.json_utils import dumps, loads_dict


router = APIRouter(prefix="/notifications", tags=["notifications"])


def _out(channel: NotificationChannel) -> NotificationChannelOut:
    return NotificationChannelOut(
        id=channel.id,
        name=channel.name,
        type=channel.type,
        enabled=channel.enabled,
        min_risk_level=channel.min_risk_level,
        config=loads_dict(channel.config_json),
        created_at=channel.created_at,
        updated_at=channel.updated_at,
    )


@router.get("", response_model=list[NotificationChannelOut])
def list_channels(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[NotificationChannelOut]:
    return [_out(row) for row in db.query(NotificationChannel).order_by(NotificationChannel.id.desc()).all()]


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


@router.post("/{channel_id}/test")
def test_channel(
    channel_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    channel = db.get(NotificationChannel, channel_id)
    if not channel:
        return {"status": "failed", "message": "notification channel not found"}
    sample = TelegramMessage(
        id=0,
        source="watchout-test",
        source_id="0",
        message_id="test",
        event_time=datetime.now(timezone.utc),
        sender_id="system",
        sender_username="watchout",
        sender_name="WatchOut Telegram",
        content="这是一条 WatchOut Telegram 通知测试消息。",
        message_kind="text",
        media_type="",
        links_json="[]",
        risk_level=channel.min_risk_level,
        score=0,
        status="test",
    )
    try:
        if channel.type == "telegram_bot":
            send_telegram_bot(channel, sample)
        elif channel.type == "webhook":
            send_webhook(channel, sample)
        elif channel.type == "feishu":
            send_feishu(channel, sample)
        else:
            raise NotImplementedError(f"{channel.type} test is not implemented")
    except Exception as exc:
        return {"status": "failed", "message": str(exc)}
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
