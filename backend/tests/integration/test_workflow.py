"""End-to-end V1 workflow (plan Phase 11), persistence across restarts, and backup recovery.

Uses the fake provider; never calls Yahoo Finance.
"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.fake_snaptrade import FakeSnapTrade, account, stock
from tests.fakes import FakeProvider

ROOT = Path(__file__).resolve().parents[3]


def _start(settings: Settings, provider: FakeProvider, snaptrade: FakeSnapTrade | None = None) -> TestClient:
    snaptrade = snaptrade or FakeSnapTrade()
    return TestClient(create_app(settings, provider=provider, snaptrade=snaptrade.factory), raise_server_exceptions=False)


def _market(provider: FakeProvider, now: datetime) -> None:
    """History for AAPL oscillates around 100; MSFT is flat; VOD.L is in pence."""
    today = now.date()
    provider.set_closes("AAPL", {today - timedelta(days=i): (98.0 if i % 2 else 102.0) for i in range(1, 60)})
    provider.set_closes("MSFT", {today - timedelta(days=i): 400.0 + (i % 3) for i in range(1, 60)})
    provider.set_quote("AAPL", 100.0, previous_close=99.0, timestamp=now)
    provider.set_quote("MSFT", 401.0, previous_close=400.0, timestamp=now)
    provider.currency = "GBp"
    provider.set_quote("VOD.L", 70.0, previous_close=71.0, timestamp=now)
    provider.currency = "USD"


def _backup_script(data_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "DATA_DIR": str(data_dir)}
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "backup_data.py"), *args],
        env=env, capture_output=True, text=True, timeout=60, check=False,
    )


def test_complete_workflow_survives_restart_and_restore(settings: Settings, data_dir: Path) -> None:
    provider = FakeProvider()
    now = datetime.now(UTC).replace(microsecond=0)
    _market(provider, now)

    snaptrade = FakeSnapTrade()
    snaptrade.accounts = [account("acc-1", "Brokerage", "****0001"), account("acc-2", "ISA", "****0002", currency="GBP")]
    snaptrade.positions = {
        "acc-1": [stock("AAPL", "10", "99", "90.5"),
                  stock("AAPL  261218C00240000", "1", "5.5", "4", kind="option", multiplier=100)],
        "acc-2": [stock("VOD", "1000", "0.69", "0.60", currency="GBP", exchange="XLON")],
    }

    # -- 1-13: the workflow from the plan ---------------------------------------
    with _start(settings, provider, snaptrade) as api:
        [watchlist] = api.get("/api/portfolios").json()
        watch = watchlist["id"]

        for t in ("aapl", "MSFT", "VOD.L"):
            assert api.post(f"/api/portfolios/{watch}/tickers", json={"ticker": t}).status_code == 201
        assert api.post(f"/api/portfolios/{watch}/tickers", json={"ticker": "ZZZZ"}).status_code == 422
        assert api.put(f"/api/portfolios/{watch}/favourites/MSFT").status_code == 200

        refresh = api.post("/api/market-data/refresh", json={"extra_tickers": []}).json()
        assert refresh["status"] == "completed" and refresh["tickers_requested"] == 3

        # Broker accounts: set up SnapTrade (accounts listed first, then each account's positions).
        assert api.get("/api/brokers/snaptrade/settings").json() == {
            "configured": False, "personal": None, "client_id": None, "user_id": None,
            "consumer_key_hint": None, "user_secret_hint": None}
        setup = api.put("/api/brokers/snaptrade/settings", json=snaptrade.credentials())
        assert setup.status_code == 200 and setup.json()["errors"] == []
        assert snaptrade.calls == ["/accounts/all", "/accounts/acc-1/positions/all", "/accounts/acc-2/positions/all"]
        accounts = {a["id"]: a for a in api.get("/api/brokers/accounts").json()["accounts"]}
        assert accounts["acc-1"]["tickers"] == ["AAPL"] and accounts["acc-2"]["tickers"] == ["VOD.L"]

        us = api.get("/api/brokers/accounts/acc-1/positions").json()
        rows = {r["symbol"]: r for r in us["positions"]}
        assert rows["AAPL"]["price_source"] == "market" and rows["AAPL"]["market_value"] == 1000.0
        assert rows["AAPL"]["unrealised_pnl"] == 95.0 and rows["AAPL"]["daily_pnl"] == 10.0
        option = rows["AAPL  261218C00240000"]
        assert option["price_source"] == "broker" and option["market_value"] == 550.0 and option["unrealised_pnl"] == 150.0
        [usd] = us["totals"]
        assert usd["market_value"] == 1550.0 and usd["incomplete"] is True  # the option has no daily change

        # The London holding: pounds at the broker, pence in market data -> converted.
        [vod] = api.get("/api/brokers/accounts/acc-2/positions").json()["positions"]
        assert vod["ticker"] == "VOD.L" and vod["currency"] == "GBP" and vod["price_source"] == "market"
        assert vod["current_price"] == 0.7 and vod["market_value"] == 700.0 and vod["daily_pnl"] == -10.0

        # Strategy on a broker account's tickers, lookback 10.
        account_tickers = accounts["acc-1"]["tickers"] + accounts["acc-2"]["tickers"]
        before = api.post("/api/strategies/mean_reversion/run",
                          json={"tickers": account_tickers, "config": {"lookback_days": 10}, "instance_id": "pane-wf"}).json()
        assert {r["ticker"]: r["signal"] for r in before["results"]}["AAPL"] is None  # baseline: no signal
        provider.set_quote("AAPL", 95.0, previous_close=100.0, timestamp=now + timedelta(seconds=1))
        assert api.post("/api/market-data/refresh").json()["status"] == "completed"
        run = api.post("/api/strategies/mean_reversion/run",
                       json={"tickers": account_tickers, "config": {"lookback_days": 10}, "instance_id": "pane-wf"}).json()
        results = {r["ticker"]: r for r in run["results"]}
        assert results["AAPL"]["status"] == "OK" and results["AAPL"]["signal"] == "BUY" and results["AAPL"]["is_new_signal"]
        assert results["AAPL"]["metrics"]["mean"] == pytest.approx(100.0)
        assert results["AAPL"]["metrics"]["z_score"] == pytest.approx(-2.5)
        assert results["VOD.L"]["status"] == "INSUFFICIENT_DATA"  # no history in the fake provider

        snapshot = {
            "portfolios": api.get("/api/portfolios").json(),
            "accounts": api.get("/api/brokers/accounts").json(),
            "positions": api.get("/api/brokers/accounts/acc-1/positions").json(),
            "signals": api.get("/api/strategies/signals", params={"instance_id": "pane-wf"}).json()["items"],
        }
        assert len(snapshot["signals"]) == 1

    # The credentials file is private to the owner.
    secret_file = data_dir / "config" / "snaptrade.json"
    assert secret_file.stat().st_mode & 0o777 == 0o600 and (data_dir / "config").stat().st_mode & 0o777 == 0o700

    # -- 16-18: restart; everything is intact ------------------------------------
    offline = FakeSnapTrade()  # a SnapTrade that knows nothing: the cache is used, no calls are made
    with _start(settings, FakeProvider(), offline) as api:  # new provider: no network, cache only
        assert api.get("/api/portfolios").json() == snapshot["portfolios"]
        assert api.get("/api/brokers/accounts").json() == snapshot["accounts"]
        assert api.get("/api/brokers/accounts/acc-1/positions").json() == snapshot["positions"]
        assert offline.calls == []
        status = api.get("/api/brokers/snaptrade/settings").json()
        assert status == {"configured": True, "personal": False, "client_id": snaptrade.client_id, "user_id": snaptrade.user_id,
                          "consumer_key_hint": "9876", "user_secret_hint": "4321"}
        assert api.get("/api/strategies/signals", params={"instance_id": "pane-wf"}).json()["items"] == snapshot["signals"]
        quotes = api.get(f"/api/portfolios/{watch}/quotes").json()["rows"]
        assert [(q["ticker"], q["price"], q["favourite"]) for q in quotes] == [
            ("AAPL", 95.0, False), ("MSFT", 401.0, True), ("VOD.L", 70.0, False),
        ]
        # A refresh where the provider knows nothing keeps the last prices, marked stale.
        failed = api.post("/api/market-data/refresh").json()
        assert failed["status"] == "failed" and failed["tickers_failed"] == 3
        quotes = api.get(f"/api/portfolios/{watch}/quotes").json()["rows"]
        assert [(q["price"], q["stale"]) for q in quotes] == [(95.0, True), (401.0, True), (70.0, True)]

    # -- Backup and recovery --------------------------------------------------------
    created = _backup_script(data_dir, "create", "--reason", "qa")
    assert created.returncode == 0, created.stderr
    backup = next(p.name for p in (data_dir / "backups").iterdir() if p.name.endswith("-qa"))
    assert _backup_script(data_dir, "verify", backup).returncode == 0

    # Backups never contain the SnapTrade credentials or the broker cache.
    backup_files = {p.relative_to(data_dir / "backups" / backup).parts[0] for p in (data_dir / "backups" / backup).rglob("*")}
    assert "config" not in backup_files and "brokers" not in backup_files

    # Damage the portfolios file: the backend refuses to start and leaves it alone.
    portfolios_file = data_dir / "portfolios" / "portfolios.parquet"
    portfolios_file.write_bytes(b"not a parquet file")
    with pytest.raises(Exception, match="portfolios"):
        with _start(settings, FakeProvider()):
            pass
    assert portfolios_file.read_bytes() == b"not a parquet file"

    restored = _backup_script(data_dir, "restore", backup, "--yes")
    assert restored.returncode == 0, restored.stderr
    with _start(settings, FakeProvider()) as api:
        assert api.get("/api/portfolios").json() == snapshot["portfolios"]
        assert api.get("/api/brokers/accounts").json() == snapshot["accounts"]  # the cache is untouched by restore

