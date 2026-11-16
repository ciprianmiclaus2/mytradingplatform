"""Invalid input across the API: always a 4xx with the error envelope, never a 500."""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.fakes import FakeProvider

LONG = "x" * 2000

# (method, path, json body); {w} = watchlist id, {p} = positions portfolio id, {pos} = an open position id
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
    ("POST", "/api/portfolios/{p}/tickers", {"ticker": "AAPL"}),  # positions lists are derived
    ("DELETE", "/api/portfolios/{w}/tickers/NOTTHERE", None),
    ("PUT", "/api/portfolios/{w}/favourites/NOTTHERE", None),
    ("PUT", "/api/portfolios/{w}/favourites/b@d", None),
    # positions
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL"}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": 0}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": -5}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": "abc"}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": "1.123456789"}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": "1e30"}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": 1, "entry_price": 0}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": 1, "entry_date": "2026-13-45"}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "AAPL", "quantity": 1, "notes": LONG}),
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "MSFT", "quantity": 1}),  # duplicate open position
    ("POST", "/api/portfolios/{w}/positions", {"ticker": "AAPL", "quantity": 1}),  # watchlist
    ("POST", "/api/portfolios/{p}/positions", {"ticker": "NOSUCH", "quantity": 1}),
    ("PUT", "/api/positions/{pos}", {"quantity": -1}),
    ("PUT", "/api/positions/{pos}", {"exit_price": 10}),  # exit fields on an open position
    ("POST", "/api/positions/{pos}/close", {"exit_price": -1}),
    ("POST", "/api/positions/{pos}/close", {"exit_date": "1990-01-01"}),  # before entry
    ("GET", "/api/positions/nope", None),
    ("DELETE", "/api/positions/nope", None),
    ("GET", "/api/portfolios/{p}/positions?status=pending", None),
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
    by_type = {p["type"]: p["id"] for p in client.get("/api/portfolios").json()}
    client.post(f"/api/portfolios/{by_type['watchlist']}/tickers", json={"ticker": "AAPL"})
    pos = client.post(f"/api/portfolios/{by_type['positions']}/positions", json={"ticker": "MSFT", "quantity": 1}).json()
    return {"w": by_type["watchlist"], "p": by_type["positions"], "pos": pos["id"]}


@pytest.mark.parametrize(("method", "path", "body"), CASES, ids=[f"{m} {p[:60]} {str(b)[:40]}" for m, p, b in CASES])
def test_invalid_input_is_rejected_cleanly(client: TestClient, ids: dict[str, str], method: str, path: str, body: Any) -> None:
    resp = client.request(method, path.format(**ids), json=body)
    assert 400 <= resp.status_code < 500, resp.text
    error = resp.json()["error"]
    assert error["code"] and error["message"]


def test_invalid_input_changes_nothing(client: TestClient, ids: dict[str, str]) -> None:
    before = (client.get("/api/portfolios").json(), client.get(f"/api/portfolios/{ids['p']}/positions").json())
    for method, path, body in CASES:
        if method != "GET":
            client.request(method, path.format(**ids), json=body)
    after = (client.get("/api/portfolios").json(), client.get(f"/api/portfolios/{ids['p']}/positions").json())
    assert after == before
