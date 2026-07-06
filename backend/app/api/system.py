from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.database import get_db
from app.models import User
from app.services.enrichment import translate_text
from app.services.intelligence_settings import (
    effective_translation_target,
    get_intelligence_settings,
    set_intelligence_settings,
)
from app.services.collection_settings import get_collection_settings, set_collection_settings
from app.storage.sinks import _mask_database_url
from app.workers.backfill_scheduler import backfill_scheduler


router = APIRouter(prefix="/system", tags=["system"])


class DatabaseConfigIn(BaseModel):
    engine: str = Field(default="postgresql")
    host: str = "localhost"
    port: int = 5432
    database: str = "watchout_telegram"
    username: str = "watchout"
    password: str = ""
    sqlite_path: str = "./data/app.db"
    url: str = ""


class TranslationTestIn(BaseModel):
    text: str = ""
    target_language: str = ""
    config: dict[str, Any] = Field(default_factory=dict)


def _database_url_from_payload(payload: DatabaseConfigIn) -> str:
    if payload.url.strip():
        return payload.url.strip()
    if payload.engine == "sqlite":
        return f"sqlite:///{payload.sqlite_path or './data/app.db'}"
    return (
        "postgresql+psycopg://"
        f"{payload.username}:{payload.password}@{payload.host}:{payload.port}/{payload.database}"
    )


def _database_config_from_url(url_text: str) -> dict[str, Any]:
    url = make_url(url_text)
    engine = "sqlite" if url.get_backend_name() == "sqlite" else "postgresql"
    return {
        "engine": engine,
        "driver": url.drivername,
        "host": url.host or "localhost",
        "port": url.port or (5432 if engine == "postgresql" else None),
        "database": url.database or "",
        "username": url.username or "",
        "sqlite_path": url.database if engine == "sqlite" else "./data/app.db",
        "url": _mask_database_url(url_text),
        "restart_required": True,
    }


@router.get("/database/config")
def database_config(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return _database_config_from_url(settings.database_url)


@router.post("/database/test")
def test_database_config(
    payload: DatabaseConfigIn,
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    url_text = _database_url_from_payload(payload)
    engine = None
    try:
        engine = create_engine(
            url_text,
            connect_args={"check_same_thread": False} if url_text.startswith("sqlite") else {},
        )
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"ok": True, "message": "连接正常", "url": _mask_database_url(url_text)}
    except Exception as exc:
        return {"ok": False, "message": str(exc), "url": _mask_database_url(url_text)}
    finally:
        if engine is not None:
            engine.dispose()


@router.get("/intelligence/config")
def intelligence_config(
    _user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    config = get_intelligence_settings(db)
    config["effective_translation_target"] = effective_translation_target(config)
    return config


@router.put("/intelligence/config")
def update_intelligence_config(
    payload: dict[str, Any],
    _user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    config = set_intelligence_settings(db, payload)
    config["effective_translation_target"] = effective_translation_target(config)
    return config


@router.post("/intelligence/translate-test")
def test_intelligence_translation(
    payload: TranslationTestIn,
    _user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    config = payload.config if isinstance(payload.config, dict) and payload.config else get_intelligence_settings(db)
    resolved_target = payload.target_language or effective_translation_target(config)
    result = translate_text(payload.text, config, target_language=resolved_target)
    return {
        "ok": result["translation_status"] == "translated",
        "target_language": resolved_target,
        "source_language": result["language"] or "auto",
        "translation_engine": result["translation_engine"],
        "translation_status": result["translation_status"],
        "translated_content": result["translated_content"],
        "desc": result["desc"],
    }


@router.get("/collection/config")
def collection_config(
    _user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    config = get_collection_settings(db)
    config["scheduler"] = backfill_scheduler.status()
    return config


@router.put("/collection/config")
async def update_collection_config(
    payload: dict[str, Any],
    _user: User = Depends(get_current_user),
    db=Depends(get_db),
) -> dict[str, Any]:
    config = set_collection_settings(db, payload)
    backfill_scheduler.apply_config(config)
    config["scheduler"] = backfill_scheduler.status()
    return config
