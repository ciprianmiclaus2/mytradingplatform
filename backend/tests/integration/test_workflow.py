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
from tests.fakes import FakeProvider

ROOT = Path(__file__).resolve().parents[3]


def _start(settings: Settings, provider: FakeProvider) -> TestClient:
    return TestClient(create_app(settings, provider=provider), raise_server_exceptions=False)


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

    # -- 1-13: the workflow from the plan ---------------------------------------
    with _start(settings, provider) as api:
        portfolios = {p["type"]: p for p in api.get("/api/portfolios").json()}
        watch, pos = portfolios["watchlist"]["id"], portfolios["positions"]["id"]

        for t in ("aapl", "MSFT", "VOD.L"):
            assert api.post(f"/api/portfolios/{watch}/tickers", json={"ticker": t}).status_code == 201
        assert api.post(f"/api/portfolios/{watch}/tickers", json={"ticker": "ZZZZ"}).status_code == 422
        assert api.put(f"/api/portfolios/{watch}/favourites/MSFT").status_code == 200

        refresh = api.post("/api/market-data/refresh", json={"extra_tickers": []}).json()
        assert refresh["status"] == "completed" and refresh["tickers_requested"] == 3

        aapl = api.post(f"/api/portfolios/{pos}/positions",
                        json={"ticker": "AAPL", "quantity": "10", "entry_price": "90.5"}).json()
        api.post(f"/api/portfolios/{pos}/positions", json={"ticker": "VOD.L", "quantity": "1000", "entry_price": "60"})
        msft = api.post(f"/api/portfolios/{pos}/positions", json={"ticker": "MSFT", "quantity": "2", "entry_price": "350"}).json()
        assert api.post(f"/api/positions/{msft['id']}/close", json={"exit_price": "410"}).status_code == 200

        listing = api.get(f"/api/portfolios/{pos}/positions").json()
        totals = {t["currency"]: t for t in listing["totals"]}
        assert set(totals) == {"GBp", "USD"}  # never combined
        assert totals["USD"]["market_value"] == 1000.0 and totals["USD"]["unrealised_pnl"] == 95.0
        assert totals["USD"]["realised_pnl"] == 120.0
        assert totals["GBp"]["market_value"] == 70000.0 and totals["GBp"]["daily_pnl"] == -1000.0

        # Strategy on the positions portfolio (open positions only), lookback 10.
        positions_tickers = api.get(f"/api/portfolios/{pos}").json()["tickers"]
        assert positions_tickers == ["AAPL", "VOD.L"]
        provider.set_quote("AAPL", 95.0, previous_close=100.0, timestamp=now + timedelta(seconds=1))
        assert api.post("/api/market-data/refresh").json()["status"] == "completed"
        run = api.post("/api/strategies/mean_reversion/run",
                       json={"tickers": positions_tickers, "config": {"lookback_days": 10}, "instance_id": "pane-wf"}).json()
        results = {r["ticker"]: r for r in run["results"]}
        assert results["AAPL"]["status"] == "OK" and results["AAPL"]["signal"] == "BUY"
        assert results["AAPL"]["metrics"]["mean"] == pytest.approx(100.0)
        assert results["AAPL"]["metrics"]["z_score"] == pytest.approx(-2.5)
        assert results["VOD.L"]["status"] == "INSUFFICIENT_DATA"  # no history in the fake provider

        snapshot = {
            "portfolios": api.get("/api/portfolios").json(),
            "positions": api.get(f"/api/portfolios/{pos}/positions").json(),
            "signals": api.get("/api/strategies/signals", params={"instance_id": "pane-wf"}).json()["items"],
        }
        assert len(snapshot["signals"]) == 1

    # -- 16-18: restart; everything is intact ------------------------------------
    with _start(settings, FakeProvider()) as api:  # new provider: no network, cache only
        assert api.get("/api/portfolios").json() == snapshot["portfolios"]
        assert api.get(f"/api/portfolios/{pos}/positions").json() == snapshot["positions"]
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

    # Damage the positions file: the backend refuses to start and leaves it alone.
    positions_file = data_dir / "positions" / "positions.parquet"
    positions_file.write_bytes(b"not a parquet file")
    with pytest.raises(Exception, match="positions"):
        with _start(settings, FakeProvider()):
            pass
    assert positions_file.read_bytes() == b"not a parquet file"

    restored = _backup_script(data_dir, "restore", backup, "--yes")
    assert restored.returncode == 0, restored.stderr
    with _start(settings, FakeProvider()) as api:
        restored_positions = api.get(f"/api/portfolios/{pos}/positions").json()["positions"]
        assert [(p["ticker"], p["status"], p["quantity"]) for p in restored_positions] == [
            (p["ticker"], p["status"], p["quantity"]) for p in snapshot["positions"]["positions"]
        ]
        assert api.get("/api/portfolios").json() == snapshot["portfolios"]

