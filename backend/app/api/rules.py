from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import MonitorRule, User
from app.schemas import RuleCreate, RuleOut
from app.services.json_utils import dumps, loads_list


router = APIRouter(prefix="/rules", tags=["rules"])


def _out(rule: MonitorRule) -> RuleOut:
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
        tags=[str(item) for item in loads_list(rule.tags_json)],
        created_at=rule.created_at,
        updated_at=rule.updated_at,
    )


@router.get("", response_model=list[RuleOut])
def list_rules(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RuleOut]:
    return [_out(rule) for rule in db.query(MonitorRule).order_by(MonitorRule.priority.asc()).all()]


@router.post("", response_model=RuleOut)
def create_rule(
    payload: RuleCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleOut:
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
    db.commit()
    db.refresh(rule)
    return _out(rule)


@router.patch("/{rule_id}", response_model=RuleOut)
def patch_rule(
    rule_id: int,
    payload: RuleCreate,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RuleOut:
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
    db.commit()
    db.refresh(rule)
    return _out(rule)
