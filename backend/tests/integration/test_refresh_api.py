"""Global dashboard refresh (plan §11): ticker collection, partial failure, valuation."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from app.market_data.base import ProviderError
from tests.fakes import FIXED_NOW, FakeProvider


def _ids(client: TestClient) -> tuple[str, str]:
    by_type = {p["type"]: p["id"] for p in client.get("/api/portfolios").json()}
    return by_type["watchlist"], by_type["positions"]


def _requested(fake: FakeProvider) -> list[str]:
    return [t for call in fake.quote_calls for t in call]


def test_refresh_collects_portfolio_and_extra_tickers_once(client: TestClient, fake_provider: FakeProvider) -> None:
    for ticker, price in {"AAPL": 100.0, "MSFT": 200.0, "VOD.L": 1.2, "NVDA": 50.0, "OLD": 10.0}.items():
        fake_provider.set_quote(ticker, price, previous_close=price)
    watchlist, positions = _ids(client)
    client.post(f"/api/portfolios/{watchlist}/tickers", json={"ticker": "AAPL"})
    client.post(f"/api/portfolios/{watchlist}/tickers", json={"ticker": "MSFT"})
    client.post(f"/api/portfolios/{positions}/positions", json={"ticker": "AAPL", "quantity": 1})
    client.post(f"/api/portfolios/{positions}/positions", json={"ticker": "VOD.L", "quantity": 1})
    old = client.post(f"/api/portfolios/{positions}/positions", json={"ticker": "OLD", "quantity": 1}).json()
    client.post(f"/api/positions/{old['id']}/close", json={})
    fake_provider.quote_calls.clear()

    resp = client.post("/api/market-data/refresh", json={"extra_tickers": ["nvda", "MSFT", "AAPL"]})

    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "completed"
    assert (body["tickers_requested"], body["tickers_updated"], body["tickers_failed"]) == (4, 4, 0)
    # One provider request per unique ticker; closed positions need no price.
    requested = _requested(fake_provider)
    assert sorted(requested) == ["AAPL", "MSFT", "NVDA", "VOD.L"]
    assert len(requested) == len(set(requested))


def test_refresh_without_body_uses_portfolios_only(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("AAPL", 100.0)
    watchlist, _ = _ids(client)
    client.post(f"/api/portfolios/{watchlist}/tickers", json={"ticker": "AAPL"})
    fake_provider.quote_calls.clear()

    assert client.post("/api/market-data/refresh").json()["tickers_requested"] == 1
    assert client.post("/api/market-data/refresh", json={}).json()["tickers_requested"] == 1
    assert _requested(fake_provider) == ["AAPL", "AAPL"]


def test_refresh_with_nothing_to_do(client: TestClient) -> None:
    body = client.post("/api/market-data/refresh").json()
    assert body["status"] == "completed" and body["tickers_requested"] == 0


def test_refresh_request_validation(client: TestClient) -> None:
    # The old per-ticker body is rejected rather than silently ignored.
    assert client.post("/api/market-data/refresh", json={"tickers": ["AAPL"]}).status_code == 422
    assert client.post("/api/market-data/refresh", json={"extra_tickers": ["bad ticker!"]}).status_code == 422
    too_many = [f"T{i}" for i in range(201)]
    assert client.post("/api/market-data/refresh", json={"extra_tickers": too_many}).status_code == 422


def test_partial_failure_keeps_last_price_and_updates_valuation(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("AAPL", 100.0, previous_close=95.0)
    fake_provider.set_quote("MSFT", 200.0, previous_close=190.0)
    watchlist, positions = _ids(client)
    client.post(f"/api/portfolios/{watchlist}/tickers", json={"ticker": "MSFT"})
    client.post(f"/api/portfolios/{positions}/positions", json={"ticker": "AAPL", "quantity": 10, "entry_price": "90"})

    # Next refresh: AAPL moves (a later quote), MSFT fails.
    later = FIXED_NOW + timedelta(minutes=5)
    fake_provider.set_quote("AAPL", 110.0, previous_close=100.0, timestamp=later)
    fake_provider.quotes["MSFT"] = ProviderError("timeout")
    body = client.post("/api/market-data/refresh").json()
    assert body["status"] == "partial"
    assert (body["tickers_updated"], body["tickers_failed"]) == (1, 1)
    assert body["errors"][0]["ticker"] == "MSFT"

    # Position valuation uses the new price.
    [position] = client.get(f"/api/portfolios/{positions}/positions").json()["positions"]
    assert position["current_price"] == 110.0
    assert position["market_value"] == 1100.0 and position["unrealised_pnl"] == 200.0 and position["daily_pnl"] == 100.0

    # MSFT keeps its last valid price, marked stale.
    [row] = client.get(f"/api/portfolios/{watchlist}/quotes").json()["rows"]
    assert row["price"] == 200.0 and row["stale"] is True and row["last_error"] == "timeout"

    status = client.get("/api/market-data/status").json()
    assert status["last_refresh"]["status"] == "partial"
    assert status["last_successful_refresh_at"] is not None

    # A later successful refresh clears the stale flag.
    fake_provider.set_quote("MSFT", 205.0, previous_close=200.0, timestamp=later)
    assert client.post("/api/market-data/refresh").json()["status"] == "completed"
    [row] = client.get(f"/api/portfolios/{watchlist}/quotes").json()["rows"]
    assert row["price"] == 205.0 and row["stale"] is False


def test_strategy_recalculates_after_refresh(client: TestClient, fake_provider: FakeProvider) -> None:
    today = datetime.now(UTC).date()
    fake_provider.set_closes("AAPL", {today - timedelta(days=i): (98.0 if i % 2 else 102.0) for i in range(1, 40)})
    fake_provider.set_quote("AAPL", 100.0, previous_close=100.0, timestamp=datetime.now(UTC))
    run = {"tickers": ["AAPL"], "config": {"lookback_days": 10}, "instance_id": "pane-r"}

    client.post("/api/market-data/refresh", json={"extra_tickers": ["AAPL"]})
    first = client.post("/api/strategies/mean_reversion/run", json=run).json()["results"][0]
    assert first["signal"] is None

    fake_provider.set_quote("AAPL", 90.0, previous_close=100.0, timestamp=datetime.now(UTC) + timedelta(seconds=1))
    client.post("/api/market-data/refresh", json={"extra_tickers": ["AAPL"]})
    second = client.post("/api/strategies/mean_reversion/run", json=run).json()["results"][0]
    assert second["current_price"] == 90.0 and second["signal"] == "BUY" and second["is_new_signal"] is True


def test_concurrent_refresh_is_rejected(client: TestClient) -> None:
    service = client.app.state.refresh
    assert service._running.acquire(blocking=False)
    try:
        resp = client.post("/api/market-data/refresh")
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "refresh_in_progress"
    finally:
        service._running.release()
    assert client.post("/api/market-data/refresh").status_code == 200
