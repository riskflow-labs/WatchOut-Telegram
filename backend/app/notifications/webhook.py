from __future__ import annotations

import json
import hashlib
import hmac
import base64
import urllib.parse
import time
import urllib.request

from app.models import NotificationChannel, TelegramMessage
from app.notifications.message_format import (
    content_excerpt,
    local_time_text,
    markdown_notification_text,
    message_link,
    rule_text,
    sender_text,
    source_link,
)
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
        "rule": rule_text(message),
        "message_link": message_link(message),
        "summary": content_excerpt(message, 500),
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
    _open_json_request(request)


def send_feishu(channel: NotificationChannel, message: TelegramMessage) -> None:
    config = loads_dict(channel.config_json)
    url = str(config.get("webhook_url") or config.get("url") or "")
    if not url:
        raise RuntimeError("Feishu notification requires webhook_url")
    body = _feishu_card_body(message)
    result = _post_json(url, body)
    code = result.get("code")
    if code not in (None, 0):
        raise RuntimeError(f"Feishu rejected notification: code={code}, msg={result.get('msg') or result.get('message') or result}")


def send_wecom(channel: NotificationChannel, message: TelegramMessage) -> None:
    config = loads_dict(channel.config_json)
    url = str(config.get("webhook_url") or config.get("url") or "")
    if not url:
        raise RuntimeError("WeCom notification requires webhook_url")
    text = _markdown_text(message)
    result = _post_json(url, {"msgtype": "markdown", "markdown": {"content": text}})
    code = result.get("errcode")
    if code not in (None, 0):
        raise RuntimeError(f"WeCom rejected notification: errcode={code}, errmsg={result.get('errmsg') or result}")


def send_dingtalk(channel: NotificationChannel, message: TelegramMessage) -> None:
    config = loads_dict(channel.config_json)
    url = _dingtalk_url(config)
    if not url:
        raise RuntimeError("DingTalk notification requires webhook_url or access_token")
    result = _post_json(url, _dingtalk_body(message))
    code = result.get("errcode")
    if code not in (None, 0):
        raise RuntimeError(f"DingTalk rejected notification: errcode={code}, errmsg={result.get('errmsg') or result}")


def _dingtalk_url(config: dict[str, object]) -> str:
    raw_url = str(config.get("webhook_url") or config.get("url") or "").strip()
    access_token = str(config.get("access_token") or "").strip()
    secret = str(config.get("secret") or config.get("sign") or config.get("secret_key") or "").strip()
    if raw_url:
        if "access_token=" in raw_url:
            url = raw_url
        elif access_token:
            url = f"https://oapi.dingtalk.com/robot/send?access_token={urllib.parse.quote(access_token)}"
        else:
            return raw_url
    elif access_token:
        url = f"https://oapi.dingtalk.com/robot/send?access_token={urllib.parse.quote(access_token)}"
    else:
        return ""
    if not secret:
        return url
    url = _without_query_params(url, {"timestamp", "sign"})
    timestamp = str(round(time.time() * 1000))
    string_to_sign = f"{timestamp}\n{secret}"
    signature = urllib.parse.quote_plus(
        base64.b64encode(hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha256).digest())
        .decode("utf-8")
    )
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}timestamp={timestamp}&sign={signature}"


def _without_query_params(url: str, names: set[str]) -> str:
    parts = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parts.query, keep_blank_values=True)
    filtered = [(key, value) for key, value in query if key not in names]
    return urllib.parse.urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urllib.parse.urlencode(filtered),
            parts.fragment,
        )
    )


def _markdown_text(message: TelegramMessage) -> str:
    return markdown_notification_text(message)


def _dingtalk_body(message: TelegramMessage) -> dict[str, object]:
    title = f"WatchOut 测试通知 L{message.risk_level} · 测试规则" if message.status == "test" else f"WatchOut 线索 L{message.risk_level} · {rule_text(message)}"
    return {
        "msgtype": "markdown",
        "markdown": {
            "title": title,
            "text": _dingtalk_markdown_text(message),
        },
    }


def _dingtalk_markdown_text(message: TelegramMessage) -> str:
    if message.status == "test":
        rows = [
            ("状态", "测试成功"),
            ("等级", f"L{message.risk_level} · 分数 0"),
            ("来源", "测试来源"),
            ("源 ID", "0"),
            ("发送人", "watchout"),
            ("时间", local_time_text(message)),
            ("目标类型", "text"),
            ("消息 ID", "test"),
            ("命中规则", "测试规则"),
            ("互动", "浏览 0 ｜ 回复 0 ｜ 转发 0"),
        ]
        summary = "这是一条推送渠道连通性测试消息，不包含真实业务数据。"
        return _dingtalk_template_text(f"WatchOut 测试通知 L{message.risk_level} · 测试规则", rows, summary)

    rows = [
        ("状态", "新线索"),
        ("等级", f"L{message.risk_level} · 分数 {message.score or 0}"),
        ("来源", message.source or "-"),
        ("源 ID", message.source_id or "-"),
        ("发送人", sender_text(message)),
        ("时间", local_time_text(message)),
        ("目标类型", message.source_type or message.message_kind or "-"),
        ("消息 ID", message.message_id or "-"),
        ("命中规则", rule_text(message)),
        ("互动", f"浏览 {message.views_count or 0} ｜ 回复 {message.replies_count or 0} ｜ 转发 {message.forwards_count or 0}"),
    ]
    links = []
    link = message_link(message)
    src_link = source_link(message)
    if link:
        links.append(f"[打开原消息]({link})")
    if src_link:
        links.append(f"[打开源频道]({src_link})")
    summary = content_excerpt(message, 1800)
    if links:
        summary = f"{summary}\n\n{' ｜ '.join(links)}"
    return _dingtalk_template_text(f"WatchOut 线索 L{message.risk_level} · {rule_text(message)}", rows, summary)


