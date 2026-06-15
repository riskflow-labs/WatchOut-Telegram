from __future__ import annotations

import hashlib

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.database import Base, engine
from app.core.config import settings
from app.core.security import hash_password
from app.models import MonitorRule, MonitorRun, TelegramMessage, TelegramTarget, User
from app.services.json_utils import dumps


def init_database() -> None:
    Base.metadata.create_all(bind=engine)
    _migrate_sqlite_schema()
    _backfill_message_hashes()
    _ensure_sqlite_indexes()
    _reset_stale_runtime_state()


def seed_defaults(db: Session) -> None:
    if not db.query(User).filter(User.username == settings.default_admin_username).first():
        db.add(
            User(
                username=settings.default_admin_username,
                password_hash=hash_password(settings.default_admin_password),
            )
        )
    if not db.query(MonitorRule).first():
        db.add(
            MonitorRule(
                name="链接与脚本关键词",
                match_type="contains",
                patterns_json=dumps(["http", "https", "t.me", "bot", "script", "脚本", "验证码", "账号"]),
                risk_level=1,
                priority=10,
                enabled=True,
                notify=True,
                tags_json=dumps(["keyword", "link"]),
            )
        )
    db.commit()


def _migrate_sqlite_schema() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    inspector = inspect(engine)
    if "telegram_messages" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("telegram_messages")}
    columns = {
        "message_uid": "VARCHAR(32) DEFAULT ''",
        "channel": "VARCHAR(40) DEFAULT 'tg'",
        "source_type": "VARCHAR(40) DEFAULT 'unknown'",
        "sub_channel": "VARCHAR(80) DEFAULT ''",
        "insert_time": "DATETIME",
        "content_md5": "VARCHAR(32) DEFAULT ''",
        "data_id": "VARCHAR(32) DEFAULT ''",
        "similar_id": "VARCHAR(32) DEFAULT ''",
        "original_content": "TEXT DEFAULT ''",
        "desc": "TEXT DEFAULT ''",
        "category": "VARCHAR(80) DEFAULT '开源'",
        "media_count": "INTEGER DEFAULT 0",
        "hit": "INTEGER DEFAULT 0",
        "keyword_type": "VARCHAR(120) DEFAULT ''",
        "keyword_source": "VARCHAR(255) DEFAULT ''",
        "views_count": "INTEGER DEFAULT 0",
        "replies_count": "INTEGER DEFAULT 0",
        "forwards_count": "INTEGER DEFAULT 0",
    }
    with engine.begin() as connection:
        for name, ddl in columns.items():
            if name not in existing:
                connection.execute(text(f"ALTER TABLE telegram_messages ADD COLUMN {name} {ddl}"))


def _backfill_message_hashes() -> None:
    while True:
        db = Session(bind=engine)
        try:
            rows = (
                db.query(TelegramMessage)
                .filter(
                    (TelegramMessage.message_uid == "")
                    | (TelegramMessage.content_md5 == "")
                    | (TelegramMessage.data_id == "")
                    | (TelegramMessage.similar_id == "")
                    | (TelegramMessage.insert_time.is_(None))
                )
                .limit(5000)
                .all()
            )
            if not rows:
                return
            for row in rows:
                content = row.content or ""
                content_md5 = hashlib.md5(content.encode("utf-8")).hexdigest()
                message_uid = hashlib.md5(f"tg:{row.source_id}:{row.message_id}".encode("utf-8")).hexdigest()
                row.message_uid = row.message_uid or message_uid
                row.channel = row.channel or "tg"
                row.content_md5 = row.content_md5 or content_md5
                row.data_id = row.data_id or content_md5
                row.similar_id = row.similar_id or content_md5
                row.original_content = row.original_content or content
                row.insert_time = row.insert_time or row.created_at
            db.commit()
        finally:
            db.close()


def _ensure_sqlite_indexes() -> None:
    if not settings.database_url.startswith("sqlite"):
        return
    with engine.begin() as connection:
        connection.execute(
            text("CREATE UNIQUE INDEX IF NOT EXISTS ix_telegram_messages_message_uid_unique ON telegram_messages(message_uid)")
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_telegram_messages_content_md5 ON telegram_messages(content_md5)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_telegram_messages_data_id ON telegram_messages(data_id)"))


def _reset_stale_runtime_state() -> None:
    db = Session(bind=engine)
    try:
        db.query(TelegramTarget).filter(TelegramTarget.status == "listening").update(
            {TelegramTarget.status: "idle"},
            synchronize_session=False,
        )
        db.query(MonitorRun).filter(MonitorRun.status == "running", MonitorRun.mode == "live").update(
            {MonitorRun.status: "stopped"},
            synchronize_session=False,
        )
        db.commit()
    finally:
        db.close()
