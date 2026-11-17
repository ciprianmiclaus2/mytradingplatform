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
    api.post("/api/market-data/refresh", json={"extra_tickers": ["LOW"]})

    body = {"tickers": ["low", "NOPE"], "config": {"lookback": 2}, "instance_id": "pane-abc"}
    # First run with a wide band: no signal yet (the baseline).
    first = api.post("/api/strategies/level_test/run", json={**body, "config": {"lookback": 2, "level": 85, "band": 50}}).json()
    assert first["results"][0]["signal"] is None and first["results"][0]["is_new_signal"] is False
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


def test_default_app_runs_mean_reversion(client: TestClient, fake_provider: FakeProvider) -> None:
    today = datetime.now(UTC).date()
    closes = {today - timedelta(days=i): (98.0 if i % 2 else 102.0) for i in range(1, 60)}
    fake_provider.set_closes("AAPL", closes)
    fake_provider.set_quote("AAPL", 95.0, previous_close=97.0, timestamp=datetime.now(UTC), name="Apple Inc.")
    client.post("/api/market-data/refresh", json={"extra_tickers": ["AAPL"]})

    listed = client.get("/api/strategies").json()
    assert [s["title"] for s in listed] == ["Bollinger Bands", "MACD", "Mean Reversion", "Moving Average Crossover", "RSI"]
    assert all(s["explanation"] for s in listed)
    resp = client.post("/api/strategies/mean_reversion/run",
                       json={"tickers": ["AAPL"], "config": {"lookback_days": 10}, "instance_id": "p1"})
    assert resp.status_code == 200
    [row] = resp.json()["results"]
    assert row["status"] == "OK" and row["signal"] == "BUY" and row["name"] == "Apple Inc."
    assert row["metrics"] == {"mean": 100.0, "standard_deviation": 2.0, "z_score": -2.5}

    bad = client.post("/api/strategies/mean_reversion/run",
                      json={"tickers": ["AAPL"], "config": {"buy_threshold": 3, "sell_threshold": 2}})
    assert bad.status_code == 422 and "buy_threshold" in bad.json()["error"]["details"]


def test_default_app_runs_rsi_and_ma_crossover(client: TestClient, fake_provider: FakeProvider) -> None:
    today = datetime.now(UTC).date()
    # 300 sessions rising steadily, then the quote drops sharply.
    fake_provider.set_closes("UP", {today - timedelta(days=i): 100.0 + (300 - i) * 0.1 for i in range(1, 301)})
    fake_provider.set_quote("UP", 110.0, previous_close=129.9, timestamp=datetime.now(UTC))
    client.post("/api/market-data/refresh", json={"extra_tickers": ["UP"]})

    schema = client.get("/api/strategies/rsi/schema").json()
    assert schema["explanation"].startswith("The Relative Strength Index")
    assert [p["name"] for p in schema["parameters"]] == ["period", "oversold", "overbought"]

    rsi = client.post("/api/strategies/rsi/run", json={"tickers": ["UP"], "instance_id": "p-rsi"}).json()
    [row] = rsi["results"]
    assert row["status"] == "OK" and 0 <= row["metrics"]["rsi"] <= 100

    ma = client.post("/api/strategies/ma_crossover/run",
                     json={"tickers": ["UP"], "config": {"fast_period": 20, "slow_period": 50, "signal_mode": "Trend"},
                           "instance_id": "p-ma"}).json()
    [row] = ma["results"]
    assert row["status"] == "OK" and row["signal"] == "BUY"  # long uptrend: fast above slow
    assert row["metrics"]["fast_ma"] > row["metrics"]["slow_ma"] and row["metrics"]["spread_pct"] > 0
    assert row["is_new_signal"] is False and row["signal_changed_at"] is None  # first sighting, not a new cross

    ema = client.post("/api/strategies/ma_crossover/run",
                      json={"tickers": ["UP"], "config": {"fast_period": 20, "slow_period": 50, "average_type": "EMA",
                                                          "use_current_price": False}}).json()
    assert ema["results"][0]["status"] == "OK" and ema["config"]["average_type"] == "EMA"

    # Default mode (recent cross): a trend that started long ago gives no signal.
    recent = client.post("/api/strategies/ma_crossover/run",
                         json={"tickers": ["UP"], "config": {"fast_period": 20, "slow_period": 50}}).json()["results"][0]
    assert recent["signal"] is None and recent["metrics"]["sessions_since_cross"] is None

    bad = client.post("/api/strategies/ma_crossover/run",
                      json={"tickers": ["UP"], "config": {"fast_period": 60, "slow_period": 50}})
    assert bad.status_code == 422 and "fast_period" in bad.json()["error"]["details"]


def test_default_app_runs_bollinger_and_macd(client: TestClient, fake_provider: FakeProvider) -> None:
    today = datetime.now(UTC).date()
    # 300 sessions oscillating gently around 100, then the quote jumps well above the range.
    fake_provider.set_closes("OSC", {today - timedelta(days=i): 100.0 + (1.0 if i % 2 else -1.0) for i in range(1, 301)})
    fake_provider.set_quote("OSC", 110.0, previous_close=99.0, timestamp=datetime.now(UTC))
    client.post("/api/market-data/refresh", json={"extra_tickers": ["OSC"]})

    bb = client.post("/api/strategies/bollinger/run", json={"tickers": ["OSC"], "instance_id": "p-bb"}).json()
    [row] = bb["results"]
    assert row["status"] == "OK" and row["signal"] == "SELL"  # mean reversion: far above the upper band
    assert row["metrics"]["percent_b"] > 1 and row["metrics"]["width_rank"] is not None
    breakout = client.post("/api/strategies/bollinger/run",
                           json={"tickers": ["OSC"], "config": {"signal_mode": "Breakout"}}).json()
    assert breakout["results"][0]["signal"] == "BUY"

    # MACD: an accelerating decline, then today's quote jumps back up.
    fake_provider.set_closes("DIP", {today - timedelta(days=i): 110.0 - 0.0001 * (300 - i) ** 2 for i in range(1, 301)})
    fake_provider.set_quote("DIP", 110.0, previous_close=101.0, timestamp=datetime.now(UTC))
    client.post("/api/market-data/refresh", json={"extra_tickers": ["DIP"]})
    macd = client.post("/api/strategies/macd/run", json={"tickers": ["DIP"], "instance_id": "p-macd"}).json()
    [row] = macd["results"]
    assert row["status"] == "OK" and row["signal"] == "BUY"  # the jump crosses the MACD above its signal line today
    assert row["metrics"]["sessions_since_cross"] == 0 and row["metrics"]["histogram"] > 0

    schema = client.get("/api/strategies/macd/schema").json()
    assert [p["name"] for p in schema["parameters"]] == [
        "fast_period", "slow_period", "signal_period", "signal_mode", "recent_sessions", "use_current_price"]
    assert schema["explanation"].startswith("MACD")
    bad = client.post("/api/strategies/bollinger/run", json={"tickers": ["OSC"], "config": {"width": 9}})
    assert bad.status_code == 422 and "width" in bad.json()["error"]["details"]
