from __future__ import annotations

import json
import urllib.request

from app.models import NotificationChannel, TelegramMessage
from app.services.json_utils import loads_dict, loads_list


def message_payload(message: TelegramMessage) -> dict[str, object]:
    return {
        "id": message.id,
        "source": message.source,
        "source_id": message.source_id,
        "message_id": message.message_id,
        "event_time": message.event_time.isoformat(),
        "sender_id": message.sender_id,
        "sender_username": message.sender_username,
        "sender_name": message.sender_name,
        "content": message.content,
        "links": loads_list(message.links_json),
        "risk_level": message.risk_level,
        "score": message.score,
    }


def send_webhook(channel: NotificationChannel, message: TelegramMessage) -> None:
    config = loads_dict(channel.config_json)
    url = str(config.get("url") or "")
    if not url:
        raise RuntimeError("Webhook notification requires url")
    request = urllib.request.Request(
        url,
        data=json.dumps(message_payload(message), ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def send_feishu(channel: NotificationChannel, message: TelegramMessage) -> None:
    config = loads_dict(channel.config_json)
    url = str(config.get("webhook_url") or config.get("url") or "")
    if not url:
        raise RuntimeError("Feishu notification requires webhook_url")
    text = "\n".join(
        [
            f"WatchOut Telegram L{message.risk_level} {message.source}",
            f"From: {message.sender_username or message.sender_name or message.sender_id or '-'}",
            f"Time: {message.event_time.isoformat()}",
            "",
            (message.content or "")[:1200],
        ]
    )
    body = {"msg_type": "text", "content": {"text": text}}
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()
