from __future__ import annotations

import json
import urllib.parse
import urllib.request

from app.models import NotificationChannel, TelegramMessage
from app.services.json_utils import loads_dict


def send_telegram_bot(channel: NotificationChannel, message: TelegramMessage) -> None:
    config = loads_dict(channel.config_json)
    token = str(config.get("bot_token") or "")
    chat_ids = config.get("chat_ids") or []
    if isinstance(chat_ids, str):
        chat_ids = [chat_ids]
    if not token or not chat_ids:
        raise RuntimeError("Telegram Bot notification requires bot_token and chat_ids")

    text = "\n".join(
        [
            f"[WatchOut Telegram] L{message.risk_level} {message.source}",
            f"From: {message.sender_username or message.sender_name or message.sender_id or '-'}",
            f"Time: {message.event_time.isoformat()}",
            "",
            (message.content or "")[:1200],
        ]
    )
    for chat_id in chat_ids:
        body = urllib.parse.urlencode({"chat_id": str(chat_id), "text": text}).encode("utf-8")
        request = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=body,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
            if not payload.get("ok"):
                raise RuntimeError(f"Telegram Bot sendMessage failed: {payload}")
