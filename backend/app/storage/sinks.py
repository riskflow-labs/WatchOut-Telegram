from __future__ import annotations

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import inspect, text
from sqlalchemy.engine import make_url

from app.core.config import settings
from app.core.database import engine
from app.models import AppSetting, TelegramMessage
from app.services.json_utils import loads_dict, loads_list


@dataclass(frozen=True)
class SinkStatus:
    name: str
    enabled: bool
    status: str
    note: str


def sink_statuses() -> list[SinkStatus]:
    db_status = "active"
    db_name = "postgresql" if settings.database_url.startswith("postgresql") else "sqlite"
    db_note = "业务主存储，保存配置、账号、目标、消息、规则匹配和运行状态"
    return [
        SinkStatus(db_name, True, db_status, db_note),
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


STORAGE_SCHEMA_PROPOSAL = [
    {
        "table": "telegram_accounts",
        "title": "采集账号",
        "note": "保存 Telegram 登录账号、代理和授权状态。数量不需要越多越好，更重要的是状态健康、分配均衡。",
        "fields": [
            {"name": "id", "type": "bigserial", "keep": "保留", "note": "内部外键使用，方便管理。"},
            {"name": "label", "type": "varchar(120)", "keep": "保留", "note": "用户自定义账号名称。"},
            {"name": "phone", "type": "varchar(64)", "keep": "保留", "note": "账号识别字段，页面可脱敏展示。"},
            {"name": "api_id/api_hash", "type": "integer/varchar", "keep": "保留", "note": "Telethon 登录必需，生产建议加密。"},
            {"name": "session_name", "type": "varchar(160)", "keep": "保留", "note": "本地 session 文件索引。"},
            {"name": "proxy_url", "type": "varchar(500)", "keep": "可选", "note": "账号代理配置，没有代理可为空。"},
            {"name": "status/is_active", "type": "varchar/bool", "keep": "保留", "note": "授权与调度可用性判断。"},
            {"name": "last_error", "type": "text", "keep": "保留", "note": "最近异常，便于排障。"},
        ],
    },
    {
        "table": "telegram_targets",
        "title": "监控目标",
        "note": "保存群组/频道真实名称、类型、成员数和监听状态；导入或可访问性检测时刷新元信息。",
        "fields": [
            {"name": "id", "type": "bigserial", "keep": "保留", "note": "内部外键使用。"},
            {"name": "account_id", "type": "bigint", "keep": "保留", "note": "绑定采集账号，可为空表示自动选择。"},
            {"name": "target", "type": "varchar(500)", "keep": "保留", "note": "用户导入的原始链接、用户名或 ID。"},
            {"name": "normalized_target", "type": "varchar(255)", "keep": "保留", "note": "去重和匹配使用。"},
            {"name": "title", "type": "varchar(255)", "keep": "保留", "note": "Telegram 返回的真实群组/频道名称。"},
            {"name": "target_type", "type": "varchar(40)", "keep": "保留", "note": "group、channel、user 等。"},
            {"name": "participants_count", "type": "integer", "keep": "保留", "note": "成员数或订阅数，部分目标可能拿不到。"},
            {"name": "enabled/status", "type": "bool/varchar", "keep": "保留", "note": "是否纳入自动采集与当前运行状态。"},
            {"name": "last_message_at/last_error", "type": "timestamptz/text", "keep": "保留", "note": "判断采集新鲜度和异常。"},
        ],
    },
    {
        "table": "telegram_messages",
        "title": "消息线索",
        "note": "核心大表。建议业务唯一 ID 使用 md5(tg:source_id:message_id)，PostgreSQL 中继续保留内部数字 ID 以兼容现有外键。",
        "fields": [
            {"name": "id", "type": "bigserial", "keep": "暂保留", "note": "内部关系字段；后续可评估完全改为 message_uid 主键。"},
            {"name": "message_uid", "type": "char(32)", "keep": "保留", "note": "稳定业务 ID，md5(tg:source_id:message_id)，适合导出、去重、外部引用。"},
            {"name": "account_id/target_id", "type": "bigint", "keep": "保留", "note": "关联采集账号和监控目标。"},
            {"name": "source/source_id/source_type", "type": "varchar", "keep": "保留", "note": "消息来源展示、跳转和去重需要。"},
            {"name": "message_id", "type": "varchar(80)", "keep": "保留", "note": "Telegram 原始消息 ID，用于构造消息链接。"},
            {"name": "event_time/insert_time", "type": "timestamptz", "keep": "保留", "note": "发送时间和入库时间，查询和覆盖采集窗口需要。"},
            {"name": "sender_*", "type": "varchar", "keep": "保留", "note": "页面可默认隐藏，但检索和溯源有价值。"},
            {"name": "content/content_md5", "type": "text/char(32)", "keep": "保留", "note": "全文检索和内容去重。"},
            {"name": "message_kind/media_type/media_count", "type": "varchar/integer", "keep": "保留", "note": "区分文本、文件、图片、服务消息。"},
            {"name": "media_name", "type": "建议新增", "keep": "建议", "note": "文件原始名称独立成字段，比只放 raw_payload 更利于列表展示。"},
            {"name": "links_json", "type": "jsonb", "keep": "保留", "note": "PostgreSQL 建议 JSONB；高频链接分析可拆 message_links。"},
            {"name": "views/replies/forwards", "type": "integer", "keep": "保留", "note": "互动数据可在详情中展示。"},
            {"name": "raw_payload", "type": "jsonb", "keep": "保留", "note": "兜底保存 Telegram 原始结构，页面不直接展示全部。"},
            {"name": "channel/sub_channel/category/desc/data_id/similar_id", "type": "mixed", "keep": "可精简", "note": "当前业务价值较弱；多来源/风险分析成熟前可隐藏或后续迁移删除。"},
        ],
    },
    {
        "table": "monitor_runs/crawl_errors",
        "title": "采集运行记录",
        "note": "用于审计每次手动采集、自动回填、监听启动和异常，建议长期保留但可按月归档。",
        "fields": [
            {"name": "run_id/id", "type": "bigserial", "keep": "保留", "note": "任务和异常记录 ID。"},
            {"name": "account_id/target_id", "type": "bigint", "keep": "保留", "note": "定位是哪一个账号和目标出问题。"},
            {"name": "mode/status", "type": "varchar", "keep": "保留", "note": "manual、scheduled、live、success、failed 等。"},
            {"name": "records_seen/records_written", "type": "integer", "keep": "保留", "note": "采集效果评估。"},
            {"name": "error/stage/error_type", "type": "text/varchar", "keep": "保留", "note": "异常处理和告警依据。"},
            {"name": "started_at/finished_at/created_at", "type": "timestamptz", "keep": "保留", "note": "任务耗时和历史追踪。"},
        ],
    },
]


def _mask_database_url(url: str) -> str:
    try:
        parsed = make_url(url)
    except Exception:
        return url
    if parsed.password:
        parsed = parsed.set(password="***")
    return parsed.render_as_string(hide_password=False)


def database_overview(db) -> dict[str, Any]:
    url = make_url(settings.database_url)
    table_counts = {}
    for table in [
        "telegram_accounts",
        "telegram_targets",
        "telegram_messages",
        "monitor_rules",
        "rule_hits",
        "monitor_runs",
        "crawl_errors",
        "app_settings",
    ]:
        try:
            table_counts[table] = db.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
        except Exception:
            table_counts[table] = None
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        status = "active"
        status_note = "连接正常"
    except Exception as exc:
        status = "error"
        status_note = str(exc)
    inspector = inspect(engine)
    return {
        "engine": url.get_backend_name(),
        "driver": url.drivername,
        "database": url.database or "",
        "host": url.host or "local-file",
        "port": url.port,
        "url": _mask_database_url(settings.database_url),
        "status": status,
        "status_note": status_note,
        "table_count": len(inspector.get_table_names()),
        "table_counts": table_counts,
        "recommendation": "PostgreSQL 适合真实业务长期运行；SQLite 更适合单机试用和轻量演示。",
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
