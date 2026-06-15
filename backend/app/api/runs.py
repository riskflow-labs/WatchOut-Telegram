from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import CrawlError, MonitorRun, User
from app.schemas import CrawlErrorOut, MonitorRunOut


router = APIRouter(prefix="/runs", tags=["runs"])


@router.get("", response_model=list[MonitorRunOut])
def list_runs(
    limit: int = Query(default=100, le=500),
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MonitorRun]:
    return db.query(MonitorRun).order_by(desc(MonitorRun.started_at)).limit(limit).all()


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
) -> MonitorRun:
    run = db.get(MonitorRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="run not found")
    return run
