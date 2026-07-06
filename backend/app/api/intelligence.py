from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import RuleHit, TelegramMessage, User
from app.services.json_utils import loads_list


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


@router.get("/tg-links")
def tg_link_discovery(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict[str, object]]:
    rows = db.query(TelegramMessage).order_by(TelegramMessage.event_time.desc()).limit(2000).all()
    counter: Counter[str] = Counter()
    examples: dict[str, str] = {}
    for row in rows:
        candidates = list(loads_list(row.links_json))
        candidates.extend(re.findall(r"(?:https?://)?t\.me/[A-Za-z0-9_+/=-]+", row.content or ""))
        for link in candidates:
            text = str(link).strip()
            if "t.me/" not in text:
                continue
            normalized = text if text.startswith("http") else f"https://{text}"
            counter[normalized] += 1
            examples.setdefault(normalized, row.content[:180])
    return [
        {"link": link, "count": count, "example": examples.get(link, "")}
        for link, count in counter.most_common(100)
    ]


@router.post("/ocr/test")
async def test_ocr(
    file: UploadFile = File(...),
    language: str = "eng",
    _user: User = Depends(get_current_user),
) -> dict[str, object]:
    if not shutil.which("tesseract"):
        raise HTTPException(status_code=503, detail="Tesseract OCR is not installed on this machine.")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}:
        suffix = ".png"
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded image is empty.")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Uploaded image is too large; max size is 10MB.")

    started = time.perf_counter()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=True) as image_file:
        image_file.write(content)
        image_file.flush()
        command = ["tesseract", image_file.name, "stdout", "-l", language, "--psm", "6"]
        result = subprocess.run(command, capture_output=True, text=True, timeout=30, check=False)
    elapsed_ms = round((time.perf_counter() - started) * 1000)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=(result.stderr or "OCR failed").strip())
    text = result.stdout.strip()
    return {
        "engine": "tesseract",
        "language": language,
        "elapsed_ms": elapsed_ms,
        "text": text,
        "chars": len(text),
    }


@router.get("/group-graph")
def group_graph(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, list[dict[str, object]]]:
    rows = db.query(TelegramMessage).order_by(TelegramMessage.event_time.desc()).limit(3000).all()
    nodes: Counter[str] = Counter()
    edges: Counter[tuple[str, str]] = Counter()
    for row in rows:
        nodes[row.source] += 1
        links = re.findall(r"(?:https?://)?t\.me/([A-Za-z0-9_+/-]+)", row.content or "")
        for link in links:
            target = link.strip("/")
            if target and target != row.source:
                nodes[target] += 1
                edges[(row.source, target)] += 1
    return {
        "nodes": [{"id": key, "weight": value} for key, value in nodes.most_common(200)],
        "edges": [
            {"source": source, "target": target, "weight": weight}
            for (source, target), weight in edges.most_common(300)
        ],
    }


@router.get("/risk-summary")
def risk_summary(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    messages = db.query(TelegramMessage).filter(TelegramMessage.event_time >= since).all()
    hits = db.query(RuleHit).filter(RuleHit.created_at >= since).all()
    by_source: defaultdict[str, int] = defaultdict(int)
    top_terms: Counter[str] = Counter()
    for message in messages:
        if message.risk_level > 0:
            by_source[message.source] += 1
            for word in re.findall(r"[A-Za-z0-9_]{4,}|[\u4e00-\u9fff]{2,}", message.content or ""):
                top_terms[word.lower()] += 1
    return {
        "window": "24h",
        "messages": len(messages),
        "hits": len(hits),
        "high_risk_messages": sum(1 for item in messages if item.risk_level >= 2),
        "top_sources": [
            {"source": source, "matched_messages": count}
            for source, count in sorted(by_source.items(), key=lambda item: item[1], reverse=True)[:20]
        ],
        "top_terms": [
            {"term": term, "count": count}
            for term, count in top_terms.most_common(30)
        ],
        "summary": _summary_text(len(messages), len(hits), by_source),
    }


@router.get("/daily-report")
def daily_report(
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    payload = risk_summary(_user=_user, db=db)
    return {
        "title": "WatchOut Telegram 日报",
        "generated_at": datetime.now(timezone.utc),
        "sections": [
            {"heading": "总体情况", "body": payload["summary"]},
            {"heading": "规则匹配来源", "rows": payload["top_sources"]},
            {"heading": "高频词", "rows": payload["top_terms"]},
        ],
        "ai_summary_status": "local_heuristic",
        "ai_summary_note": "第三阶段可接入 OpenAI 或本地模型生成更自然的摘要。",
    }


def _summary_text(messages: int, hits: int, by_source: dict[str, int]) -> str:
    if not messages:
        return "最近 24 小时暂无 Telegram 消息入库。"
    top = sorted(by_source.items(), key=lambda item: item[1], reverse=True)[:3]
    top_text = "、".join(f"{source}({count})" for source, count in top) if top else "暂无明显匹配来源"
    return f"最近 24 小时归档 {messages} 条消息，规则匹配 {hits} 次。主要匹配来源：{top_text}。"
