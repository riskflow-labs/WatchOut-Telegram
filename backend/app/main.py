from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import routers
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.bootstrap import init_database, seed_defaults
from app.telegram.runtime import runtime
from app.workers.account_health_scheduler import account_health_scheduler
from app.workers.backfill_scheduler import backfill_scheduler


async def _restore_enabled_targets_after_startup() -> None:
    await asyncio.sleep(5)
    await runtime.restore_enabled_targets()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.session_dir.mkdir(parents=True, exist_ok=True)
    init_database()
    db = SessionLocal()
    try:
        seed_defaults(db)
    finally:
        db.close()
    backfill_scheduler.start()
    account_health_scheduler.start()
    restore_task = asyncio.create_task(_restore_enabled_targets_after_startup())
    try:
        yield
    finally:
        restore_task.cancel()
        try:
            await restore_task
        except asyncio.CancelledError:
            pass
        await backfill_scheduler.shutdown()
        await account_health_scheduler.shutdown()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in routers:
    app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


frontend_dist = Path(os.getenv("WATCHOUT_TELEGRAM_FRONTEND_DIST", "/app/frontend_dist"))
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