def _dingtalk_template_text(title: str, rows: list[tuple[str, str]], summary: str) -> str:
    field_lines = [f"- **{label}**：{_escape_dingtalk_markdown(value)}" for label, value in rows]
    return "\n".join(
        [
            f"### {title}",
            "",
            *field_lines,
            "",
            "---",
            "",
            "**消息摘要**",
            "",
            _escape_dingtalk_markdown(summary),
        ]
    )


def _escape_dingtalk_markdown(value: object) -> str:
    return str(value or "-").replace("\r", " ").strip()


def _feishu_card_body(message: TelegramMessage) -> dict[str, object]:
    if message.status == "test":
        return _feishu_test_card_body(message)
    link = message_link(message)
    src_link = source_link(message)
    elements: list[dict[str, object]] = [
        {
            "tag": "div",
            "fields": [
                _feishu_field("状态", "新线索"),
                _feishu_field("等级", f"L{message.risk_level} · 分数 {message.score or 0}"),
                _feishu_field("来源", message.source or "-"),
                _feishu_field("源 ID", message.source_id or "-"),
                _feishu_field("发送人", sender_text(message)),
                _feishu_field("时间", local_time_text(message)),
                _feishu_field("目标类型", message.source_type or message.message_kind or "-"),
                _feishu_field("消息 ID", message.message_id or "-"),
                _feishu_field("命中规则", rule_text(message)),
                _feishu_field("互动", f"浏览 {message.views_count or 0} ｜ 回复 {message.replies_count or 0} ｜ 转发 {message.forwards_count or 0}"),
            ],
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"**消息摘要**\n{_escape_card_markdown(content_excerpt(message, 1800))}",
        },
    ]
    actions = []
    if link:
        actions.append(_feishu_button("打开原消息", link, "primary"))
    if src_link:
        actions.append(_feishu_button("打开源频道", src_link, "default"))
    if actions:
        elements.append({"tag": "action", "actions": actions})
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": _feishu_card_color(message.risk_level),
                "title": {"tag": "plain_text", "content": f"WatchOut 线索 L{message.risk_level} · {rule_text(message)}"},
            },
            "elements": elements,
        },
    }


def _feishu_test_card_body(message: TelegramMessage) -> dict[str, object]:
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "green",
                "title": {"tag": "plain_text", "content": f"WatchOut 测试通知 L{message.risk_level} · 测试规则"},
            },
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        _feishu_field("状态", "测试成功"),
                        _feishu_field("等级", f"L{message.risk_level} · 分数 0"),
                        _feishu_field("来源", "测试来源"),
                        _feishu_field("源 ID", "0"),
                        _feishu_field("发送人", "watchout"),
                        _feishu_field("时间", local_time_text(message)),
                        _feishu_field("目标类型", "text"),
                        _feishu_field("消息 ID", "test"),
                        _feishu_field("命中规则", "测试规则"),
                        _feishu_field("互动", "浏览 0 ｜ 回复 0 ｜ 转发 0"),
                    ],
                },
                {"tag": "hr"},
                {"tag": "markdown", "content": "**消息摘要**\n这是一条推送渠道连通性测试消息，不包含真实业务数据。"},
            ],
        },
    }


def _feishu_field(label: str, value: str) -> dict[str, object]:
    return {"is_short": True, "text": {"tag": "lark_md", "content": f"**{label}**\n{_escape_card_markdown(value)}"}}


def _feishu_button(text: str, url: str, button_type: str) -> dict[str, object]:
    return {
        "tag": "button",
        "text": {"tag": "plain_text", "content": text},
        "type": button_type,
        "url": url,
    }


def _feishu_card_color(risk_level: int) -> str:
    if risk_level >= 3:
        return "red"
    if risk_level == 2:
        return "orange"
    return "turquoise"


def _escape_card_markdown(value: object) -> str:
    text = str(value or "-").replace("\r", " ").strip()
    return text.replace("<", "\\<").replace(">", "\\>")


def _post_json(url: str, body: dict[str, object]) -> dict[str, object]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    return _open_json_request(request)


def _open_json_request(request: urllib.request.Request) -> dict[str, object]:
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read()
    if not raw:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
