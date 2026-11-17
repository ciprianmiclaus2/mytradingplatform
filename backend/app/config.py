"""Central application configuration.

All settings can be overridden through environment variables (or a ``.env``
file in the backend directory). Relative ``DATA_DIR`` values are resolved
against the project root so the data location does not depend on the
directory the backend is started from.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent


class AppEnv(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: AppEnv = AppEnv.DEVELOPMENT
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)

    data_dir: Path = Path("~/mytradingplatform/data")

    market_data_provider: str = "yfinance"
    market_data_timeout: float = Field(default=30, gt=0)
    current_price_archive_threshold: int = Field(default=100_000, gt=0)
    backup_retention_count: int = Field(default=10, ge=1)
    backup_on_startup: bool = True
    persistence_lock_timeout: float = Field(default=10, gt=0)

    snaptrade_base_url: str = "https://api.snaptrade.com"
    snaptrade_timeout: float = Field(default=30, gt=0)

    # Origins allowed to call the API directly (the Vite dev server by default).
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    log_level: str = "INFO"

    @field_validator("data_dir", mode="after")
    @classmethod
    def _resolve_data_dir(cls, value: Path) -> Path:
        path = value.expanduser()
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path.resolve()

    @field_validator("market_data_provider", mode="after")
    @classmethod
    def _normalise_provider(cls, value: str) -> str:
        return value.strip().lower()


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""
    return Settings()
