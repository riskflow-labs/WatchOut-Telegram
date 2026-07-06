from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import MonitorRuleNotificationChannel, NotificationChannel, NotificationDelivery, RuleHit, TelegramMessage
from app.notifications.telegram_bot import send_telegram_bot
from app.notifications.webhook import send_dingtalk, send_feishu, send_webhook, send_wecom


def dispatch_for_message(db: Session, message: TelegramMessage) -> None:
    channels = _channels_for_message(db, message)
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
            elif channel.type == "wecom":
                send_wecom(channel, message)
            elif channel.type == "dingtalk":
                send_dingtalk(channel, message)
            else:
                raise RuntimeError(f"unsupported notification channel type: {channel.type}")
            delivery.status = "delivered"
            delivery.delivered_at = datetime.now(timezone.utc)
        except Exception as exc:
            delivery.status = "failed"
            delivery.error = str(exc)
            delivery.attempts += 1


def _channels_for_message(db: Session, message: TelegramMessage) -> list[NotificationChannel]:
    db.flush()
    rule_ids = [
        rule_id
        for (rule_id,) in db.query(RuleHit.rule_id)
        .filter(RuleHit.message_id == message.id, RuleHit.rule_id.isnot(None), RuleHit.status == "open")
        .all()
        if rule_id
    ]
    bound_channel_ids: list[int] = []
    if rule_ids:
        rows = (
            db.query(MonitorRuleNotificationChannel.channel_id)
            .filter(MonitorRuleNotificationChannel.rule_id.in_(rule_ids))
            .all()
        )
        bound_channel_ids = sorted({channel_id for (channel_id,) in rows})
    query = (
        db.query(NotificationChannel)
        .filter(NotificationChannel.enabled == True)  # noqa: E712
        .filter(NotificationChannel.min_risk_level <= message.risk_level)
    )
    if bound_channel_ids:
        query = query.filter(NotificationChannel.id.in_(bound_channel_ids))
    return query.all()
