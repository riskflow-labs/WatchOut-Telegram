from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import NotificationChannel, NotificationDelivery, TelegramMessage
from app.notifications.telegram_bot import send_telegram_bot
from app.notifications.webhook import send_feishu, send_webhook


def dispatch_for_message(db: Session, message: TelegramMessage) -> None:
    channels = (
        db.query(NotificationChannel)
        .filter(NotificationChannel.enabled == True)  # noqa: E712
        .filter(NotificationChannel.min_risk_level <= message.risk_level)
        .all()
    )
    if not channels:
        return
    for channel in channels:
        delivery = NotificationDelivery(channel_id=channel.id, message_id=message.id, status="pending")
        db.add(delivery)
        db.flush()
        try:
            if channel.type == "telegram_bot":
                send_telegram_bot(channel, message)
            elif channel.type == "webhook":
                send_webhook(channel, message)
            elif channel.type == "feishu":
                send_feishu(channel, message)
            else:
                raise RuntimeError(f"unsupported notification channel type: {channel.type}")
            delivery.status = "delivered"
            delivery.delivered_at = datetime.now(timezone.utc)
        except Exception as exc:
            delivery.status = "failed"
            delivery.error = str(exc)
            delivery.attempts += 1
