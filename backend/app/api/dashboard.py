from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CrawlError, MonitorRun, NotificationDelivery, RuleHit, TelegramAccount, TelegramMessage, TelegramTarget, User
from app.schemas import DashboardOut
from app.storage.sinks import database_overview, get_sink_config, set_sink_config, sink_statuses
from app.telegram.runtime import runtime


router = APIRouter(tags=["dashboard"])


RANGE_HOURS = {
    "24h": 24,
    "48h": 48,
    "7d": 24 * 7,
    "30d": 24 * 30,
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str:
    return _as_utc(value).isoformat() if value else ""


def _range_hours(value: str) -> int:
    return RANGE_HOURS.get(value, 24)


def _granularity_hours(hours: int) -> int:
    if hours <= 24:
        return 1
    if hours <= 48:
        return 2
    if hours <= 24 * 7:
        return 6
    return 24


def _bucket_start(value: datetime, granularity_hours: int) -> datetime:
    value = _as_utc(value) or value
    if granularity_hours >= 24:
        return value.replace(hour=0, minute=0, second=0, microsecond=0)
    hour = (value.hour // granularity_hours) * granularity_hours
    return value.replace(hour=hour, minute=0, second=0, microsecond=0)


def _bucket_key(value: datetime) -> str:
    return value.isoformat()


def _pct_change(current: int, previous: int) -> int | None:
    if previous == 0:
        return None if current == 0 else 100
    return round(((current - previous) / previous) * 100)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100, 1)


def _dedupe_anomalies(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    severity_rank = {"critical": 3, "warning": 2, "info": 1}
    grouped: dict[tuple[str, object], dict[str, object]] = {}
    counts: Counter[tuple[str, object]] = Counter()
    for row in rows:
        key = (str(row.get("object_type") or row.get("type") or ""), row.get("object_id") or row.get("object_name") or row.get("type"))
        counts[key] += 1
        current = grouped.get(key)
        if current is None or _anomaly_sort_key(row, severity_rank) > _anomaly_sort_key(current, severity_rank):
            grouped[key] = dict(row)
    merged = list(grouped.values())
    for item in merged:
        key = (str(item.get("object_type") or item.get("type") or ""), item.get("object_id") or item.get("object_name") or item.get("type"))
        duplicate_count = counts[key] - 1
        if duplicate_count > 0:
            item["merged_count"] = duplicate_count
            item["description"] = f"{item.get('description') or ''}；已合并同对象 {duplicate_count} 条重复提醒"
    return sorted(merged, key=lambda row: _anomaly_sort_key(row, severity_rank), reverse=True)


def _anomaly_sort_key(row: dict[str, object], severity_rank: dict[str, int]) -> tuple[int, datetime]:
    occurred_at = _parse_iso_datetime(str(row.get("occurred_at") or ""))
    return (severity_rank.get(str(row.get("severity") or ""), 0), occurred_at or datetime.min.replace(tzinfo=timezone.utc))


def _parse_iso_datetime(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return _as_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _normalize_run_status(value: str) -> str:
    normalized = str(value or "").lower()
    if normalized in {"success", "completed", "done", "finished"}:
        return "success"
    if normalized in {"failed", "error"}:
        return "failed"
    if normalized in {"running", "backfilling", "starting"}:
        return "running"
    if normalized in {"queued", "pending"}:
        return "queued"
    return "other"


def _run_kind(value: str) -> str:
    normalized = str(value or "").lower()
    if normalized in {"live", "listen", "listener"}:
        return "live"
    if normalized in {"scheduled", "auto", "scheduler"}:
        return "scheduled_backfill"
    return "manual_backfill"


def _message_query(db: Session, start: datetime, end: datetime, account_id: int | None, target_id: int | None):
    query = db.query(TelegramMessage).filter(TelegramMessage.event_time >= start, TelegramMessage.event_time < end)
    if account_id:
        query = query.filter(TelegramMessage.account_id == account_id)
    if target_id:
        query = query.filter(TelegramMessage.target_id == target_id)
    return query


def _run_query(db: Session, start: datetime, end: datetime, account_id: int | None, target_id: int | None, collection_type: str):
    query = db.query(MonitorRun).filter(MonitorRun.started_at >= start, MonitorRun.started_at < end)
    if account_id:
        query = query.filter(MonitorRun.account_id == account_id)
    if target_id:
        query = query.filter(MonitorRun.target_id == target_id)
    if collection_type and collection_type != "all":
        if collection_type == "live":
            query = query.filter(MonitorRun.mode.in_(["live", "listen", "listener"]))
        elif collection_type == "backfill":
            query = query.filter(~MonitorRun.mode.in_(["live", "listen", "listener"]))
        else:
            query = query.filter(MonitorRun.mode == collection_type)
    return query


def _hit_query(db: Session, start: datetime, end: datetime, account_id: int | None, target_id: int | None):
    query = db.query(RuleHit).join(TelegramMessage, RuleHit.message_id == TelegramMessage.id).filter(
        RuleHit.created_at >= start,
        RuleHit.created_at < end,
    )
    if account_id:
        query = query.filter(TelegramMessage.account_id == account_id)
    if target_id:
        query = query.filter(TelegramMessage.target_id == target_id)
    return query


def _target_label(target: TelegramTarget | None, fallback: str = "") -> str:
    if not target:
        return fallback or "未知目标"
    return target.title or target.target or f"目标 #{target.id}"


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardOut:
    return DashboardOut(
        accounts=db.query(TelegramAccount).count(),
        active_accounts=db.query(TelegramAccount).filter(TelegramAccount.status == "authorized").count(),
        targets=db.query(TelegramTarget).count(),
        enabled_targets=db.query(TelegramTarget).filter(TelegramTarget.enabled == True).count(),  # noqa: E712
        messages=db.query(TelegramMessage).count(),
        hits=db.query(RuleHit).count(),
        open_hits=db.query(RuleHit).filter(RuleHit.status == "open").count(),
        runs=db.query(MonitorRun).count(),
    )


@router.get("/dashboard/overview")
def dashboard_overview(
    range: str = Query(default="24h", pattern="^(24h|48h|7d|30d)$"),
    account_id: int | None = None,
    target_id: int | None = None,
    collection_type: str = "all",
    timezone_name: str = Query(default="Asia/Shanghai", alias="timezone"),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    now = _utcnow()
    hours = _range_hours(range)
    start = now - timedelta(hours=hours)
    previous_start = start - timedelta(hours=hours)
    granularity = _granularity_hours(hours)
    bucket_start = _bucket_start(start, granularity)

    accounts = db.query(TelegramAccount).order_by(TelegramAccount.id.asc()).all()
    targets_query = db.query(TelegramTarget)
    if account_id:
        targets_query = targets_query.filter(TelegramTarget.account_id == account_id)
    targets = targets_query.order_by(TelegramTarget.id.asc()).all()
    target_ids = [target.id for target in targets]
    running_ids = runtime.running_target_ids()

    current_messages = _message_query(db, start, now, account_id, target_id).all()
    previous_messages = _message_query(db, previous_start, start, account_id, target_id).all()
    current_hits = _hit_query(db, start, now, account_id, target_id).all()
    current_runs = _run_query(db, start, now, account_id, target_id, collection_type).all()

    latest_conditions = []
    if account_id:
        latest_conditions.append(TelegramMessage.account_id == account_id)
    if target_id:
        latest_conditions.append(TelegramMessage.target_id == target_id)
    latest_message = db.query(TelegramMessage).filter(*latest_conditions).order_by(desc(TelegramMessage.insert_time)).first()
    latest_insert_time = _as_utc(latest_message.insert_time if latest_message else None)
    collection_delay_minutes = round((now - latest_insert_time).total_seconds() / 60) if latest_insert_time else None

    authorized_accounts = [account for account in accounts if account.status == "authorized" and account.is_active]
    account_issues = [
        account for account in accounts
        if account.is_active and (account.status not in {"authorized", "code_sent"} or account.last_error)
    ]
    enabled_targets = [target for target in targets if target.enabled]

    message_count = len(current_messages)
    previous_message_count = len(previous_messages)
    hit_count = len(current_hits)
    hit_message_ids = {hit.message_id for hit in current_hits}
    hit_rate = _rate(len(hit_message_ids), message_count)

    run_status = Counter(_normalize_run_status(run.status) for run in current_runs)
    run_kind = Counter(_run_kind(run.mode) for run in current_runs)
    total_runs = len(current_runs)
    success_runs = run_status["success"]
    failed_runs = run_status["failed"]
    running_runs = run_status["running"]
    success_rate = _rate(success_runs, total_runs)

    health_rows = []
    health_counts = Counter()
    anomaly_rows = []
    for target in targets:
        target_message_count = sum(1 for message in current_messages if message.target_id == target.id)
        recent_time = _as_utc(target.last_message_at)
        has_recent = bool(recent_time and recent_time >= start)
        failed_for_target = sum(1 for run in current_runs if run.target_id == target.id and _normalize_run_status(run.status) == "failed")
        runtime_status = "listening" if target.id in running_ids else target.status
        if not target.enabled:
            health = "disabled"
        elif target.last_error or failed_for_target:
            health = "error"
        elif target.id in running_ids and has_recent:
            health = "normal"
        elif target.id in running_ids:
            health = "low_activity"
        elif recent_time and (now - recent_time) > timedelta(hours=max(6, min(hours, 24))):
            health = "stale"
        else:
            health = "idle"
        health_counts[health] += 1
        row = {
            "target_id": target.id,
            "account_id": target.account_id,
            "name": _target_label(target),
            "target": target.target,
            "status": runtime_status,
            "health": health,
            "last_message_at": _iso(recent_time),
            "message_count": target_message_count,
            "failed_runs": failed_for_target,
            "last_error": target.last_error,
        }
        health_rows.append(row)
        if health in {"error", "stale"}:
            anomaly_rows.append(
                {
                    "severity": "critical" if health == "error" else "warning",
                    "type": "target_health",
                    "title": "目标异常" if health == "error" else "疑似断流目标",
                    "description": target.last_error or f"所选周期内消息量 {target_message_count}，最近消息 {row['last_message_at'] or '未知'}",
                    "occurred_at": row["last_message_at"],
                    "object_type": "target",
                    "object_id": target.id,
                    "object_name": row["name"],
                    "action": "targets",
                }
            )

    for account in account_issues:
        anomaly_rows.append(
            {
                "severity": "critical" if account.status in {"error", "unauthorized"} else "warning",
                "type": "account_health",
                "title": "账号需要处理",
                "description": account.last_error or f"账号状态为 {account.status}",
                "occurred_at": _iso(account.updated_at if hasattr(account, "updated_at") else account.created_at),
                "object_type": "account",
                "object_id": account.id,
                "object_name": account.label or account.phone,
                "action": "accounts",
            }
        )

    failed_run_rows = sorted(
        [run for run in current_runs if _normalize_run_status(run.status) == "failed"],
        key=lambda item: item.started_at,
        reverse=True,
    )[:20]
    target_by_id = {target.id: target for target in targets}
    for run in failed_run_rows:
        target = target_by_id.get(run.target_id)
        anomaly_rows.append(
            {
                "severity": "critical",
                "type": "run_failed",
                "title": "采集任务失败",
                "description": run.error or f"{run.mode} 任务失败",
                "occurred_at": _iso(run.finished_at or run.started_at),
                "object_type": "target" if target else "run",
                "object_id": run.target_id or run.id,
                "object_name": _target_label(target, f"任务 #{run.id}"),
                "action": "runs",
            }
        )

    failed_deliveries = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.created_at >= start, NotificationDelivery.created_at < now, NotificationDelivery.status == "failed")
        .order_by(desc(NotificationDelivery.created_at))
        .limit(5)
        .all()
    )
    for delivery in failed_deliveries:
        anomaly_rows.append(
            {
                "severity": "warning",
                "type": "notification_failed",
                "title": "通知发送失败",
                "description": delivery.error or "外部通知通道返回失败",
                "occurred_at": _iso(delivery.created_at),
                "object_type": "notification",
                "object_id": delivery.id,
                "object_name": f"投递 #{delivery.id}",
                "action": "notifications",
            }
        )

    high_risk_open = [hit for hit in current_hits if (hit.risk_level or 1) >= 3 and hit.status == "open"]
    if high_risk_open:
        anomaly_rows.append(
            {
                "severity": "warning",
                "type": "high_risk_open_hits",
                "title": "高风险线索待处理",
                "description": f"{len(high_risk_open)} 条 L3+ 线索仍待处理",
                "occurred_at": _iso(max((_as_utc(hit.created_at) for hit in high_risk_open if hit.created_at), default=None)),
                "object_type": "hit",
                "object_id": None,
                "object_name": "命中线索",
                "action": "matches",
            }
        )

    if collection_delay_minutes is not None and collection_delay_minutes > 120 and enabled_targets:
        anomaly_rows.append(
            {
                "severity": "warning",
                "type": "collection_delay",
                "title": "采集延迟偏高",
                "description": f"距离最近入库消息已 {collection_delay_minutes} 分钟",
                "occurred_at": _iso(latest_insert_time),
                "object_type": "message",
                "object_id": latest_message.id if latest_message else None,
                "object_name": "最近消息",
                "action": "messages",
            }
        )

    grouped_anomalies = _dedupe_anomalies(anomaly_rows)

    system_status = "normal"
    if any(item["severity"] == "critical" for item in grouped_anomalies):
        system_status = "critical"
    elif grouped_anomalies or account_issues or health_counts["stale"]:
        system_status = "warning"

    buckets: dict[str, dict[str, object]] = {}
    cursor = bucket_start
    end_bucket = _bucket_start(now, granularity)
    while cursor <= end_bucket:
        buckets[_bucket_key(cursor)] = {
            "start": _bucket_key(cursor),
            "end": _bucket_key(cursor + timedelta(hours=granularity)),
            "messages": 0,
            "hits": 0,
            "hit_rate": 0.0,
            "live_messages": 0,
            "backfill_messages": 0,
            "failed_runs": 0,
        }
        cursor += timedelta(hours=granularity)
    bucket_message_ids: dict[str, set[int]] = defaultdict(set)
    for message in current_messages:
        key = _bucket_key(_bucket_start(message.event_time, granularity))
        if key not in buckets:
            continue
        buckets[key]["messages"] = int(buckets[key]["messages"]) + 1
        bucket_message_ids[key].add(message.id)
        if str(message.status or "").lower() == "backfill":
            buckets[key]["backfill_messages"] = int(buckets[key]["backfill_messages"]) + 1
        else:
            buckets[key]["live_messages"] = int(buckets[key]["live_messages"]) + 1
    for hit in current_hits:
        key = _bucket_key(_bucket_start(hit.created_at, granularity))
        if key in buckets:
            buckets[key]["hits"] = int(buckets[key]["hits"]) + 1
    for run in current_runs:
        if _normalize_run_status(run.status) != "failed":
            continue
        key = _bucket_key(_bucket_start(run.started_at, granularity))
        if key in buckets:
            buckets[key]["failed_runs"] = int(buckets[key]["failed_runs"]) + 1
    for key, row in buckets.items():
        row["hit_rate"] = _rate(int(row["hits"]), int(row["messages"]))

    message_type_counts = Counter()
    for message in current_messages:
        kind = message.media_type if message.media_type and message.media_type != "none" else message.message_kind or "unknown"
        normalized = str(kind or "unknown").lower()
        if normalized in {"message", "none", ""}:
            normalized = "text"
        message_type_counts[normalized] += 1
    message_types = [
        {"type": key, "count": count, "ratio": _rate(count, message_count)}
        for key, count in message_type_counts.most_common()
    ]

    target_stats = []
    for target in targets:
        messages_for_target = [message for message in current_messages if message.target_id == target.id]
        hits_for_target = [hit for hit in current_hits if hit.message and hit.message.target_id == target.id]
        previous_for_target = [message for message in previous_messages if message.target_id == target.id]
        target_stats.append(
            {
                "target_id": target.id,
                "name": _target_label(target),
                "status": "listening" if target.id in running_ids else target.status,
                "health": next((row["health"] for row in health_rows if row["target_id"] == target.id), "idle"),
                "messages": len(messages_for_target),
                "previous_messages": len(previous_for_target),
                "change_percent": _pct_change(len(messages_for_target), len(previous_for_target)),
                "hits": len(hits_for_target),
                "hit_rate": _rate(len({hit.message_id for hit in hits_for_target}), len(messages_for_target)),
                "last_message_at": _iso(_as_utc(target.last_message_at)),
            }
        )

    risk_counts = Counter()
    rule_counts = Counter()
    for hit in current_hits:
        level = "high" if (hit.risk_level or 1) >= 3 else "medium" if (hit.risk_level or 1) == 2 else "low"
        risk_counts[level] += 1
        rule_counts[hit.rule_name or f"规则 #{hit.rule_id or '-'}"] += 1

    return {
        "generated_at": _iso(now),
        "timezone": timezone_name,
        "time_range": {
            "preset": range,
            "start": _iso(start),
            "end": _iso(now),
            "previous_start": _iso(previous_start),
            "granularity_hours": granularity,
            "label": {"24h": "近24小时", "48h": "近48小时", "7d": "近7天", "30d": "近30天"}[range],
        },
        "filters": {"account_id": account_id, "target_id": target_id, "collection_type": collection_type},
        "system_status": {
            "level": system_status,
            "label": {"normal": "正常", "warning": "部分异常", "critical": "严重异常"}[system_status],
            "anomaly_count": len(grouped_anomalies),
            "critical_count": sum(1 for item in grouped_anomalies if item["severity"] == "critical"),
            "warning_count": sum(1 for item in grouped_anomalies if item["severity"] == "warning"),
        },
        "summary": {
            "account_health": {
                "authorized": len(authorized_accounts),
                "total": len(accounts),
                "abnormal": len(account_issues),
                "scope": "当前状态，不受时间范围影响",
            },
            "target_health": {
                "normal": health_counts["normal"] + health_counts["low_activity"],
                "enabled": len(enabled_targets),
                "abnormal": health_counts["error"] + health_counts["stale"],
                "scope": "当前状态 + 最近消息时间 + 任务失败",
            },
            "new_messages": {
                "value": message_count,
                "previous": previous_message_count,
                "change_percent": _pct_change(message_count, previous_message_count),
                "scope": "所选周期内按 event_time 去重后的入库消息数",
            },
            "risk_hits": {
                "value": hit_count,
                "hit_message_count": len(hit_message_ids),
                "hit_rate": hit_rate,
                "scope": "所选周期内 rule_hits.created_at 命中记录",
            },
            "task_success": {
                "success": success_runs,
                "total": total_runs,
                "failed": failed_runs,
                "running": running_runs,
                "queued": run_status["queued"],
                "other": run_status["other"],
                "success_rate": success_rate,
                "live": run_kind["live"],
                "manual_backfill": run_kind["manual_backfill"],
                "scheduled_backfill": run_kind["scheduled_backfill"],
                "scope": "所选周期内 started_at 落入范围的采集任务",
            },
            "collection_delay": {
                "minutes": collection_delay_minutes,
                "last_insert_time": _iso(latest_insert_time),
                "scope": "当前时间 - 最近一条入库消息 insert_time",
            },
            "archive_total": {"messages": db.query(TelegramMessage).count(), "scope": "历史辅助指标"},
        },
        "collection_trend": list(buckets.values()),
        "target_health": {
            "counts": dict(health_counts),
            "rows": sorted(health_rows, key=lambda row: (row["health"] not in {"error", "stale"}, -int(row["message_count"])))[:10],
        },
        "anomalies": grouped_anomalies[:12],
        "active_targets": sorted(target_stats, key=lambda row: row["messages"], reverse=True)[:10],
        "message_type_distribution": message_types,
        "task_quality": {
            "total": total_runs,
            "success": success_runs,
            "failed": failed_runs,
            "running": running_runs,
            "queued": run_status["queued"],
            "other": run_status["other"],
            "success_rate": success_rate,
            "live": run_kind["live"],
            "manual_backfill": run_kind["manual_backfill"],
            "scheduled_backfill": run_kind["scheduled_backfill"],
            "records_seen": sum(run.records_seen or 0 for run in current_runs),
            "records_written": sum(run.records_written or 0 for run in current_runs),
            "write_rate": _rate(sum(run.records_written or 0 for run in current_runs), sum(run.records_seen or 0 for run in current_runs)),
        },
        "risk_distribution": {
            "levels": [
                {"key": "high", "label": "高风险 L3+", "count": risk_counts["high"]},
                {"key": "medium", "label": "中风险 L2", "count": risk_counts["medium"]},
                {"key": "low", "label": "低风险 L1", "count": risk_counts["low"]},
            ],
            "rule_rank": [{"name": name, "count": count} for name, count in rule_counts.most_common(8)],
            "open_high_risk": len(high_risk_open),
        },
        "p1_extensions": {
            "active_target_sort_keys": ["messages", "hits", "hit_rate", "health"],
            "cross_filter_ready": True,
            "baseline_ready": False,
        },
        "p2_extensions": {
            "auto_anomaly_detection_ready": False,
            "trend_reason_ready": False,
            "notification_quality_ready": False,
            "rule_accuracy_ready": False,
        },
    }


def _hour_key(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0).isoformat()


@router.get("/dashboard/trends")
def dashboard_trends(
    days: int = Query(default=7, ge=1, le=30),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    now = datetime.now(timezone.utc)
    since = now - timedelta(days=days)
    start_hour = since.replace(minute=0, second=0, microsecond=0)
    end_hour = now.replace(minute=0, second=0, microsecond=0)
    messages = (
        db.query(
            TelegramMessage.event_time,
            TelegramMessage.target_id,
            TelegramMessage.source,
            TelegramMessage.message_kind,
            TelegramMessage.media_type,
            TelegramMessage.hit,
            TelegramMessage.risk_level,
        )
        .filter(TelegramMessage.event_time >= since)
        .all()
    )
    runs = (
        db.query(MonitorRun.started_at, MonitorRun.status, MonitorRun.records_seen, MonitorRun.records_written)
        .filter(MonitorRun.started_at >= since)
        .all()
    )
    hits = db.query(RuleHit.created_at, RuleHit.risk_level).filter(RuleHit.created_at >= since).all()
    targets = db.query(TelegramTarget.id, TelegramTarget.title, TelegramTarget.target, TelegramTarget.enabled, TelegramTarget.status, TelegramTarget.last_error).all()

    message_hours: dict[str, dict[str, int]] = defaultdict(lambda: {"messages": 0, "hits": 0})
    cursor = start_hour
    while cursor <= end_hour:
        message_hours[_hour_key(cursor)]
        cursor += timedelta(hours=1)
    target_counts: Counter[int] = Counter()
    source_counts: Counter[str] = Counter()
    message_types: Counter[str] = Counter()
    for event_time, target_id, source, message_kind, media_type, hit, _risk_level in messages:
        key = _hour_key(event_time)
        message_hours[key]["messages"] += 1
        if hit:
            message_hours[key]["hits"] += 1
        if target_id:
            target_counts[target_id] += 1
        else:
            source_counts[source or "未知来源"] += 1
        kind = media_type if media_type and media_type != "none" else message_kind or "unknown"
        message_types[kind] += 1

    run_hours: dict[str, dict[str, int]] = defaultdict(lambda: {"success": 0, "failed": 0, "running": 0, "seen": 0, "written": 0})
    cursor = start_hour
    while cursor <= end_hour:
        run_hours[_hour_key(cursor)]
        cursor += timedelta(hours=1)
    for started_at, status, records_seen, records_written in runs:
        key = _hour_key(started_at)
        normalized = str(status or "").lower()
        if normalized in {"success", "completed"}:
            run_hours[key]["success"] += 1
        elif normalized in {"failed", "error"}:
            run_hours[key]["failed"] += 1
        elif normalized in {"running", "backfilling", "starting"}:
            run_hours[key]["running"] += 1
        run_hours[key]["seen"] += records_seen or 0
        run_hours[key]["written"] += records_written or 0

    hit_hours: dict[str, dict[str, int]] = defaultdict(lambda: {"total": 0, "l1": 0, "l2": 0, "l3": 0})
    cursor = start_hour
    while cursor <= end_hour:
        hit_hours[_hour_key(cursor)]
        cursor += timedelta(hours=1)
    for created_at, risk_level in hits:
        key = _hour_key(created_at)
        hit_hours[key]["total"] += 1
        level_key = f"l{min(max(risk_level or 1, 1), 3)}"
        hit_hours[key][level_key] += 1

    target_names = {target_id: title or target or f"target #{target_id}" for target_id, title, target, _enabled, _status, _error in targets}
    active_targets = [
        {"target_id": target_id, "name": target_names.get(target_id, f"target #{target_id}"), "messages": count}
        for target_id, count in target_counts.most_common(8)
    ]
    if len(active_targets) < 8:
        active_targets.extend(
            {"target_id": None, "name": source, "messages": count}
            for source, count in source_counts.most_common(8 - len(active_targets))
        )

    health = Counter()
    for _target_id, _title, _target, enabled, status, last_error in targets:
        normalized = str(status or "").lower()
        if last_error:
            health["error"] += 1
        elif not enabled:
            health["disabled"] += 1
        elif normalized in {"listening", "running"}:
            health["listening"] += 1
        elif normalized in {"backfilling", "starting"}:
            health["working"] += 1
        else:
            health["idle"] += 1

    return {
        "since": since.isoformat(),
        "until": now.isoformat(),
        "days": days,
        "message_hours": [{"hour": key, **value} for key, value in sorted(message_hours.items())],
        "run_hours": [{"hour": key, **value} for key, value in sorted(run_hours.items())],
        "hit_hours": [{"hour": key, **value} for key, value in sorted(hit_hours.items())],
        "active_targets": active_targets,
        "message_types": [{"type": key, "count": count} for key, count in message_types.most_common(8)],
        "target_health": dict(health),
    }


@router.get("/runtime")
def runtime_status(_user: User = Depends(get_current_user)) -> dict[str, object]:
    return {"running_target_ids": sorted(runtime.running_target_ids())}


@router.get("/storage/sinks")
def storage_sinks(_user: User = Depends(get_current_user)) -> list[dict[str, object]]:
    return [status.__dict__ for status in sink_statuses()]


@router.get("/storage/config")
def storage_config(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return get_sink_config(db)


@router.get("/storage/overview")
def storage_overview(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return {"database": database_overview(db), "sinks": [status.__dict__ for status in sink_statuses()]}


@router.put("/storage/config")
def update_storage_config(
    payload: dict[str, object],
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    return set_sink_config(db, payload)


@router.get("/targets/health")
def target_health(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    targets = db.query(TelegramTarget).order_by(TelegramTarget.id.asc()).all()
    running_ids = runtime.running_target_ids()
    rows = []
    for target in targets:
        status = "listening" if target.id in running_ids else target.status
        severity = 0 if status == "listening" else 2 if target.enabled else 1
        rows.append(
            {
                "target_id": target.id,
                "target": target.target,
                "title": target.title,
                "enabled": target.enabled,
                "status": status,
                "severity": severity,
                "last_message_at": target.last_message_at,
                "last_error": target.last_error,
            }
        )
    return rows
