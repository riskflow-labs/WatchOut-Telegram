from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class LoginIn(BaseModel):
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)


class TelegramAccountCreate(BaseModel):
    label: str = Field(..., min_length=1, max_length=120)
    api_id: int
    api_hash: str
    phone: str
    proxy_url: str = ""

    @field_validator("label")
    @classmethod
    def label_required(cls, value: str) -> str:
        label = value.strip()
        if not label:
            raise ValueError("账号名称不能为空")
        return label


class TelegramAccountPatch(BaseModel):
    label: str | None = None
    proxy_url: str | None = None
    is_active: bool | None = None


class TelegramAccountOut(BaseModel):
    id: int
    label: str
    phone: str
    session_name: str
    proxy_url: str
    status: str
    is_active: bool
    last_error: str
    health_status: str = "unchecked"
    health_message: str = ""
    health_me: str = ""
    health_target_count: int = 0
    health_listening_target_count: int = 0
    health_checked_at: datetime | None = None
    proxy_status: str = "unchecked"
    proxy_latency_ms: int | None = None
    proxy_message: str = ""
    proxy_checked_at: datetime | None = None
    authorization_status: str = "created"
    runtime_status: str = "stopped"
    bound_target_count: int = 0
    listening_target_count: int = 0
    last_message_at: datetime | None = None
    last_checked_at: datetime | None = None
    available_actions: list[str] = []
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TelegramAccountHealthOut(BaseModel):
    account_id: int
    status: str
    listening: bool
    authorized: bool
    healthy: bool
    severity: str
    target_count: int
    listening_target_count: int
    proxy_configured: bool
    me: str = ""
    message: str = ""
    last_error: str = ""


class AccountDiagnosisItem(BaseModel):
    key: str
    label: str
    status: str
    duration_ms: int | None = None
    result: str = ""
    suggestion: str = ""


class AccountDiagnosisOut(BaseModel):
    account_id: int
    authorization_status: str
    health_status: str
    proxy_status: str
    runtime_status: str
    checked_at: datetime
    items: list[AccountDiagnosisItem]


class AccountRuntimeEventOut(BaseModel):
    id: int
    event_type: str
    status: str
    summary: str
    detail: str = ""
    created_at: datetime

    class Config:
        from_attributes = True


class AccountBulkIn(BaseModel):
    account_ids: list[int]
    action: str


class AccountBulkItemOut(BaseModel):
    account_id: int
    label: str = ""
    eligible: bool
    status: str
    message: str = ""


class AccountBulkOut(BaseModel):
    action: str
    selected: int
    executable: int
    skipped: int
    succeeded: int
    failed: int
    items: list[AccountBulkItemOut]


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
    target_group: str = ""
    about: str = ""
    enabled: bool = True


class TelegramTargetPatch(BaseModel):
    account_id: int | None = None
    account_id_set: bool = False
    title: str | None = None
    target_group: str | None = None
    enabled: bool | None = None


class TargetParseIn(BaseModel):
    text: str
    account_id: int | None = None
    target_type: str = "auto"
    target_group: str = ""


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
    target_group: str = ""
    participants_count: int | None = None
    about: str = ""
    duplicate_of: int | None = None


class TargetParseOut(BaseModel):
    items: list[TargetParseItem]
    total: int
    raw_total: int | None = None
    importable: int
    duplicated: int
    invalid: int


class BackfillIn(BaseModel):
    limit: int = Field(default=5000, ge=1, le=20000)
    since_days: int | None = Field(default=None, ge=1, le=365)
    since_hours: int | None = Field(default=None, ge=1, le=168)


class TelegramTargetOut(BaseModel):
    id: int
    account_id: int | None
    title: str
    target: str
    normalized_target: str
    target_type: str
    target_group: str = ""
    participants_count: int | None = None
    message_count: int = 0
    about: str = ""
    enabled: bool
    status: str
    last_message_at: datetime | None
    last_run_id: int | None = None
    last_run_at: datetime | None = None
    last_run_records: int = 0
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


