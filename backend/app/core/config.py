from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    app_name: str = "WatchOut Telegram"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "postgresql+psycopg://watchout:watchout_dev_password@localhost:5432/watchout_telegram"
    session_dir: Path = Path("./data/sessions")
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://0.0.0.0:5173",
        ]
    )
    cors_origin_regex: str | None = r"http://(localhost|127\.0\.0\.1|0\.0\.0\.0|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(1[6-9]|2\d|3[0-1])\.\d{1,3}\.\d{1,3}):5173"
    enable_scheduler: bool = True
    account_health_enabled: bool = True
    account_health_interval_seconds: int = 86400
    account_health_startup_delay_seconds: int = 300
    backfill_enabled: bool = True
    backfill_interval_seconds: int = 10800
    backfill_startup_delay_seconds: int = 120
    backfill_limit_per_target: int = 10000
    backfill_window_hours: int = 4
    live_start_backfill_limit: int = 5000
    live_start_backfill_window_hours: int = 24
    default_admin_username: str = "admin"
    default_admin_password: str = "admin123"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_prefix="WATCHOUT_TELEGRAM_",
        extra="ignore",
    )


settings = Settings()
