from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.models import AppSetting, TelegramMessage
from app.services.json_utils import loads_dict, loads_list


@dataclass(frozen=True)
class SinkStatus:
    name: str
    enabled: bool
    status: str
    note: str


def sink_statuses() -> list[SinkStatus]:
    return [
        SinkStatus("sqlite", True, "active", "默认主存储，保存配置、消息、规则匹配和运行状态"),
        SinkStatus("jsonl", False, "optional", "可选本地原始导出 Sink"),
        SinkStatus("clickhouse", False, "optional", "可选大体量消息分析 Sink"),
        SinkStatus("elasticsearch", False, "optional", "可选全文检索 Sink"),
    ]


DEFAULT_SINK_CONFIG = {
    "jsonl": {"enabled": False, "path": "./data/messages.jsonl"},
    "clickhouse": {
        "enabled": False,
        "url": "http://localhost:8123",
        "database": "watchout_telegram",
        "table": "telegram_messages",
        "user": "default",
        "password": "",
    },
    "elasticsearch": {
        "enabled": False,
        "url": "http://localhost:9200",
        "index": "watchout-telegram-messages",
        "username": "",
        "password": "",
    },
}


def get_sink_config(db) -> dict[str, Any]:
    row = db.get(AppSetting, "storage_sinks_config")
    if not row:
        return DEFAULT_SINK_CONFIG
    config = loads_dict(row.value)
    merged = json.loads(json.dumps(DEFAULT_SINK_CONFIG))
    for key, value in config.items():
        if isinstance(value, dict) and key in merged:
            merged[key].update(value)
    return merged


def set_sink_config(db, config: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_SINK_CONFIG))
    for key, value in config.items():
        if isinstance(value, dict) and key in merged:
            merged[key].update(value)
    row = db.get(AppSetting, "storage_sinks_config")
    if row:
        row.value = json.dumps(merged, ensure_ascii=False)
    else:
        db.add(AppSetting(key="storage_sinks_config", value=json.dumps(merged, ensure_ascii=False)))
    db.commit()
    return merged


def export_message(db, message: TelegramMessage) -> None:
    config = get_sink_config(db)
    payload = _message_payload(message)
    if config["jsonl"].get("enabled"):
        _write_jsonl(config["jsonl"], payload)
    if config["clickhouse"].get("enabled"):
        _write_clickhouse(config["clickhouse"], payload)
    if config["elasticsearch"].get("enabled"):
        _write_elasticsearch(config["elasticsearch"], payload)


def _message_payload(message: TelegramMessage) -> dict[str, Any]:
    return {
        "id": message.message_uid,
        "local_id": message.id,
        "message_uid": message.message_uid,
        "channel": message.channel,
        "account_id": message.account_id,
        "target_id": message.target_id,
        "source": message.source,
        "source_id": message.source_id,
        "source_type": message.source_type,
        "sub_channel": message.sub_channel,
        "message_id": message.message_id,
        "event_time": message.event_time.isoformat(),
        "insert_time": message.insert_time.isoformat(),
        "sender_id": message.sender_id,
        "sender_username": message.sender_username,
        "sender_name": message.sender_name,
        "content": message.content,
        "content_md5": message.content_md5,
        "data_id": message.data_id,
        "similar_id": message.similar_id,
        "original_content": message.original_content,
        "category": message.category,
        "message_kind": message.message_kind,
        "media_type": message.media_type,
        "media_count": message.media_count,
        "links": loads_list(message.links_json),
        "views_count": message.views_count,
        "replies_count": message.replies_count,
        "forwards_count": message.forwards_count,
        "risk_level": message.risk_level,
        "score": message.score,
        "hit": message.hit,
        "keyword_type": message.keyword_type,
        "keyword_source": message.keyword_source,
        "status": message.status,
        "raw_payload": message.raw_payload,
    }


def _write_jsonl(config: dict[str, Any], payload: dict[str, Any]) -> None:
    path = Path(str(config.get("path") or "./data/messages.jsonl"))
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _write_clickhouse(config: dict[str, Any], payload: dict[str, Any]) -> None:
    columns = [
        "id",
        "message_uid",
        "channel",
        "source",
        "source_id",
        "source_type",
        "sub_channel",
        "message_id",
        "event_time",
        "insert_time",
        "sender_id",
        "sender_username",
        "sender_name",
        "content",
        "content_md5",
        "data_id",
        "similar_id",
        "message_kind",
        "media_type",
        "media_count",
        "links",
        "views_count",
        "replies_count",
        "forwards_count",
        "risk_level",
        "score",
        "hit",
        "status",
    ]
    row = {column: payload.get(column) for column in columns}
    query = (
        f"INSERT INTO {config.get('database')}.{config.get('table')} "
        f"({', '.join(columns)}) FORMAT JSONEachRow"
    )
    endpoint = str(config.get("url", "")).rstrip("/") + "/?" + urllib.parse.urlencode(
        {
            "user": config.get("user", "default"),
            "password": config.get("password", ""),
            "query": query,
        }
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(row, ensure_ascii=False).encode("utf-8"),
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def _write_elasticsearch(config: dict[str, Any], payload: dict[str, Any]) -> None:
    url = f"{str(config.get('url', '')).rstrip('/')}/{config.get('index')}/_doc/{payload['id']}"
    request = urllib.request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="PUT",
    )
    username = str(config.get("username") or "")
    password = str(config.get("password") or "")
    if username or password:
        import base64

        token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
        request.add_header("Authorization", f"Basic {token}")
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()
