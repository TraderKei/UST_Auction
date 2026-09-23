from __future__ import annotations

from datetime import date
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from UST_* environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="UST_", env_file=".env", extra="ignore", case_sensitive=False
    )

    database_url: str = "postgresql+psycopg://ust_app@localhost:5432/ust_data"
    raw_root: Path = Path("data/raw")
    user_agent: str = "ust-auction-qra-pipeline/0.1 (contact=unset)"
    http_timeout_seconds: float = Field(default=30, gt=0)
    http_max_retries: int = Field(default=4, ge=0, le=10)
    http_backoff_base_seconds: float = Field(default=0.5, ge=0)
    ca_bundle: Path | None = None
    qra_request_delay_seconds: float = Field(default=1.0, ge=0)
    auction_page_size: int = Field(default=1000, ge=1, le=10000)
    auction_overlap_days: int = Field(default=45, ge=1, le=366)
    initial_from_date: date = date(1979, 1, 1)
    initial_to_date: date = date(2099, 12, 31)
    log_level: str = "INFO"

    @field_validator("ca_bundle", mode="before")
    @classmethod
    def empty_ca_bundle(cls, value):
        return value or None

    @field_validator("raw_root", mode="before")
    @classmethod
    def expand_raw_root(cls, value: str | Path) -> Path:
        return Path(value).expanduser()
