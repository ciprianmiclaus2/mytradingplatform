from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.market_data.base import ProviderError
from tests.fakes import FakeProvider


def _main(client: TestClient) -> dict:
    return client.get("/api/portfolios", params={"type": "watchlist"}).json()[0]


def test_default_portfolios(client: TestClient) -> None:
    resp = client.get("/api/portfolios")
    assert resp.status_code == 200
    assert [(p["name"], p["type"]) for p in resp.json()] == [("Main Portfolio", "watchlist")]


def test_portfolio_crud(client: TestClient) -> None:
    created = client.post("/api/portfolios", json={"name": "Tech", "description": "AI names"})
    assert created.status_code == 201
    pid = created.json()["id"]
    assert created.json()["type"] == "watchlist"

    assert client.get(f"/api/portfolios/{pid}").json()["name"] == "Tech"
    updated = client.put(f"/api/portfolios/{pid}", json={"name": "Technology"})
    assert updated.status_code == 200 and updated.json()["name"] == "Technology"
    assert updated.json()["description"] == "AI names"

    assert client.delete(f"/api/portfolios/{pid}").status_code == 204
    missing = client.get(f"/api/portfolios/{pid}")
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"


def test_create_validation_errors(client: TestClient) -> None:
    dup = client.post("/api/portfolios", json={"name": "main portfolio"})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "conflict"
    assert client.post("/api/portfolios", json={"name": ""}).status_code == 422
    assert client.post("/api/portfolios", json={"name": "X", "type": "account"}).status_code == 422
    assert client.post("/api/portfolios", json={"name": "X", "type": "positions"}).status_code == 422  # retired


def test_cannot_delete_last_portfolio(client: TestClient) -> None:
    first = client.get("/api/portfolios").json()[0]
    second = client.post("/api/portfolios", json={"name": "Second"}).json()
    assert client.delete(f"/api/portfolios/{first['id']}").status_code == 204
    resp = client.delete(f"/api/portfolios/{second['id']}")
    assert resp.status_code == 409 and "last remaining" in resp.json()["error"]["message"]


def test_ticker_and_favourite_flow(client: TestClient, fake_provider: FakeProvider) -> None:
    fake_provider.set_quote("AAPL", 215.0, previous_close=214.0)
    fake_provider.set_quote("MSFT", 410.0, previous_close=412.0)
    pid = _main(client)["id"]

    resp = client.post(f"/api/portfolios/{pid}/tickers", json={"ticker": "aapl"})
    assert resp.status_code == 201 and resp.json()["tickers"] == ["AAPL"]
    client.post(f"/api/portfolios/{pid}/tickers", json={"ticker": "MSFT"})
    assert client.post(f"/api/portfolios/{pid}/tickers", json={"ticker": "AAPL"}).status_code == 409

    fav = client.put(f"/api/portfolios/{pid}/favourites/msft")
    assert fav.status_code == 200 and fav.json()["favourites"] == ["MSFT"]
    not_member = client.put(f"/api/portfolios/{pid}/favourites/NVDA")
    assert not_member.status_code == 400

    quotes = client.get(f"/api/portfolios/{pid}/quotes").json()
    assert quotes["portfolio_id"] == pid
    assert [(r["ticker"], r["price"], r["daily_change"], r["favourite"]) for r in quotes["rows"]] == [
        ("AAPL", 215.0, 1.0, False), ("MSFT", 410.0, -2.0, True)]

    removed = client.delete(f"/api/portfolios/{pid}/tickers/MSFT")
    assert removed.json()["tickers"] == ["AAPL"] and removed.json()["favourites"] == []
    assert client.delete(f"/api/portfolios/{pid}/favourites/AAPL").status_code == 200


def test_add_ticker_errors(client: TestClient, fake_provider: FakeProvider) -> None:
    pid = _main(client)["id"]
    unknown = client.post(f"/api/portfolios/{pid}/tickers", json={"ticker": "ZZZZ"})
    assert unknown.status_code == 422 and unknown.json()["error"]["code"] == "invalid_ticker"

    fake_provider.quotes["AAPL"] = ProviderError("timeout")
    down = client.post(f"/api/portfolios/{pid}/tickers", json={"ticker": "AAPL"})
    assert down.status_code == 502 and down.json()["error"]["code"] == "market_data_provider_unavailable"

    bad = client.post(f"/api/portfolios/{pid}/tickers", json={"ticker": "bad ticker"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "validation_error"

    assert client.post("/api/portfolios/nope/tickers", json={"ticker": "AAPL"}).status_code == 404


def test_portfolios_persist_across_restart(settings, fake_provider: FakeProvider, data_dir: Path) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app

    fake_provider.set_quote("AAPL", 1.0)
    with TestClient(create_app(settings, provider=fake_provider)) as c:
        pid = c.post("/api/portfolios", json={"name": "Keep"}).json()["id"]
        c.post(f"/api/portfolios/{pid}/tickers", json={"ticker": "AAPL"})
    with TestClient(create_app(settings, provider=fake_provider)) as c:
        names = [p["name"] for p in c.get("/api/portfolios").json()]
        assert names == ["Main Portfolio", "Keep"]
        assert c.get(f"/api/portfolios/{pid}").json()["tickers"] == ["AAPL"]
    assert (data_dir / "portfolios" / "portfolios.parquet").exists()


def test_legacy_positions_lists_are_removed_at_startup_with_a_backup(settings, fake_provider: FakeProvider,  # type: ignore[no-untyped-def]
                                                                       data_dir: Path) -> None:
    from datetime import UTC, datetime

    import pyarrow as pa

    from app.main import create_app
    from app.persistence.parquet import ParquetStore
    from app.portfolio.repository import PORTFOLIOS

    with TestClient(create_app(settings, provider=fake_provider)) as c:
        watchlist = c.get("/api/portfolios").json()[0]
    # Add a positions list as an older version would have stored it.
    store = ParquetStore(data_dir, c.app.state.persistence.store.lock)  # type: ignore[attr-defined]
    now = datetime(2026, 1, 1, tzinfo=UTC)
    legacy = {"id": "old", "name": "Main Positions", "description": "", "type": "positions", "tickers": [],
              "favourites": [], "created_at": now, "updated_at": now}
    store.update(PORTFOLIOS, lambda t: pa.concat_tables([t, pa.Table.from_pylist([legacy], schema=PORTFOLIOS.schema)]))
    backups_before = len(list((data_dir / "backups").iterdir()))

    with TestClient(create_app(settings, provider=fake_provider)) as c:
        assert [p["id"] for p in c.get("/api/portfolios").json()] == [watchlist["id"]]
    backups = sorted((data_dir / "backups").iterdir())
    assert any("before-remove-positions-lists" in b.name for b in backups[backups_before - 1:])
    with TestClient(create_app(settings, provider=fake_provider)) as c:  # nothing left to remove
        assert len(c.get("/api/portfolios").json()) == 1
