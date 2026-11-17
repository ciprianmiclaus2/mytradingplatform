from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fake_snaptrade import FakeSnapTrade
from tests.fakes import FakeProvider

_ENV_VARS = (
    "APP_ENV",
    "APP_HOST",
    "APP_PORT",
    "DATA_DIR",
    "MARKET_DATA_PROVIDER",
    "MARKET_DATA_TIMEOUT",
    "CURRENT_PRICE_ARCHIVE_THRESHOLD",
    "BACKUP_RETENTION_COUNT",
    "CORS_ORIGINS",
    "LOG_LEVEL",
    "SNAPTRADE_BASE_URL",
    "SNAPTRADE_TIMEOUT",
)


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's shell environment out of the tests."""
    for name in _ENV_VARS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def data_dir(tmp_path: Path) -> Path:
    return tmp_path / "data"


@pytest.fixture
def settings(data_dir: Path) -> Settings:
    return Settings(_env_file=None, app_env="test", data_dir=data_dir)


@pytest.fixture
def fake_provider() -> FakeProvider:
    return FakeProvider()


@pytest.fixture
def fake_snaptrade() -> FakeSnapTrade:
    return FakeSnapTrade()


@pytest.fixture
def client(settings: Settings, fake_provider: FakeProvider, fake_snaptrade: FakeSnapTrade) -> Iterator[TestClient]:
    app = create_app(settings, provider=fake_provider, snaptrade=fake_snaptrade.factory)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
