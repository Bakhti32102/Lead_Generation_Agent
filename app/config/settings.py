"""
Central configuration module.
Loads settings from .env and provides typed access throughout the application.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project root (one level above this file)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")


def _env(key: str, default: str = "") -> str:
    """Read an environment variable, stripping surrounding whitespace."""
    return os.getenv(key, default).strip()


def _env_int(key: str, default: int = 0) -> int:
    try:
        return int(_env(key, str(default)))
    except (ValueError, TypeError):
        return default


def _env_bool(key: str, default: bool = False) -> bool:
    val = _env(key, str(default)).lower()
    return val in ("true", "1", "yes")


# ---------------------------------------------------------------------------
# Data-path helpers
# ---------------------------------------------------------------------------
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"

DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)


# ---------------------------------------------------------------------------
# Typed configuration dataclasses
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LLMConfig:
    provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "openai"))
    model: str = field(default_factory=lambda: _env("LLM_MODEL", "gpt-4o-mini"))
    api_key: str = field(default_factory=lambda: _env("LLM_API_KEY"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class SearchConfig:
    provider: str = field(default_factory=lambda: _env("SEARCH_PROVIDER", "tavily"))
    api_key: str = field(default_factory=lambda: _env("SEARCH_API_KEY"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class GoogleMapsConfig:
    api_key: str = field(default_factory=lambda: _env("GOOGLE_MAPS_API_KEY"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)


@dataclass(frozen=True)
class GoogleSheetsConfig:
    service_account_json: str = field(
        default_factory=lambda: _env("GOOGLE_SERVICE_ACCOUNT_JSON", "service_account.json")
    )
    sheet_id: str = field(default_factory=lambda: _env("GOOGLE_SHEET_ID"))
    worksheet_name: str = field(default_factory=lambda: _env("GOOGLE_WORKSHEET_NAME", "Leads"))

    @property
    def credentials_path(self) -> Path:
        path = Path(self.service_account_json)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path

    @property
    def is_configured(self) -> bool:
        return bool(self.sheet_id) and self.credentials_path.exists()


@dataclass(frozen=True)
class EmailConfig:
    provider: str = field(default_factory=lambda: _env("EMAIL_PROVIDER", "gmail"))
    api_key: str = field(default_factory=lambda: _env("EMAIL_API_KEY"))
    from_address: str = field(default_factory=lambda: _env("EMAIL_FROM"))

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.from_address)


@dataclass(frozen=True)
class WhatsAppConfig:
    access_token: str = field(default_factory=lambda: _env("WHATSAPP_ACCESS_TOKEN"))
    phone_number_id: str = field(default_factory=lambda: _env("WHATSAPP_PHONE_NUMBER_ID"))
    business_account_id: str = field(default_factory=lambda: _env("WHATSAPP_BUSINESS_ACCOUNT_ID"))

    @property
    def is_configured(self) -> bool:
        return bool(self.access_token) and bool(self.phone_number_id)


@dataclass(frozen=True)
class MyBusinessConfig:
    name: str = field(default_factory=lambda: _env("MY_NAME"))
    description: str = field(default_factory=lambda: _env("MY_BUSINESS_DESCRIPTION"))
    email: str = field(default_factory=lambda: _env("MY_EMAIL"))
    whatsapp_number: str = field(default_factory=lambda: _env("MY_WHATSAPP_NUMBER"))
    website_url: str = field(default_factory=lambda: _env("MY_WEBSITE_URL"))
    fiverr_url: str = field(default_factory=lambda: _env("MY_FIVERR_URL"))
    linkedin_url: str = field(default_factory=lambda: _env("MY_LINKEDIN_URL"))


@dataclass(frozen=True)
class CampaignConfig:
    target_country: str = field(default_factory=lambda: _env("TARGET_COUNTRY"))
    target_city: str = field(default_factory=lambda: _env("TARGET_CITY"))
    target_business_category: str = field(default_factory=lambda: _env("TARGET_BUSINESS_CATEGORY"))
    daily_lead_target: int = field(default_factory=lambda: _env_int("DAILY_LEAD_TARGET", 15))
    lead_score_threshold: int = field(default_factory=lambda: _env_int("LEAD_SCORE_THRESHOLD", 60))
    max_daily_outreach: int = field(default_factory=lambda: _env_int("MAX_DAILY_OUTREACH", 15))
    dry_run: bool = field(default_factory=lambda: _env_bool("DRY_RUN", True))
    review_mode: bool = field(default_factory=lambda: _env_bool("REVIEW_MODE", True))
    scheduler_enabled: bool = field(default_factory=lambda: _env_bool("SCHEDULER_ENABLED", False))
    scheduler_cron_hour: int = field(default_factory=lambda: _env_int("SCHEDULER_CRON_HOUR", 9))
    scheduler_cron_minute: int = field(default_factory=lambda: _env_int("SCHEDULER_CRON_MINUTE", 0))


@dataclass(frozen=True)
class NotificationConfig:
    method: str = field(default_factory=lambda: _env("NOTIFICATION_METHOD", "email"))
    email: str = field(default_factory=lambda: _env("NOTIFICATION_EMAIL"))


# ---------------------------------------------------------------------------
# Aggregated settings
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Settings:
    llm: LLMConfig = field(default_factory=LLMConfig)
    search: SearchConfig = field(default_factory=SearchConfig)
    google_maps: GoogleMapsConfig = field(default_factory=GoogleMapsConfig)
    google_sheets: GoogleSheetsConfig = field(default_factory=GoogleSheetsConfig)
    email: EmailConfig = field(default_factory=EmailConfig)
    whatsapp: WhatsAppConfig = field(default_factory=WhatsAppConfig)
    my_business: MyBusinessConfig = field(default_factory=MyBusinessConfig)
    campaign: CampaignConfig = field(default_factory=CampaignConfig)
    notification: NotificationConfig = field(default_factory=NotificationConfig)
    log_level: str = field(default_factory=lambda: _env("LOG_LEVEL", "INFO"))

    # ---- helpers ----
    def print_status(self) -> str:
        """Return a human-readable configuration status report."""
        rows = [
            ("LLM API", self.llm.is_configured),
            ("Search API", self.search.is_configured),
            ("Google Maps API", self.google_maps.is_configured),
            ("Google Sheets API", self.google_sheets.is_configured),
            ("Email API", self.email.is_configured),
            ("WhatsApp API", self.whatsapp.is_configured),
        ]
        lines = ["",
                 "+------------------------------------------+",
                 "|       Configuration Status               |",
                 "+------------------------------------------+"]
        for label, ok in rows:
            status = "[OK]" if ok else "[NOT CONFIGURED]"
            lines.append(f"|  {label:<20s} {status:>18s} |")
        lines.append("+------------------------------------------+\n")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------
settings = Settings()
