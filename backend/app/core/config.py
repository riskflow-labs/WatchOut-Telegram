from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "WatchOut Telegram"
    secret_key: str = "change-me-in-production"
    access_token_expire_minutes: int = 60 * 24
    database_url: str = "sqlite:///./data/app.db"
    session_dir: Path = Path("./data/sessions")
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173", "http://127.0.0.1:5173"]
    )
    enable_scheduler: bool = True
    backfill_enabled: bool = True
    backfill_interval_seconds: int = 1800
    backfill_startup_delay_seconds: int = 120
    backfill_limit_per_target: int = 50
    default_admin_username: str = "admin"
    default_admin_password: str = "change-me-before-first-run"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WATCHOUT_TELEGRAM_",
        extra="ignore",
    )


settings = Settings()
