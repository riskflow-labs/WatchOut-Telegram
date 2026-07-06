from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import AppSetting
from app.services.json_utils import loads_dict


SETTING_KEY = "collection_settings"


def _default_settings() -> dict[str, Any]:
    return {
        "auto_backfill_on_import": True,
        "auto_start_listening_on_import": True,
        "initial_backfill_limit": settings.live_start_backfill_limit,
        "initial_backfill_window_hours": settings.live_start_backfill_window_hours,
        "backfill_enabled": settings.backfill_enabled,
        "backfill_interval_seconds": 900,
        "backfill_limit_per_target": settings.backfill_limit_per_target,
        "backfill_window_hours": settings.backfill_window_hours,
        "max_concurrent_initial_jobs": 3,
        "max_initial_jobs_per_account": 1,
        "max_targets_per_account": 80,
    }


def get_collection_settings(db: Session) -> dict[str, Any]:
    merged = _default_settings()
    row = db.get(AppSetting, SETTING_KEY)
    if row:
        saved = loads_dict(row.value)
        merged.update(saved)
    return _normalized(merged)


def set_collection_settings(db: Session, incoming: dict[str, Any]) -> dict[str, Any]:
    merged = _default_settings()
    merged.update(incoming or {})
    normalized = _normalized(merged)
    value = json.dumps(normalized, ensure_ascii=False)
    row = db.get(AppSetting, SETTING_KEY)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=SETTING_KEY, value=value))
    db.commit()
    return normalized


def _normalized(config: dict[str, Any]) -> dict[str, Any]:
    return {
        "auto_backfill_on_import": bool(config.get("auto_backfill_on_import", True)),
        "auto_start_listening_on_import": bool(config.get("auto_start_listening_on_import", True)),
        "initial_backfill_limit": _int_range(config.get("initial_backfill_limit"), 0, 20000, settings.live_start_backfill_limit),
        "initial_backfill_window_hours": _int_range(
            config.get("initial_backfill_window_hours"),
            1,
            168,
            settings.live_start_backfill_window_hours,
        ),
        "backfill_enabled": bool(config.get("backfill_enabled", settings.backfill_enabled)),
        "backfill_interval_seconds": _int_range(config.get("backfill_interval_seconds"), 60, 86400, 900),
        "backfill_limit_per_target": _int_range(
            config.get("backfill_limit_per_target"),
            1,
            20000,
            settings.backfill_limit_per_target,
        ),
        "backfill_window_hours": _int_range(config.get("backfill_window_hours"), 1, 168, settings.backfill_window_hours),
        "max_concurrent_initial_jobs": _int_range(config.get("max_concurrent_initial_jobs"), 1, 20, 3),
        "max_initial_jobs_per_account": _int_range(config.get("max_initial_jobs_per_account"), 1, 5, 1),
        "max_targets_per_account": _int_range(config.get("max_targets_per_account"), 0, 10000, 80),
    }


def _int_range(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
