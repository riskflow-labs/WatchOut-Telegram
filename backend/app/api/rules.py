from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import MonitorRule, MonitorRuleNotificationChannel, NotificationChannel, RuleHit, TelegramMessage, User
from app.notifications.dispatcher import dispatch_for_message
from app.rules.engine import evaluate_rules
from app.schemas import RuleCreate, RuleExcludeAppendIn, RuleOut, RuleReprocessIn, RuleReprocessOut
from app.services.json_utils import dumps, loads_list


router = APIRouter(prefix="/rules", tags=["rules"])


def _rule_channel_ids(db: Session, rule_ids: list[int]) -> dict[int, list[int]]:
    if not rule_ids:
        return {}
    rows = (
        db.query(MonitorRuleNotificationChannel.rule_id, MonitorRuleNotificationChannel.channel_id)
        .filter(MonitorRuleNotificationChannel.rule_id.in_(rule_ids))
        .all()
    )
    result: dict[int, list[int]] = {}
    for rule_id, channel_id in rows:
        result.setdefault(rule_id, []).append(channel_id)
    return result


def _sync_rule_channels(db: Session, rule: MonitorRule, channel_ids: list[int]) -> None:
    clean_ids = sorted({int(channel_id) for channel_id in channel_ids if int(channel_id) > 0})
    if clean_ids:
        existing_count = db.query(func.count(NotificationChannel.id)).filter(NotificationChannel.id.in_(clean_ids)).scalar() or 0
        if existing_count != len(clean_ids):
            raise HTTPException(status_code=400, detail="部分推送渠道不存在")
    db.query(MonitorRuleNotificationChannel).filter(MonitorRuleNotificationChannel.rule_id == rule.id).delete(synchronize_session=False)
    for channel_id in clean_ids:
        db.add(MonitorRuleNotificationChannel(rule_id=rule.id, channel_id=channel_id))


def _out(rule: MonitorRule, hit_count: int = 0, recent_hit_at=None, notification_channel_ids: list[int] | None = None) -> RuleOut:
    return RuleOut(
        id=rule.id,
        name=rule.name,
        match_type=rule.match_type,
        patterns=[str(item) for item in loads_list(rule.patterns_json)],
        exclude_patterns=[str(item) for item in loads_list(rule.exclude_patterns_json)],
        target_filter=[str(item) for item in loads_list(rule.target_filter_json)],
        sender_filter=[str(item) for item in loads_list(rule.sender_filter_json)],
        risk_level=rule.risk_level,
        priority=rule.priority,
        enabled=rule.enabled,
        notify=rule.notify,
        notification_channel_ids=notification_channel_ids or [],
        tags=[str(item) for item in loads_list(rule.tags_json)],
        created_at=rule.created_at,
        updated_at=rule.updated_at,
        hit_count=hit_count,
        recent_hit_at=recent_hit_at,
    )


def _validate_rule(payload: RuleCreate) -> None:
    if payload.match_type != "regex":
        return
    for pattern in payload.patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"正则表达式无效：{pattern}（{exc}）") from exc
    for pattern in payload.exclude_patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"排除正则无效：{pattern}（{exc}）") from exc


@router.get("", response_model=list[RuleOut])
def list_rules(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RuleOut]:
    rules = db.query(MonitorRule).order_by(MonitorRule.priority.asc()).all()
    stats = (
        db.query(RuleHit.rule_id, func.count(RuleHit.id), func.max(RuleHit.created_at))
        .filter(RuleHit.rule_id.isnot(None))
        .group_by(RuleHit.rule_id)
        .all()
    )
    stat_map = {rule_id: (count, recent_at) for rule_id, count, recent_at in stats}
    channel_map = _rule_channel_ids(db, [rule.id for rule in rules])
    return [_out(rule, *(stat_map.get(rule.id, (0, None))), notification_channel_ids=channel_map.get(rule.id, [])) for rule in rules]


