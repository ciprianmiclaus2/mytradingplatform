"""Broker (SnapTrade) API: settings, refresh, positions and error responses."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.fake_snaptrade import FakeSnapTrade, account, stock
from tests.fakes import FakeProvider


def _setup(client: TestClient, snaptrade: FakeSnapTrade) -> None:
    snaptrade.accounts = [account("acc-1", "Brokerage", value=1234.5)]
    snaptrade.positions = {"acc-1": [stock("AAPL", "10", "99", "90")]}
    assert client.put("/api/brokers/snaptrade/settings", json=snaptrade.credentials()).status_code == 200


def test_not_set_up(client: TestClient) -> None:
    assert client.get("/api/brokers/accounts").json() == {"configured": False, "accounts": [], "accounts_refreshed_at": None}
    for method, path in (("POST", "/api/brokers/refresh"), ("POST", "/api/brokers/accounts/x/refresh"),
                         ("GET", "/api/brokers/accounts/x/positions")):
        resp = client.request(method, path)
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "snaptrade_not_configured"


def test_settings_never_return_secrets(client: TestClient, fake_snaptrade: FakeSnapTrade) -> None:
    _setup(client, fake_snaptrade)
    text = client.get("/api/brokers/snaptrade/settings").text
    assert fake_snaptrade.user_secret not in text and fake_snaptrade.consumer_key not in text
    assert '"user_secret_hint":"4321"' in text and '"personal":false' in text


def test_rejected_credentials(client: TestClient, fake_snaptrade: FakeSnapTrade) -> None:
    resp = client.put("/api/brokers/snaptrade/settings", json=fake_snaptrade.credentials(consumer_key="wrong-key-1234"))
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "snaptrade_credentials_rejected"
    assert "Unable to verify signature" in resp.json()["error"]["message"]
    assert client.get("/api/brokers/snaptrade/settings").json()["configured"] is False


def test_account_pane_flow(client: TestClient, fake_snaptrade: FakeSnapTrade, fake_provider: FakeProvider) -> None:
    _setup(client, fake_snaptrade)
    listing = client.get("/api/brokers/accounts").json()
    [acc] = listing["accounts"]
    assert (acc["name"], acc["number"], acc["net_value"], acc["tickers"]) == ("Brokerage", "****1234", 1234.5, ["AAPL"])
    assert listing["accounts_refreshed_at"] is not None

    # No market price yet: the broker's price is used.
    first = client.get("/api/brokers/accounts/acc-1/positions").json()
    assert first["positions"][0]["price_source"] == "broker" and first["positions"][0]["market_value"] == 990.0

    # The pane's refresh button: fresh positions from SnapTrade, valued with the market price.
    fake_provider.set_quote("AAPL", 100.0, previous_close=98.0)
    client.post("/api/market-data/refresh")
    fake_snaptrade.positions["acc-1"] = [stock("AAPL", "12", "99", "90")]
    fake_snaptrade.calls.clear()
    refreshed = client.post("/api/brokers/accounts/acc-1/refresh").json()
    assert fake_snaptrade.calls == ["/accounts/all", "/accounts/acc-1/positions/all"]
    [row] = refreshed["positions"]
    assert (row["quantity"], row["price_source"], row["market_value"], row["daily_pnl"]) == (12.0, "market", 1200.0, 24.0)
    assert refreshed["account"]["positions_refreshed_at"] is not None


def test_snaptrade_errors_reach_the_ui(client: TestClient, fake_snaptrade: FakeSnapTrade) -> None:
    _setup(client, fake_snaptrade)
    fake_snaptrade.fail("/accounts/acc-1/positions/all", 429, {"detail": "throttled"}, {"Retry-After": "12"})
    limited = client.post("/api/brokers/accounts/acc-1/refresh")
    assert limited.status_code == 429 and "Try again in 12 seconds" in limited.json()["error"]["message"]

    fake_snaptrade.fail("/accounts/all", 401, {"detail": "Invalid userID or userSecret provided"})
    rejected = client.post("/api/brokers/refresh")
    assert rejected.status_code == 502 and rejected.json()["error"]["code"] == "snaptrade_auth_failed"
    # The cached positions are still shown.
    assert client.get("/api/brokers/accounts/acc-1/positions").json()["positions"][0]["quantity"] == 10.0

    del fake_snaptrade.failures["/accounts/all"]
    fake_snaptrade.accounts = []
    gone = client.post("/api/brokers/accounts/acc-1/refresh")
    assert gone.status_code == 404 and "no longer listed" in gone.json()["error"]["message"]


def test_disconnect(client: TestClient, fake_snaptrade: FakeSnapTrade) -> None:
    _setup(client, fake_snaptrade)
    assert client.delete("/api/brokers/snaptrade/settings").status_code == 204
    assert client.get("/api/brokers/accounts").json()["configured"] is False
    assert client.get("/api/brokers/snaptrade/settings").json()["configured"] is False


def test_personal_api_key_setup(settings, fake_provider: FakeProvider) -> None:  # type: ignore[no-untyped-def]
    from app.main import create_app

    personal = FakeSnapTrade(personal=True)
    personal.accounts = [account("acc-1", "Brokerage")]
    personal.positions = {"acc-1": [stock("AAPL", "10", "99", "90")]}
    with TestClient(create_app(settings, provider=fake_provider, snaptrade=personal.factory)) as client:
        # Blank user fields, as the dialog sends them, mean a Personal key.
        body = {"client_id": personal.client_id, "consumer_key": personal.consumer_key, "user_id": "", "user_secret": ""}
        setup = client.put("/api/brokers/snaptrade/settings", json=body)
        assert setup.status_code == 200 and [a["id"] for a in setup.json()["accounts"]] == ["acc-1"]
        assert client.get("/api/brokers/snaptrade/settings").json() == {
            "configured": True, "personal": True, "client_id": personal.client_id, "user_id": None,
            "consumer_key_hint": "9876", "user_secret_hint": None}
        assert client.post("/api/brokers/accounts/acc-1/refresh").json()["positions"][0]["quantity"] == 10.0

        half = client.put("/api/brokers/snaptrade/settings", json={**body, "user_id": "someone"})
        assert half.status_code == 422 and "or neither" in half.text
