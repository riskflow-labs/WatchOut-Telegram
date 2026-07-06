from __future__ import annotations

import json
import os
from typing import Any

from sqlalchemy.orm import Session

from app.models import AppSetting
from app.services.json_utils import loads_dict


DEFAULT_INTELLIGENCE_SETTINGS = {
    "platform_language": "zh-CN",
    "translation": {
        "enabled": False,
        "engine": "tencent",
        "baidu_app_id": os.getenv("WATCHOUT_TELEGRAM_BAIDU_APP_ID", ""),
        "baidu_secret_key": os.getenv("WATCHOUT_TELEGRAM_BAIDU_SECRET_KEY", ""),
        "tencent_secret_id": os.getenv("WATCHOUT_TELEGRAM_TENCENT_SECRET_ID", ""),
        "tencent_secret_key": os.getenv("WATCHOUT_TELEGRAM_TENCENT_SECRET_KEY", ""),
        "tencent_region": os.getenv("WATCHOUT_TELEGRAM_TENCENT_TRANSLATE_REGION", "ap-guangzhou"),
        "target_language": "auto",
        "skip_language_prefixes": ["zh"],
        "min_chars": 20,
    },
    "ocr": {
        "enabled": False,
        "engine": "paddleocr",
        "max_image_mb": 5,
        "delete_after_ocr": True,
        "include_in_search": True,
        "include_in_rules": True,
    },
    "summary": {
        "enabled": False,
        "mode": "structured",
        "min_chars": 600,
    },
}


def _env_any(*names: str, default: str = "") -> str:
    for name in names:
        value = os.getenv(name)
        if value is not None and str(value).strip():
            return str(value).strip()
    return default


DEFAULT_INTELLIGENCE_SETTINGS["translation"].update(
    {
        "baidu_app_id": _env_any("WATCHOUT_TELEGRAM_BAIDU_APP_ID", "BAIDU_APP_ID"),
        "baidu_secret_key": _env_any("WATCHOUT_TELEGRAM_BAIDU_SECRET_KEY", "BAIDU_SECRET_KEY"),
        "tencent_secret_id": _env_any("WATCHOUT_TELEGRAM_TENCENT_SECRET_ID", "TENCENT_SECRET_ID"),
        "tencent_secret_key": _env_any("WATCHOUT_TELEGRAM_TENCENT_SECRET_KEY", "TENCENT_SECRET_KEY"),
        "tencent_region": _env_any("WATCHOUT_TELEGRAM_TENCENT_TRANSLATE_REGION", "TENCENT_TRANSLATE_REGION", default="ap-guangzhou"),
    }
)


def effective_translation_target(settings: dict[str, Any]) -> str:
    translation = settings.get("translation") or {}
    target = str(translation.get("target_language") or "auto")
    if target != "auto":
        return target
    platform_language = str(settings.get("platform_language") or "zh-CN").lower()
    if platform_language.startswith("zh"):
        return "zh"
    if platform_language.startswith("en"):
        return "en"
    if platform_language.startswith("ja"):
        return "ja"
    if platform_language.startswith("ko"):
        return "ko"
    return platform_language.split("-")[0] or "zh"


def get_intelligence_settings(db: Session) -> dict[str, Any]:
    row = db.get(AppSetting, "intelligence_settings")
    merged = json.loads(json.dumps(DEFAULT_INTELLIGENCE_SETTINGS))
    if not row:
        _normalize_settings(merged)
        return merged
    saved = loads_dict(row.value)
    _deep_update(merged, saved)
    _normalize_settings(merged)
    return merged


def set_intelligence_settings(db: Session, settings: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_INTELLIGENCE_SETTINGS))
    _deep_update(merged, settings)
    _normalize_settings(merged)
    row = db.get(AppSetting, "intelligence_settings")
    value = json.dumps(merged, ensure_ascii=False)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key="intelligence_settings", value=value))
    db.commit()
    return merged


def _deep_update(base: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value


def _normalize_settings(settings: dict[str, Any]) -> None:
    translation = settings.get("translation")
    if not isinstance(translation, dict):
        settings["translation"] = json.loads(json.dumps(DEFAULT_INTELLIGENCE_SETTINGS["translation"]))
        return
    baidu_app_id = _env_any("WATCHOUT_TELEGRAM_BAIDU_APP_ID", "BAIDU_APP_ID")
    baidu_secret_key = _env_any("WATCHOUT_TELEGRAM_BAIDU_SECRET_KEY", "BAIDU_SECRET_KEY")
    tencent_secret_id = _env_any("WATCHOUT_TELEGRAM_TENCENT_SECRET_ID", "TENCENT_SECRET_ID")
    tencent_secret_key = _env_any("WATCHOUT_TELEGRAM_TENCENT_SECRET_KEY", "TENCENT_SECRET_KEY")
    tencent_region = _env_any("WATCHOUT_TELEGRAM_TENCENT_TRANSLATE_REGION", "TENCENT_TRANSLATE_REGION", default="ap-guangzhou")
    if not str(translation.get("baidu_app_id") or "").strip():
        translation["baidu_app_id"] = baidu_app_id
    if not str(translation.get("baidu_secret_key") or "").strip():
        translation["baidu_secret_key"] = baidu_secret_key
    if not str(translation.get("tencent_secret_id") or "").strip():
        translation["tencent_secret_id"] = tencent_secret_id
    if not str(translation.get("tencent_secret_key") or "").strip():
        translation["tencent_secret_key"] = tencent_secret_key
    if not str(translation.get("tencent_region") or "").strip():
        translation["tencent_region"] = tencent_region
    engine = _translation_engine(translation.get("engine"))
    if engine not in {"baidu", "tencent"}:
        translation["engine"] = "tencent" if tencent_secret_id and tencent_secret_key else "baidu"
    elif engine == "baidu" and tencent_secret_id and tencent_secret_key and not baidu_app_id and not baidu_secret_key:
        translation["engine"] = "tencent"
    else:
        translation["engine"] = engine


def _translation_engine(value: object) -> str:
    normalized = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "baidu": "baidu",
        "baidu_cloud": "baidu",
        "baidu_translate": "baidu",
        "baidu_translation": "baidu",
        "百度": "baidu",
        "百度云": "baidu",
        "百度云翻译": "baidu",
        "tencent": "tencent",
        "tencent_cloud": "tencent",
        "tencent_translate": "tencent",
        "tmt": "tencent",
        "腾讯": "tencent",
        "腾讯云": "tencent",
        "腾讯云机器翻译": "tencent",
    }
    return aliases.get(normalized, normalized)