@router.post("", response_model=RuleOut)
def create_rule(
    payload: RuleCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleOut:
    _validate_rule(payload)
    rule = MonitorRule(
        name=payload.name,
        match_type=payload.match_type,
        patterns_json=dumps(payload.patterns),
        exclude_patterns_json=dumps(payload.exclude_patterns),
        target_filter_json=dumps(payload.target_filter),
        sender_filter_json=dumps(payload.sender_filter),
        risk_level=payload.risk_level,
        priority=payload.priority,
        enabled=payload.enabled,
        notify=payload.notify,
        tags_json=dumps(payload.tags),
    )
    db.add(rule)
    db.flush()
    _sync_rule_channels(db, rule, payload.notification_channel_ids)
    db.commit()
    db.refresh(rule)
    return _out(rule, notification_channel_ids=payload.notification_channel_ids)


@router.patch("/{rule_id}", response_model=RuleOut)
def patch_rule(
    rule_id: int,
    payload: RuleCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleOut:
    _validate_rule(payload)
    rule = db.get(MonitorRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule not found")
    rule.name = payload.name
    rule.match_type = payload.match_type
    rule.patterns_json = dumps(payload.patterns)
    rule.exclude_patterns_json = dumps(payload.exclude_patterns)
    rule.target_filter_json = dumps(payload.target_filter)
    rule.sender_filter_json = dumps(payload.sender_filter)
    rule.risk_level = payload.risk_level
    rule.priority = payload.priority
    rule.enabled = payload.enabled
    rule.notify = payload.notify
    rule.tags_json = dumps(payload.tags)
    _sync_rule_channels(db, rule, payload.notification_channel_ids)
    db.commit()
    db.refresh(rule)
    return _out(rule, notification_channel_ids=payload.notification_channel_ids)


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, bool]:
    rule = db.get(MonitorRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule not found")
    db.query(MonitorRuleNotificationChannel).filter(MonitorRuleNotificationChannel.rule_id == rule.id).delete(synchronize_session=False)
    db.query(RuleHit).filter(RuleHit.rule_id == rule.id).update({RuleHit.rule_id: None})
    db.delete(rule)
    db.commit()
    return {"ok": True}


@router.post("/reprocess", response_model=RuleReprocessOut)
def reprocess_rules(
    payload: RuleReprocessIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleReprocessOut:
    rules_query = db.query(MonitorRule).filter(MonitorRule.enabled == True)  # noqa: E712
    if payload.rule_id is not None:
        rules_query = rules_query.filter(MonitorRule.id == payload.rule_id)
    rules = rules_query.order_by(MonitorRule.priority.asc()).all()
    if payload.rule_id is not None and not rules:
        raise HTTPException(status_code=404, detail="rule not found")

    messages = (
        db.query(TelegramMessage)
        .order_by(desc(TelegramMessage.event_time))
        .limit(payload.limit)
        .all()
    )
    rule_ids = [rule.id for rule in rules]
    if rule_ids and payload.reset_existing:
        db.query(RuleHit).filter(RuleHit.rule_id.in_(rule_ids)).delete(synchronize_session=False)

    created = 0
    notified_message_ids: set[int] = set()
    for message in messages:
        matches = evaluate_rules(message, rules)
        if not matches:
            continue
        message.risk_level = max(message.risk_level or 0, max(match.rule.risk_level for match in matches))
        message.score = max(message.score or 0, min(100, sum(20 + 10 * len(match.matched_patterns) for match in matches)))
        message.hit = 1
        message.keyword_type = "rule"
        message.keyword_source = ",".join(match.rule.name for match in matches[:5])
        for match in matches:
            db.add(
                RuleHit(
                    message_id=message.id,
                    rule_id=match.rule.id,
                    rule_name=match.rule.name,
                    matched_patterns_json=dumps(match.matched_patterns),
                    risk_level=match.rule.risk_level,
                    status="open" if match.rule.notify else "muted",
                )
            )
            created += 1
        if payload.notify_matches and any(match.rule.notify for match in matches):
            dispatch_for_message(db, message)
            notified_message_ids.add(message.id)

    db.commit()
    return RuleReprocessOut(scanned=len(messages), created=created, notified=len(notified_message_ids))


@router.post("/{rule_id}/exclude", response_model=RuleOut)
def append_rule_exclude_pattern(
    rule_id: int,
    payload: RuleExcludeAppendIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleOut:
    rule = db.get(MonitorRule, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule not found")
    pattern = payload.pattern.strip()
    if not pattern:
        raise HTTPException(status_code=400, detail="exclude pattern is required")
    if rule.match_type == "regex":
        try:
            re.compile(pattern)
        except re.error as exc:
            raise HTTPException(status_code=400, detail=f"排除正则无效：{pattern}（{exc}）") from exc
    patterns = [str(item) for item in loads_list(rule.exclude_patterns_json)]
    if pattern not in patterns:
        patterns.append(pattern)
        rule.exclude_patterns_json = dumps(patterns)
        db.commit()
        db.refresh(rule)
    count, recent_at = (
        db.query(func.count(RuleHit.id), func.max(RuleHit.created_at))
        .filter(RuleHit.rule_id == rule.id)
        .one()
    )
    return _out(rule, count or 0, recent_at)
