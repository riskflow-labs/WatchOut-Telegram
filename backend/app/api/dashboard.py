from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import MonitorRun, RuleHit, TelegramAccount, TelegramMessage, TelegramTarget, User
from app.schemas import DashboardOut
from app.storage.sinks import get_sink_config, set_sink_config, sink_statuses
from app.telegram.runtime import runtime


router = APIRouter(tags=["dashboard"])


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
