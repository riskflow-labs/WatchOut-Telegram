from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    username: str
    password: str


class TelegramAccountCreate(BaseModel):
    label: str = ""
    api_id: int
    api_hash: str
    phone: str
    proxy_url: str = ""


class TelegramAccountOut(BaseModel):
    id: int
    label: str
    phone: str
    session_name: str
    proxy_url: str
    status: str
    is_active: bool
    last_error: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class VerifyCodeIn(BaseModel):
    code: str


class VerifyPasswordIn(BaseModel):
    password: str


class TelegramDialogOut(BaseModel):
    account_id: int
    title: str
    target: str
    normalized_target: str
    target_type: str
    dialog_type: str
    username: str
    chat_id: str
    participants_count: int | None = None
    last_message_at: datetime | None = None
    status: str = "ready"
    reason: str = ""


class TelegramTargetCreate(BaseModel):
    account_id: int | None = None
    title: str = ""
    target: str
    target_type: str = "group"
    enabled: bool = True


class TelegramTargetPatch(BaseModel):
    account_id: int | None = None
    title: str | None = None
    enabled: bool | None = None


class TargetParseIn(BaseModel):
    text: str
    account_id: int | None = None
    target_type: str = "auto"


class TargetParseItem(BaseModel):
    line: int
    raw: str
    status: str
    reason: str = ""
    detected_type: str = "unknown"
    target_type: str = "group"
    target: str = ""
    normalized_target: str = ""
    title: str = ""
    account_id: int | None = None
    duplicate_of: int | None = None


class TargetParseOut(BaseModel):
    items: list[TargetParseItem]
    total: int
    importable: int
    duplicated: int
    invalid: int


class BackfillIn(BaseModel):
    limit: int = Field(default=5000, ge=1, le=20000)
    since_days: int | None = Field(default=None, ge=1, le=365)


class TelegramTargetOut(BaseModel):
    id: int
    account_id: int | None
    title: str
    target: str
    normalized_target: str
    target_type: str
    enabled: bool
    status: str
    last_message_at: datetime | None
    last_error: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TargetBulkCreateIn(BaseModel):
    items: list[TargetParseItem]


class TargetBulkCreateOut(BaseModel):
    created: list[TelegramTargetOut]
    skipped: list[TargetParseItem]
    created_count: int
    skipped_count: int


class TargetImportDialogsIn(BaseModel):
    account_id: int
    dialogs: list[TelegramDialogOut]


class TargetCheckIn(BaseModel):
    items: list[TargetParseItem]
    account_id: int | None = None
    auto_join_invites: bool = False


class TargetCheckItem(BaseModel):
    line: int
    raw: str
    target: str
    normalized_target: str
    status: str
    category: str = ""
    reason: str = ""
    title: str = ""
    target_type: str = "group"


class TargetCheckOut(BaseModel):
    items: list[TargetCheckItem]
    total: int
    accessible: int
    failed: int


class RuleCreate(BaseModel):
    name: str
    match_type: str = "contains"
    patterns: list[str] = Field(default_factory=list)
    exclude_patterns: list[str] = Field(default_factory=list)
    target_filter: list[str] = Field(default_factory=list)
    sender_filter: list[str] = Field(default_factory=list)
    risk_level: int = 1
    priority: int = 100
    enabled: bool = True
    notify: bool = True
    tags: list[str] = Field(default_factory=list)


class RuleOut(RuleCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class NotificationChannelCreate(BaseModel):
    name: str
    type: str = "telegram_bot"
    enabled: bool = True
    min_risk_level: int = 2
    config: dict[str, Any] = Field(default_factory=dict)


class NotificationChannelOut(NotificationChannelCreate):
    id: int
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    message_uid: str
    channel: str
    account_id: int | None
    target_id: int | None
    source: str
    source_id: str
    source_type: str
    sub_channel: str
    message_id: str
    event_time: datetime
    insert_time: datetime
    sender_id: str
    sender_username: str
    sender_name: str
    content: str
    content_md5: str
    data_id: str
    similar_id: str
    original_content: str
    category: str
    message_kind: str
    media_type: str
    media_count: int
    links: list[str]
    views_count: int
    replies_count: int
    forwards_count: int
    risk_level: int
    score: int
    hit: int
    keyword_type: str
    keyword_source: str
    status: str
    created_at: datetime


class RuleHitOut(BaseModel):
    id: int
    message_id: int
    rule_id: int | None
    rule_name: str
    matched_patterns: list[str]
    risk_level: int
    status: str
    created_at: datetime


class MonitorRunOut(BaseModel):
    id: int
    account_id: int | None
    target_id: int | None
    mode: str
    status: str
    records_seen: int
    records_written: int
    error: str
    started_at: datetime
    finished_at: datetime | None

    class Config:
        from_attributes = True


class CrawlErrorOut(BaseModel):
    id: int
    account_id: int | None
    target_id: int | None
    message_id: str
    stage: str
    error_type: str
    error_message: str
    retryable: bool
    created_at: datetime

    class Config:
        from_attributes = True


class DashboardOut(BaseModel):
    accounts: int
    active_accounts: int
    targets: int
    enabled_targets: int
    messages: int
    hits: int
    open_hits: int
    runs: int
