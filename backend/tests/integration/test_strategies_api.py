from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.strategies.registry import StrategyRegistry
from tests.fakes import FakeProvider
from tests.strategy_fixtures import BrokenStrategy, LevelStrategy


@pytest.fixture
def api(settings: Settings, fake_provider: FakeProvider) -> Iterator[TestClient]:
    registry = StrategyRegistry()
    registry.register(LevelStrategy)
    registry.register(BrokenStrategy)
    with TestClient(create_app(settings, provider=fake_provider, registry=registry),
                    raise_server_exceptions=False) as c:
        yield c


def test_list_and_schema(api: TestClient) -> None:
    listing = api.get("/api/strategies").json()
    assert [s["name"] for s in listing] == ["broken_test", "level_test"]
    schema = api.get("/api/strategies/level_test/schema").json()
    assert schema["title"] == "Level (test)"
    assert {p["name"]: p["type"] for p in schema["parameters"]} == {
        "lookback": "integer", "level": "number", "band": "number", "mode": "string", "enabled": "boolean"}
    assert [o["format"] for o in schema["outputs"]] == ["price", "number"]
    missing = api.get("/api/strategies/nope/schema")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_run_with_signal_history(api: TestClient, fake_provider: FakeProvider) -> None:
    today = datetime.now(UTC).date()
    fake_provider.set_closes("LOW", {today - timedelta(days=i): 100.0 for i in range(1, 30)})
    fake_provider.set_quote("LOW", 90.0, previous_close=91.0)
    api.post("/api/market-data/refresh", json={"tickers": ["LOW"]})

    body = {"tickers": ["low", "NOPE"], "config": {"lookback": 2}, "instance_id": "pane-abc"}
    resp = api.post("/api/strategies/level_test/run", json=body)

    assert resp.status_code == 200
    data = resp.json()
    assert data["strategy"] == "level_test" and data["instance_id"] == "pane-abc"
    assert data["config"] == {"lookback": 2, "level": 100.0, "band": 10.0, "mode": "normal", "enabled": True}
    low, nope = data["results"]
    assert low["ticker"] == "LOW" and low["signal"] == "BUY" and low["status"] == "OK" and low["is_new_signal"]
    assert low["metrics"]["distance"] == -10.0 and low["current_price"] == 90.0
    assert nope["status"] == "NO_PRICE" and nope["signal"] is None

    again = api.post("/api/strategies/level_test/run", json=body).json()["results"][0]
    assert again["is_new_signal"] is False and again["signal"] == "BUY"

    history = api.get("/api/strategies/signals", params={"instance_id": "pane-abc"}).json()
    assert history["total"] == 1 and history["limit"] == 50
    [event] = history["items"]
    assert (event["ticker"], event["previous_signal"], event["new_signal"]) == ("LOW", None, "BUY")
    assert event["metric_name"] == "distance" and event["metric_value"] == -10.0
    assert api.get("/api/strategies/signals", params={"ticker": "low"}).json()["total"] == 1


def test_run_errors(api: TestClient) -> None:
    bad_config = api.post("/api/strategies/level_test/run", json={"tickers": ["A"], "config": {"lookback": 0}})
    assert bad_config.status_code == 422
    error = bad_config.json()["error"]
    assert error["code"] == "invalid_strategy_config" and "lookback" in error["details"]

    assert api.post("/api/strategies/nope/run", json={"tickers": ["A"]}).status_code == 404
    bad_ticker = api.post("/api/strategies/level_test/run", json={"tickers": ["not valid"]})
    assert bad_ticker.status_code == 422 and bad_ticker.json()["error"]["code"] == "validation_error"
    bad_instance = api.post("/api/strategies/level_test/run", json={"tickers": ["A"], "instance_id": "a b"})
    assert bad_instance.status_code == 422

    crashed = api.post("/api/strategies/broken_test/run", json={"tickers": ["A"]})
    assert crashed.status_code == 500
    assert crashed.json()["error"]["code"] == "strategy_failed" and "Traceback" not in crashed.text

    assert api.get("/api/strategies/signals", params={"limit": 0}).status_code == 422


def test_default_app_discovers_strategies(client: TestClient) -> None:
    # The real registry: no strategies yet in Phase 6 (Mean Reversion arrives in Phase 7).
    assert client.get("/api/strategies").status_code == 200
