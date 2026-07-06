from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import asc, desc, func, nullslast
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CrawlError, MonitorRun, TelegramAccount, TelegramTarget, User
from app.schemas import CrawlErrorOut, MonitorRunOut


router = APIRouter(prefix="/runs", tags=["runs"])


RUN_SORT_COLUMNS = {
    "id": MonitorRun.id,
    "target": TelegramTarget.title,
    "account": TelegramAccount.label,
    "mode": MonitorRun.mode,
    "status": MonitorRun.status,
    "records_seen": MonitorRun.records_seen,
    "records_written": MonitorRun.records_written,
    "started_at": MonitorRun.started_at,
    "finished_at": MonitorRun.finished_at,
    "duration": func.coalesce(MonitorRun.finished_at, func.now()) - MonitorRun.started_at,
}


@router.get("", response_model=list[MonitorRunOut])
def list_runs(
    target_id: int | None = None,
    status: str = "",
    mode: str = "",
    sort: str = "started_at",
    direction: str = "desc",
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MonitorRunOut]:
    query = _runs_query(db)
    if target_id:
        query = query.filter(MonitorRun.target_id == target_id)
    if status:
        query = query.filter(MonitorRun.status == status)
    if mode:
        query = query.filter(MonitorRun.mode == mode)
    sort_column = RUN_SORT_COLUMNS.get(sort, MonitorRun.started_at)
    order = asc(sort_column) if direction == "asc" else nullslast(desc(sort_column))
    rows = query.order_by(order, desc(MonitorRun.id)).offset(offset).limit(limit).all()
    return [_run_out(*row) for row in rows]


@router.get("/count")
def count_runs(
    target_id: int | None = None,
    status: str = "",
    mode: str = "",
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int]:
    query = db.query(MonitorRun)
    if target_id:
        query = query.filter(MonitorRun.target_id == target_id)
    if status:
        query = query.filter(MonitorRun.status == status)
    if mode:
        query = query.filter(MonitorRun.mode == mode)
    return {"total": query.count()}


@router.get("/errors", response_model=list[CrawlErrorOut])
def list_crawl_errors(
    limit: int = Query(default=100, le=500),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[CrawlError]:
    return db.query(CrawlError).order_by(desc(CrawlError.created_at)).limit(limit).all()


@router.get("/{run_id}", response_model=MonitorRunOut)
def get_run(
    run_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MonitorRunOut:
    row = _runs_query(db).filter(MonitorRun.id == run_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return _run_out(*row)


def _runs_query(db: Session):
    return (
        db.query(MonitorRun, TelegramTarget, TelegramAccount)
        .outerjoin(TelegramTarget, MonitorRun.target_id == TelegramTarget.id)
        .outerjoin(TelegramAccount, MonitorRun.account_id == TelegramAccount.id)
    )


def _duration_seconds(run: MonitorRun) -> int | None:
    if not run.started_at:
        return None
    finished_at = run.finished_at
    if finished_at is None and run.status == "running":
        finished_at = datetime.now(timezone.utc)
    if finished_at is None:
        return None
    started_at = run.started_at
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if finished_at.tzinfo is None:
        finished_at = finished_at.replace(tzinfo=timezone.utc)
    return max(0, int((finished_at - started_at).total_seconds()))


def _run_out(run: MonitorRun, target: TelegramTarget | None, account: TelegramAccount | None) -> MonitorRunOut:
    return MonitorRunOut(
        id=run.id,
        account_id=run.account_id,
        target_id=run.target_id,
        account_label=(account.label or account.phone) if account else "",
        target_title=target.title if target else "",
        target_ref=(target.target or target.normalized_target) if target else "",
        mode=run.mode,
        status=run.status,
        records_seen=run.records_seen,
        records_written=run.records_written,
        error=run.error,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=_duration_seconds(run),
    )
