from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routers
from app.core.config import settings
from app.core.database import SessionLocal
from app.services.bootstrap import init_database, seed_defaults
from app.workers.backfill_scheduler import backfill_scheduler


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
    try:
        yield
    finally:
        await backfill_scheduler.shutdown()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for router in routers:
    app.include_router(router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
