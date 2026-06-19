from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    database_url: str | None
    base_url: str
    host: str
    port: int
    log_level: str

    poll_interval_minutes: int
    http_timeout_seconds: int

    smtp_host: str | None
    smtp_port: int
    smtp_username: str | None
    smtp_password: str | None
    smtp_from_email: str | None
    smtp_from_name: str
    smtp_use_ssl: bool
    smtp_starttls: bool

    @property
    def email_configured(self) -> bool:
        return bool(self.smtp_host and self.smtp_from_email)

    @property
    def db_configured(self) -> bool:
        return bool(self.database_url)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings(
        database_url=os.getenv("DATABASE_URL") or None,
        base_url=(os.getenv("BASE_URL") or "http://localhost:8000").rstrip("/"),
        host=os.getenv("HOST") or "0.0.0.0",
        port=_get_int("PORT", 8000),
        log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
        poll_interval_minutes=max(1, _get_int("POLL_INTERVAL_MINUTES", 5)),
        http_timeout_seconds=max(5, _get_int("HTTP_TIMEOUT_SECONDS", 20)),
        smtp_host=os.getenv("SMTP_HOST") or None,
        smtp_port=_get_int("SMTP_PORT", 587),
        smtp_username=os.getenv("SMTP_USERNAME") or None,
        smtp_password=os.getenv("SMTP_PASSWORD") or None,
        smtp_from_email=os.getenv("SMTP_FROM_EMAIL") or os.getenv("SMTP_USERNAME") or None,
        smtp_from_name=os.getenv("SMTP_FROM_NAME") or "CUNY Tracker",
        smtp_use_ssl=_get_bool("SMTP_USE_SSL", False),
        smtp_starttls=_get_bool("SMTP_STARTTLS", True),
    )