class TargetDeleteIn(BaseModel):
    delete_messages: bool = False


class TargetBulkDeleteIn(BaseModel):
    target_ids: list[int]
    delete_messages: bool = False


class DeleteOut(BaseModel):
    deleted: int
    deleted_messages: int = 0
    deleted_hits: int = 0
    deleted_media: int = 0


class TargetImportDialogsIn(BaseModel):
    account_id: int
    target_group: str = ""
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
    target_group: str = ""
    participants_count: int | None = None
    about: str = ""


class TargetCheckOut(BaseModel):
    items: list[TargetCheckItem]
    total: int
    accessible: int
    failed: int


class TargetMetadataSyncItem(BaseModel):
    id: int
    title: str
    status: str
    message: str = ""


class TargetMetadataSyncOut(BaseModel):
    total: int
    updated: int
    failed: int
    items: list[TargetMetadataSyncItem]


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
    notification_channel_ids: list[int] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class RuleOut(RuleCreate):
    id: int
    created_at: datetime
    updated_at: datetime
    hit_count: int = 0
    recent_hit_at: datetime | None = None


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
    delivery_count: int = 0
    delivered_count: int = 0
    failed_count: int = 0
    last_delivery_status: str = ""
    last_delivery_at: datetime | None = None


class NotificationPreviewOut(BaseModel):
    title: str
    text: str
    risk_level: int
    rule_name: str


class NotificationDeliveryOut(BaseModel):
    id: int
    channel_id: int | None
    channel_name: str = ""
    channel_type: str = ""
    message_id: int | None
    message_source: str = ""
    message_source_id: str = ""
    message_tg_id: str = ""
    message_event_time: datetime | None = None
    message_rule: str = ""
    message_risk_level: int = 0
    message_summary: str = ""
    status: str
    attempts: int
    error: str
    created_at: datetime
    delivered_at: datetime | None


class NotificationDeliveryPageOut(BaseModel):
    items: list[NotificationDeliveryOut]
    total: int
    page: int
    page_size: int


class MessageMediaOut(BaseModel):
    id: int
    media_index: int
    media_kind: str
    file_name: str
    mime_type: str
    size: int
    download_status: str
    ocr_status: str
    ocr_engine: str = ""
    ocr_text: str = ""
    error: str = ""
    created_at: datetime
    updated_at: datetime


class MessageOut(BaseModel):
    id: int
    message_uid: str
    channel: str
    account_id: int | None
    target_id: int | None
    target_title: str = ""
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
    language: str = ""
    translated_content: str = ""
    translation_status: str = ""
    translation_engine: str = ""
    translation_target: str = ""
    ocr_text: str = ""
    ocr_status: str = ""
    ocr_engine: str = ""
    content_md5: str
    data_id: str
    similar_id: str
    original_content: str
    desc: str = ""
    category: str
    message_kind: str
    media_type: str
    media_name: str = ""
    raw_name: str = ""
    media_count: int
    media_items: list[MessageMediaOut] = Field(default_factory=list)
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
    message: MessageOut | None = None


class RuleHitPatch(BaseModel):
    status: str


class RuleExcludeAppendIn(BaseModel):
    pattern: str


class RuleReprocessIn(BaseModel):
    rule_id: int | None = None
    limit: int = Field(default=5000, ge=1, le=50000)
    notify_matches: bool = False
    reset_existing: bool = True


class RuleReprocessOut(BaseModel):
    scanned: int
    created: int
    notified: int = 0


class MonitorRunOut(BaseModel):
    id: int
    account_id: int | None
    target_id: int | None
    account_label: str = ""
    target_title: str = ""
    target_ref: str = ""
    mode: str
    status: str
    records_seen: int
    records_written: int
    error: str
    started_at: datetime
    finished_at: datetime | None
    duration_seconds: int | None = None

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
