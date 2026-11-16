from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.config import PROJECT_ROOT, AppEnv, Settings


def test_defaults() -> None:
    s = Settings(_env_file=None)
    assert s.app_env is AppEnv.DEVELOPMENT
    assert s.app_host == "127.0.0.1"
    assert s.app_port == 8000
    assert s.data_dir == (Path.home() / "mytradingplatform" / "data").resolve()
    assert s.market_data_provider == "yfinance"
    assert s.market_data_timeout == 30
    assert s.current_price_archive_threshold == 100_000
    assert s.backup_retention_count == 10


def test_environment_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_HOST", "0.0.0.0")
    monkeypatch.setenv("APP_PORT", "9001")
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "custom"))
    monkeypatch.setenv("MARKET_DATA_PROVIDER", " YFinance ")
    monkeypatch.setenv("MARKET_DATA_TIMEOUT", "5.5")
    monkeypatch.setenv("CURRENT_PRICE_ARCHIVE_THRESHOLD", "500")
    monkeypatch.setenv("BACKUP_RETENTION_COUNT", "3")

    s = Settings(_env_file=None)

    assert s.app_env is AppEnv.PRODUCTION
    assert s.app_host == "0.0.0.0"
    assert s.app_port == 9001
    assert s.data_dir == (tmp_path / "custom").resolve()
    assert s.market_data_provider == "yfinance"
    assert s.market_data_timeout == 5.5
    assert s.current_price_archive_threshold == 500
    assert s.backup_retention_count == 3


def test_relative_data_dir_resolves_against_project_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "./data")
    assert Settings(_env_file=None).data_dir == (PROJECT_ROOT / "data").resolve()


def test_tilde_data_dir_expands_to_home(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATA_DIR", "~/somewhere")
    assert Settings(_env_file=None).data_dir == (Path.home() / "somewhere").resolve()


@pytest.mark.parametrize(
    ("var", "value"),
    [
        ("APP_PORT", "0"),
        ("APP_PORT", "not-a-number"),
        ("APP_ENV", "staging"),
        ("MARKET_DATA_TIMEOUT", "0"),
        ("BACKUP_RETENTION_COUNT", "0"),
    ],
)
def test_invalid_values_rejected(monkeypatch: pytest.MonkeyPatch, var: str, value: str) -> None:
    monkeypatch.setenv(var, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
