"""Invalid input across the API: always a 4xx with the error envelope, never a 500."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeProvider

LONG = "x" * 2000

# (method, path, json body); {w} = watchlist id
CASES: list[tuple[str, str, Any]] = [
    # portfolios
    ("POST", "/api/portfolios", {}),
    ("POST", "/api/portfolios", {"name": "   "}),
    ("POST", "/api/portfolios", {"name": LONG}),
    ("POST", "/api/portfolios", {"name": "X", "type": "cash"}),
    ("POST", "/api/portfolios", {"name": "Main Portfolio"}),  # duplicate name
    ("POST", "/api/portfolios", ["not", "an", "object"]),
    ("PUT", "/api/portfolios/{w}", {"description": LONG}),
    ("GET", "/api/portfolios/does-not-exist", None),
    ("GET", "/api/portfolios?type=cash", None),
    ("DELETE", "/api/portfolios/does-not-exist", None),
    ("POST", "/api/portfolios/{w}/tickers", {"ticker": ""}),
    ("POST", "/api/portfolios/{w}/tickers", {"ticker": "bad ticker!"}),
    ("POST", "/api/portfolios/{w}/tickers", {"ticker": "NOSUCH"}),
    ("POST", "/api/portfolios/{w}/tickers", {"ticker": 123}),
    ("DELETE", "/api/portfolios/{w}/tickers/NOTTHERE", None),
    ("PUT", "/api/portfolios/{w}/favourites/NOTTHERE", None),
    ("PUT", "/api/portfolios/{w}/favourites/b@d", None),
    # brokers (SnapTrade not set up yet)
    ("PUT", "/api/brokers/snaptrade/settings", {}),
    ("PUT", "/api/brokers/snaptrade/settings", {"client_id": "a", "consumer_key": "", "user_id": "u", "user_secret": "s"}),
    ("PUT", "/api/brokers/snaptrade/settings", {"client_id": LONG, "consumer_key": "k", "user_id": "u", "user_secret": "s"}),
    ("PUT", "/api/brokers/snaptrade/settings", {"client_id": "wrong", "consumer_key": "k", "user_id": "u", "user_secret": "s"}),
    ("PUT", "/api/brokers/snaptrade/settings", {"client_id": "c", "consumer_key": "k", "user_id": "u"}),  # secret missing
    ("POST", "/api/brokers/refresh", None),
    ("GET", "/api/brokers/accounts/nope/positions", None),
    ("POST", "/api/brokers/accounts/nope/refresh", None),
    # market data
    ("GET", "/api/market-data/search", None),
    ("GET", "/api/market-data/search?q=" + "a" * 51, None),
    ("GET", "/api/market-data/search?q=a&limit=0", None),
    ("GET", "/api/market-data/prices?tickers=", None),
    ("GET", "/api/market-data/prices?tickers=" + ",".join(f"T{i}" for i in range(201)), None),
    ("GET", "/api/market-data/history?ticker=AAPL&start=2026-02-01&end=2026-01-01", None),
    ("GET", "/api/market-data/history?ticker=AAPL&start=2000-01-01&end=2026-01-01", None),
    ("GET", "/api/market-data/history?ticker=b@d", None),
    ("POST", "/api/market-data/refresh", {"extra_tickers": "AAPL"}),
    ("POST", "/api/market-data/refresh", {"extra_tickers": ["b@d"]}),
    # strategies
    ("GET", "/api/strategies/nope/schema", None),
    ("POST", "/api/strategies/nope/run", {"tickers": ["AAPL"]}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "config": {"lookback_days": 1}}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "config": {"lookback_days": "ten"}}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "config": {"lookback_days": 2.5}}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "config": {"lookback_days": True}}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "config": {"buy_threshold": 3}}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "config": {"unknown": 1}}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "config": {"buy_threshold": "nan"}}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["AAPL"], "instance_id": "has space"}),
    ("POST", "/api/strategies/mean_reversion/run", {"tickers": ["b@d"]}),
    ("GET", "/api/strategies/signals?limit=0", None),
    ("GET", "/api/strategies/signals?ticker=b@d", None),
]


@pytest.fixture
def ids(client: TestClient, fake_provider: FakeProvider) -> dict[str, str]:
    fake_provider.set_quote("AAPL", 100.0, previous_close=99.0)
    fake_provider.set_quote("MSFT", 400.0, previous_close=399.0)
    [watchlist] = client.get("/api/portfolios").json()
    client.post(f"/api/portfolios/{watchlist['id']}/tickers", json={"ticker": "AAPL"})
    return {"w": watchlist["id"]}


@pytest.mark.parametrize(("method", "path", "body"), CASES, ids=[f"{m} {p[:60]} {str(b)[:40]}" for m, p, b in CASES])
def test_invalid_input_is_rejected_cleanly(client: TestClient, ids: dict[str, str], method: str, path: str, body: Any) -> None:
    resp = client.request(method, path.format(**ids), json=body)
    assert 400 <= resp.status_code < 500, resp.text
    error = resp.json()["error"]
    assert error["code"] and error["message"]


def test_invalid_input_changes_nothing(client: TestClient, ids: dict[str, str]) -> None:
    before = (client.get("/api/portfolios").json(), client.get("/api/brokers/snaptrade/settings").json())
    for method, path, body in CASES:
        if method != "GET":
            client.request(method, path.format(**ids), json=body)
    after = (client.get("/api/portfolios").json(), client.get("/api/brokers/snaptrade/settings").json())
    assert after == before


def test_index_ticker_round_trip_and_readable_validation_message(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("^FTSE", 8200.0, previous_close=8150.0)
    [main] = client.get("/api/portfolios").json()
    added = client.post(f"/api/portfolios/{main['id']}/tickers", json={"ticker": "^ftse"})
    assert added.status_code == 201 and "^FTSE" in added.json()["tickers"]
    assert [r["ticker"] for r in client.get(f"/api/portfolios/{main['id']}/quotes").json()["rows"]] == ["^FTSE"]
    assert client.delete(f"/api/portfolios/{main['id']}/tickers/%5EFTSE").status_code == 200

    bad = client.post(f"/api/portfolios/{main['id']}/tickers", json={"ticker": "bad ticker!"}).json()["error"]
    assert bad["code"] == "validation_error"
    assert bad["message"] == "Request validation failed: Invalid ticker symbol 'bad ticker!'"
