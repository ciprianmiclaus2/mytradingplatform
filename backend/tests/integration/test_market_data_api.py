from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.market_data.base import ProviderError
from app.market_data.models import TickerSearchResult
from tests.fakes import FakeProvider


def test_search(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.search_results = [
        TickerSearchResult(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ", currency="USD",
                           instrument_type="EQUITY", provider="fake")
    ]
    resp = client.get("/api/market-data/search", params={"q": "apple"})
    assert resp.status_code == 200
    assert resp.json() == [{"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "currency": "USD",
                            "instrument_type": "EQUITY", "provider": "fake"}]


def test_search_validation_and_provider_failure(client: TestClient, fake_provider: FakeProvider) -> None:
    assert client.get("/api/market-data/search", params={"q": ""}).status_code == 422
    fake_provider.search_error = ProviderError("Yahoo down")
    resp = client.get("/api/market-data/search", params={"q": "apple"})
    assert resp.status_code == 502
    assert resp.json()["error"]["code"] == "market_data_provider_unavailable"


def test_refresh_then_prices_then_status(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("AAPL", 215.42, previous_close=218.10)
    fake_provider.quotes["MSFT"] = ProviderError("timeout")

    resp = client.post("/api/market-data/refresh", json={"extra_tickers": ["aapl", "MSFT", "AAPL"]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "partial"
    assert (body["tickers_requested"], body["tickers_updated"], body["tickers_failed"]) == (2, 1, 1)
    assert body["errors"] == [{"ticker": "MSFT", "code": "provider_error", "message": "timeout"}]

    prices = client.get("/api/market-data/prices", params={"tickers": "AAPL,MSFT"}).json()
    assert prices["missing"] == ["MSFT"]
    [aapl] = prices["prices"]
    assert aapl["ticker"] == "AAPL" and aapl["price"] == 215.42 and aapl["delayed"] is True
    assert aapl["stale"] is False and round(aapl["daily_change"], 2) == -2.68
    assert aapl["timestamp"].startswith("2026-11-16T15:00:00")

    status = client.get("/api/market-data/status").json()
    assert status["provider"] == "fake"
    assert status["last_refresh"]["status"] == "partial"
    assert status["last_successful_refresh_at"] is not None


def test_refresh_rejects_invalid_ticker(client: TestClient) -> None:
    resp = client.post("/api/market-data/refresh", json={"extra_tickers": ["AAPL", "bad ticker!"]})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_prices_validation(client: TestClient) -> None:
    assert client.get("/api/market-data/prices", params={"tickers": " , "}).status_code == 400
    assert client.get("/api/market-data/prices", params={"tickers": "A B"}).status_code == 400


def test_history(client: TestClient, fake_provider: FakeProvider) -> None:
    yesterday = datetime.now(UTC).date() - timedelta(days=1)  # last completed session per service
    start = yesterday - timedelta(days=13)
    fake_provider.set_closes("AAPL", {start + timedelta(days=i): 100.0 + i for i in range(14)})

    resp = client.get("/api/market-data/history", params={"ticker": "aapl", "start": str(start)})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ticker"] == "AAPL" and body["status"] == "OK"
    assert len(body["bars"]) == 14
    assert body["bars"][0] == {
        "ticker": "AAPL", "trading_date": str(start), "close": 100.0, "adjusted_close": 99.0,
        "currency": "USD", "provider": "fake", "fetched_at": body["bars"][0]["fetched_at"],
    }
    # Second call is served from cache.
    client.get("/api/market-data/history", params={"ticker": "AAPL", "start": str(start)})
    assert len(fake_provider.history_calls) == 1


def test_history_errors(client: TestClient, fake_provider: FakeProvider) -> None:
    bad_range = client.get("/api/market-data/history", params={"ticker": "AAPL", "start": "2026-02-01", "end": "2026-01-01"})
    assert bad_range.status_code == 400
    too_long = client.get("/api/market-data/history", params={"ticker": "AAPL", "start": "2000-01-01", "end": "2026-01-01"})
    assert too_long.status_code == 400
    fake_provider.history_failures["MSFT"] = ProviderError("down")
    failed = client.get("/api/market-data/history", params={"ticker": "MSFT"}).json()
    assert failed["status"] == "ERROR" and failed["error"] == "down"
