from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TelegramAccount(Base):
    __tablename__ = "telegram_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    api_id: Mapped[int] = mapped_column(Integer)
    api_hash: Mapped[str] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(64), index=True)
    session_name: Mapped[str] = mapped_column(String(160), unique=True)
    proxy_url: Mapped[str] = mapped_column(String(500), default="")
    status: Mapped[str] = mapped_column(String(40), default="created")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    targets: Mapped[list["TelegramTarget"]] = relationship(back_populates="account")


class TelegramLoginFlow(Base):
    __tablename__ = "telegram_login_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("telegram_accounts.id"), index=True)
    phone_code_hash: Mapped[str] = mapped_column(String(255), default="")
    status: Mapped[str] = mapped_column(String(40), default="pending_code")
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TelegramTarget(Base):
    __tablename__ = "telegram_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_accounts.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    target: Mapped[str] = mapped_column(String(500), index=True)
    normalized_target: Mapped[str] = mapped_column(String(255), index=True)
    target_type: Mapped[str] = mapped_column(String(40), default="group")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(40), default="idle")
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    account: Mapped[TelegramAccount | None] = relationship(back_populates="targets")


class MonitorRule(Base):
    __tablename__ = "monitor_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    match_type: Mapped[str] = mapped_column(String(40), default="contains")
    patterns_json: Mapped[str] = mapped_column(Text, default="[]")
    exclude_patterns_json: Mapped[str] = mapped_column(Text, default="[]")
    target_filter_json: Mapped[str] = mapped_column(Text, default="[]")
    sender_filter_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_level: Mapped[int] = mapped_column(Integer, default=1)
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    notify: Mapped[bool] = mapped_column(Boolean, default=True)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"
    __table_args__ = (
        UniqueConstraint("source_id", "message_id", name="uq_tg_message"),
        UniqueConstraint("message_uid", name="uq_tg_message_uid"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_uid: Mapped[str] = mapped_column(String(32), default="", index=True)
    channel: Mapped[str] = mapped_column(String(40), default="tg", index=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_accounts.id"), nullable=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_targets.id"), nullable=True)
    source: Mapped[str] = mapped_column(String(255), index=True)
    source_id: Mapped[str] = mapped_column(String(80), index=True)
    source_type: Mapped[str] = mapped_column(String(40), default="unknown")
    sub_channel: Mapped[str] = mapped_column(String(80), default="")
    message_id: Mapped[str] = mapped_column(String(80), index=True)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    insert_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sender_id: Mapped[str] = mapped_column(String(80), default="")
    sender_username: Mapped[str] = mapped_column(String(160), default="")
    sender_name: Mapped[str] = mapped_column(String(255), default="")
    content: Mapped[str] = mapped_column(Text, default="")
    content_md5: Mapped[str] = mapped_column(String(32), default="", index=True)
    data_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    similar_id: Mapped[str] = mapped_column(String(32), default="", index=True)
    original_content: Mapped[str] = mapped_column(Text, default="")
    desc: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(80), default="开源")
    message_kind: Mapped[str] = mapped_column(String(40), default="text")
    media_type: Mapped[str] = mapped_column(String(120), default="")
    media_count: Mapped[int] = mapped_column(Integer, default=0)
    links_json: Mapped[str] = mapped_column(Text, default="[]")
    raw_payload: Mapped[str] = mapped_column(Text, default="{}")
    risk_level: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    hit: Mapped[int] = mapped_column(Integer, default=0)
    keyword_type: Mapped[str] = mapped_column(String(120), default="")
    keyword_source: Mapped[str] = mapped_column(String(255), default="")
    views_count: Mapped[int] = mapped_column(Integer, default=0)
    replies_count: Mapped[int] = mapped_column(Integer, default=0)
    forwards_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="new")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    hits: Mapped[list["RuleHit"]] = relationship(back_populates="message")


class CrawlError(Base):
    __tablename__ = "crawl_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_accounts.id"), nullable=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_targets.id"), nullable=True)
    message_id: Mapped[str] = mapped_column(String(80), default="")
    stage: Mapped[str] = mapped_column(String(80), default="")
    error_type: Mapped[str] = mapped_column(String(160), default="")
    error_message: Mapped[str] = mapped_column(Text, default="")
    retryable: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RuleHit(Base):
    __tablename__ = "rule_hits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("telegram_messages.id"), index=True)
    rule_id: Mapped[int | None] = mapped_column(ForeignKey("monitor_rules.id"), nullable=True)
    rule_name: Mapped[str] = mapped_column(String(160), default="")
    matched_patterns_json: Mapped[str] = mapped_column(Text, default="[]")
    risk_level: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="open")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    message: Mapped[TelegramMessage] = relationship(back_populates="hits")


class NotificationChannel(Base):
    __tablename__ = "notification_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    type: Mapped[str] = mapped_column(String(40), default="telegram_bot")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    min_risk_level: Mapped[int] = mapped_column(Integer, default=2)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int | None] = mapped_column(ForeignKey("notification_channels.id"), nullable=True)
    message_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_messages.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MonitorRun(Base):
    __tablename__ = "monitor_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_accounts.id"), nullable=True)
    target_id: Mapped[int | None] = mapped_column(ForeignKey("telegram_targets.id"), nullable=True)
    mode: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(40), default="running")
    records_seen: Mapped[int] = mapped_column(Integer, default=0)
    records_written: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(160), primary_key=True)
    value: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
