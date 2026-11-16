from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from tests.fakes import FakeProvider


def _positions_portfolio(client: TestClient) -> str:
    return client.get("/api/portfolios", params={"type": "positions"}).json()[0]["id"]


def test_position_lifecycle(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("AAPL", 215.42, previous_close=218.10)
    fake_provider.currency = "GBp"
    fake_provider.set_quote("VOD.L", 118.1, previous_close=117.0)
    fake_provider.currency = "USD"
    pid = _positions_portfolio(client)

    created = client.post(f"/api/portfolios/{pid}/positions",
                          json={"ticker": "aapl", "quantity": 20, "entry_price": "210", "entry_date": "2026-01-05"})
    assert created.status_code == 201
    aapl = created.json()
    assert aapl["ticker"] == "AAPL" and aapl["status"] == "OPEN" and aapl["currency"] == "USD"
    assert aapl["market_value"] == 4308.4 and aapl["unrealised_pnl"] == 108.4 and aapl["daily_pnl"] == -53.6

    vod = client.post(f"/api/portfolios/{pid}/positions", json={"ticker": "VOD.L", "quantity": 1000}).json()
    assert vod["entry_price"] == 118.1 and vod["currency"] == "GBp"

    dup = client.post(f"/api/portfolios/{pid}/positions", json={"ticker": "AAPL", "quantity": 1})
    assert dup.status_code == 409

    portfolio = client.get(f"/api/portfolios/{pid}").json()
    assert portfolio["tickers"] == ["AAPL", "VOD.L"]

    edited = client.put(f"/api/positions/{aapl['id']}", json={"quantity": 15, "notes": "trimmed"})
    assert edited.status_code == 200 and edited.json()["quantity"] == 15 and edited.json()["cost_basis"] == 3150

    closed = client.post(f"/api/positions/{aapl['id']}/close", json={"exit_price": 230})
    assert closed.status_code == 200
    assert closed.json()["status"] == "CLOSED" and closed.json()["realised_pnl"] == 300
    assert closed.json()["exit_date"] == str(datetime.now(UTC).date())  # defaults to today (UTC)

    listing = client.get(f"/api/portfolios/{pid}/positions").json()
    assert {p["ticker"]: p["status"] for p in listing["positions"]} == {"AAPL": "CLOSED", "VOD.L": "OPEN"}
    totals = {t["currency"]: t for t in listing["totals"]}
    assert totals["USD"]["realised_pnl"] == 300 and totals["USD"]["market_value"] is None
    assert totals["GBp"]["market_value"] == 118100 and totals["GBp"]["incomplete"] is False

    open_only = client.get(f"/api/portfolios/{pid}/positions", params={"status": "open"}).json()
    assert [p["ticker"] for p in open_only["positions"]] == ["VOD.L"]
    assert client.get(f"/api/portfolios/{pid}").json()["tickers"] == ["VOD.L"]

    assert client.delete(f"/api/positions/{aapl['id']}").status_code == 204
    assert client.get(f"/api/positions/{aapl['id']}").status_code == 404


def test_close_with_empty_body_uses_defaults(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("AAPL", 215.42)
    pid = _positions_portfolio(client)
    position = client.post(f"/api/portfolios/{pid}/positions",
                           json={"ticker": "AAPL", "quantity": 1, "entry_price": 200}).json()
    closed = client.post(f"/api/positions/{position['id']}/close")
    assert closed.status_code == 200 and closed.json()["exit_price"] == 215.42


def test_validation_errors(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("AAPL", 1.0)
    pid = _positions_portfolio(client)
    url = f"/api/portfolios/{pid}/positions"
    assert client.post(url, json={"ticker": "AAPL", "quantity": 0}).status_code == 422
    assert client.post(url, json={"ticker": "AAPL", "quantity": -1}).status_code == 422
    assert client.post(url, json={"ticker": "AAPL", "quantity": 1, "entry_price": "abc"}).status_code == 422
    assert client.post(url, json={"ticker": "ZZZZ", "quantity": 1}).json()["error"]["code"] == "invalid_ticker"
    assert client.post(url, json={"ticker": "AAPL", "quantity": 1, "entry_date": "2999-01-01"}).status_code == 400
    assert client.get(f"{url}?status=bogus").status_code == 422

    watch = client.get("/api/portfolios", params={"type": "watchlist"}).json()[0]["id"]
    resp = client.post(f"/api/portfolios/{watch}/positions", json={"ticker": "AAPL", "quantity": 1})
    assert resp.status_code == 400 and "is a watchlist" in resp.json()["error"]["message"]

    position = client.post(url, json={"ticker": "AAPL", "quantity": 1}).json()
    bad_edit = client.put(f"/api/positions/{position['id']}", json={"exit_price": 5})
    assert bad_edit.status_code == 400
    assert client.put("/api/positions/nope", json={"notes": "x"}).status_code == 404


def test_positions_survive_restart(settings, fake_provider: FakeProvider) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app

    fake_provider.set_quote("AAPL", 215.42)
    with TestClient(create_app(settings, provider=fake_provider)) as c:
        pid = _positions_portfolio(c)
        c.post(f"/api/portfolios/{pid}/positions", json={"ticker": "AAPL", "quantity": "0.5", "entry_price": "100.12345678"})
    with TestClient(create_app(settings, provider=fake_provider)) as c:
        [p] = c.get(f"/api/portfolios/{pid}/positions").json()["positions"]
        assert p["quantity"] == 0.5 and p["entry_price"] == 100.12345678
