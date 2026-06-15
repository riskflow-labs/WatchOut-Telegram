from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import socks


def normalize_target(target: str) -> str:
    target = target.strip()
    if target.startswith("@"):
        return target[1:]
    parsed = urlparse(target)
    if parsed.netloc.endswith("t.me"):
        return parsed.path.strip("/")
    return target.strip("/")


def parse_proxy(proxy_url: str | None) -> tuple[Any, ...] | None:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    proxy_type = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }.get(parsed.scheme.lower())
    if proxy_type is None or not parsed.hostname or not parsed.port:
        raise ValueError("Unsupported or incomplete proxy URL")
    return (proxy_type, parsed.hostname, parsed.port, True, parsed.username, parsed.password)


def session_path(session_dir: Path, session_name: str) -> str:
    session_dir.mkdir(parents=True, exist_ok=True)
    return str(session_dir / session_name)


def extract_links(text: str) -> list[str]:
    return re.findall(r"https?://[^\s<>)\"']+", text or "")


def stable_md5(*parts: Any) -> str:
    raw = "|".join("" if part is None else str(part) for part in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def sender_name(sender: Any) -> str:
    if sender is None:
        return ""
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    return " ".join(item for item in [first, last] if item).strip()


def raw_payload(message: Any) -> str:
    try:
        payload = message.to_dict()
    except Exception:
        payload = {"repr": repr(message)}
    return json.dumps(json_safe(payload), ensure_ascii=False, separators=(",", ":"))
