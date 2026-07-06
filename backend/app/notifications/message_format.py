from __future__ import annotations

import re
from zoneinfo import ZoneInfo
from html import escape

from app.models import TelegramMessage


DISPLAY_TIMEZONE = ZoneInfo("Asia/Shanghai")


def message_link(message: TelegramMessage) -> str:
    source = (message.source or "").strip().removeprefix("@")
    if not source or source.lstrip("-").isdigit() or not message.message_id:
        return ""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", source):
        return ""
    return f"https://t.me/{source}/{message.message_id}"


def source_link(message: TelegramMessage) -> str:
    source = (message.source or "").strip().removeprefix("@")
    if not source or source.lstrip("-").isdigit():
        return ""
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", source):
        return ""
    return f"https://t.me/{source}"


def sender_text(message: TelegramMessage) -> str:
    return message.sender_username or message.sender_name or message.sender_id or "-"


def local_time_text(message: TelegramMessage) -> str:
    return message.event_time.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S CST")


def content_excerpt(message: TelegramMessage, limit: int = 1200) -> str:
    text = message.content or message.translated_content or message.ocr_text or "这是一条 WatchOut Telegram 通知测试消息。"
    text = _normalize_message_text(str(text))
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}\n\n... 已截断，完整内容请查看原消息或系统详情。"


def _normalize_message_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    compacted: list[str] = []
    blank_seen = False
    for line in lines:
        if not line.strip():
            if not blank_seen and compacted:
                compacted.append("")
            blank_seen = True
            continue
        compacted.append(line)
        blank_seen = False
    return "\n".join(compacted).strip()


def rule_text(message: TelegramMessage) -> str:
    return message.keyword_source or "未关联规则"


def plain_notification_text(message: TelegramMessage) -> str:
    if message.status == "test":
        return "\n".join(
            [
                f"WatchOut 测试通知 L{message.risk_level} · 测试规则",
                "状态：测试成功",
                f"等级：L{message.risk_level} · 分数 0",
                "来源：测试来源",
                "源 ID：0",
                "发送人：watchout",
                f"时间：{local_time_text(message)}",
                "目标类型：text",
                "消息 ID：test",
                "命中规则：测试规则",
                "互动：浏览 0 ｜ 回复 0 ｜ 转发 0",
                "",
                "消息摘要：这是一条推送渠道连通性测试消息，不包含真实业务数据。",
            ]
        )
    link = message_link(message)
    parts = [
        f"【WatchOut 线索 L{message.risk_level}】{rule_text(message)}",
        f"来源：{message.source or '-'}",
        f"发送人：{sender_text(message)}",
        f"时间：{local_time_text(message)}",
        f"命中规则：{rule_text(message)}",
    ]
    if link:
        parts.append(f"原消息：{link}")
    parts.extend(["", "消息摘要：", content_excerpt(message, 1200)])
    return "\n".join(parts)


def markdown_notification_text(message: TelegramMessage) -> str:
    if message.status == "test":
        return "\n".join(
            [
                f"### WatchOut 测试通知 L{message.risk_level} · 测试规则",
                "- 状态：测试成功",
                f"- 等级：L{message.risk_level} · 分数 0",
                "- 来源：测试来源",
                "- 源 ID：0",
                "- 发送人：watchout",
                f"- 时间：{local_time_text(message)}",
                "- 目标类型：text",
                "- 消息 ID：test",
                "- 命中规则：测试规则",
                "- 互动：浏览 0 ｜ 回复 0 ｜ 转发 0",
                "",
                "消息摘要：这是一条推送渠道连通性测试消息，不包含真实业务数据。",
            ]
        )
    link = message_link(message)
    parts = [
        f"### WatchOut 线索 L{message.risk_level}",
        f"- 来源：{message.source or '-'}",
        f"- 发送人：{sender_text(message)}",
        f"- 时间：{local_time_text(message)}",
        f"- 命中规则：{rule_text(message)}",
    ]
    if link:
        parts.append(f"- 原消息：[打开链接]({link})")
    parts.extend(["", "**消息摘要**", content_excerpt(message, 1600)])
    return "\n".join(parts)


def html_notification_text(message: TelegramMessage) -> str:
    if message.status == "test":
        return "\n".join(
            [
                f"<b>WatchOut 测试通知 L{message.risk_level} · 测试规则</b>",
                "",
                "<b>状态</b>：测试成功",
                f"<b>等级</b>：L{message.risk_level} · 分数 0",
                "<b>来源</b>：测试来源",
                "<b>源 ID</b>：0",
                "<b>发送人</b>：watchout",
                f"<b>时间</b>：{escape(local_time_text(message))}",
                "<b>目标类型</b>：text",
                "<b>消息 ID</b>：test",
                "<b>命中规则</b>：测试规则",
                "<b>互动</b>：浏览 0 ｜ 回复 0 ｜ 转发 0",
                "",
                "<b>消息摘要</b>",
                escape("这是一条推送渠道连通性测试消息，不包含真实业务数据。"),
            ]
        )
    link = message_link(message)
    parts = [
        f"<b>WatchOut 线索 L{message.risk_level} · {escape(rule_text(message))}</b>",
        "",
        f"<b>来源</b>：{escape(message.source or '-')}",
        f"<b>发送人</b>：{escape(sender_text(message))}",
        f"<b>时间</b>：{escape(local_time_text(message))}",
        f"<b>等级</b>：L{message.risk_level}",
        f"<b>命中规则</b>：{escape(rule_text(message))}",
    ]
    if link:
        parts.append(f'<b>原消息</b>：<a href="{escape(link)}">打开链接</a>')
    summary = escape(content_excerpt(message, 2200))
    parts.extend(["", "<b>消息摘要</b>", f"<blockquote>{summary}</blockquote>"])
    return "\n".join(parts)
