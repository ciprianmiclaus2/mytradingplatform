"""SnapTrade client, instrument mapping, valuation, credential storage and the broker service."""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from app.brokers.credentials import CredentialStore
from app.brokers.mapping import market_ticker, to_position
from app.brokers.models import BrokerPosition, SnapTradeCredentials
from app.brokers.snaptrade import (
    SnapTradeAuthError,
    SnapTradeClient,
    SnapTradeError,
    SnapTradeNotFoundError,
    SnapTradeRateLimitedError,
    sign,
)
from app.brokers.valuation import currency_totals, live_quote, position_view
from app.market_data.models import LatestPrice
from app.persistence.errors import CorruptFileError
from tests.fake_snaptrade import BASE_URL, FakeSnapTrade, account, stock

NOW = datetime(2026, 11, 16, 15, tzinfo=UTC)


def creds(fake: FakeSnapTrade, **overrides: str) -> SnapTradeCredentials:
    return SnapTradeCredentials(**fake.credentials(**overrides))


# -- signing and client -----------------------------------------------------------------------------


def test_signature_matches_the_documented_algorithm() -> None:
    # Expected value computed independently with openssl from SnapTrade's documented payload:
    #   printf '%s' '{"content":null,"path":"/accounts/all","query":"clientId=C&timestamp=1700000000&userId=U&userSecret=S"}' \
    #     | openssl dgst -sha256 -hmac KEY -binary | base64
    query = "clientId=C&timestamp=1700000000&userId=U&userSecret=S"
    assert sign("KEY", "/accounts/all", query) == "X8XDx666RwGFDB6NHZefU/JoCMIbTbZQRLyOMEzGZAM="
    assert sign("KEY", "/accounts/all", query, {}) == sign("KEY", "/accounts/all", query)  # {} signs as null
    assert sign("OTHER", "/accounts/all", query) != sign("KEY", "/accounts/all", query)


def test_personal_key_signature_has_no_user() -> None:
    # openssl, as above, with payload {"content":null,"path":"/accounts/all","query":"clientId=C&timestamp=1700000000"}
    assert sign("KEY", "/accounts/all", "clientId=C&timestamp=1700000000") == "fUqlR8NT/YvstbY0OrXvtVt9y6c8HYFSNTSnRnldGF4="


def test_personal_key_requests_carry_no_user() -> None:
    fake = FakeSnapTrade(personal=True)
    fake.accounts = [account("a1", "Main")]
    fake.positions = {"a1": [stock("AAPL", "2", "100", "90")]}
    personal = SnapTradeCredentials(**fake.credentials())
    assert personal.personal and personal.user_id is None and personal.user_secret is None
    client = fake.factory(personal)
    assert [a["id"] for a in client.list_accounts()] == ["a1"]
    assert client.account_positions("a1")[0][0]["units"] == "2"
    # The fake rejects a user on a Personal key, so commercial credentials fail there.
    with pytest.raises(SnapTradeError, match="must not send userId"):
        fake.factory(creds(FakeSnapTrade())).list_accounts()


@pytest.mark.parametrize(
    ("fields", "ok"),
    [
        ({"user_id": "", "user_secret": "  "}, True),  # blanks: Personal key
        ({}, True),
        ({"user_id": "u", "user_secret": "s"}, True),
        ({"user_id": "u"}, False),
        ({"user_secret": "s", "user_id": " "}, False),
    ],
)
def test_user_id_and_secret_go_together(fields: dict, ok: bool) -> None:
    from pydantic import ValidationError

    if ok:
        c = SnapTradeCredentials(client_id="c", consumer_key="k", **fields)
        assert c.personal is ("user_id" not in fields or not fields["user_id"].strip())
    else:
        with pytest.raises(ValidationError, match="both the user ID and the user secret, or neither"):
            SnapTradeCredentials(client_id="c", consumer_key="k", **fields)


def test_client_lists_accounts_and_positions() -> None:
    fake = FakeSnapTrade()
    fake.accounts = [account("a1", "Main")]
    fake.positions = {"a1": [stock("AAPL", "2", "100", "90")]}
    client = fake.factory(creds(fake))
    assert [a["id"] for a in client.list_accounts()] == ["a1"]
    items, as_of = client.account_positions("a1")
    assert items[0]["units"] == "2" and as_of == fake.as_of
    assert fake.calls == ["/accounts/all", "/accounts/a1/positions/all"]


def test_client_sends_the_signed_query_unchanged() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"results": []})

    c = SnapTradeCredentials(client_id="c id", consumer_key="k", user_id="u+1", user_secret="s/=&")
    SnapTradeClient(c, base_url=BASE_URL, transport=httpx.MockTransport(handler), clock=lambda: 1700000000.9).list_accounts()
    [request] = seen
    query = request.url.query.decode()
    assert query == "clientId=c+id&timestamp=1700000000&userId=u%2B1&userSecret=s%2F%3D%26"
    assert request.headers["Signature"] == sign("k", "/accounts/all", query)


@pytest.mark.parametrize(
    ("status", "body", "headers", "error", "text"),
    [
        (401, {"default_detail": "Unable to verify signature sent", "default_code": 1076}, {}, SnapTradeAuthError,
         "Unable to verify signature sent"),
        (403, {"detail": "Feature not enabled", "default_code": 1141}, {}, SnapTradeAuthError, "Feature not enabled"),
        (404, {"default_detail": "Account not found"}, {}, SnapTradeNotFoundError, "Account not found"),
        (429, {"detail": "Request was throttled.", "status_code": 429, "code": "0000"}, {"Retry-After": "7"},
         SnapTradeRateLimitedError, "Try again in 7 seconds"),
        (402, {"detail": "Connection is disabled", "code": "3003"}, {}, SnapTradeError, "Reconnect it in SnapTrade"),
        (503, {"detail": "Brokerage unavailable", "status_code": 503, "code": "x"}, {}, SnapTradeError, "503"),
    ],
)
def test_client_errors(status: int, body: dict, headers: dict, error: type, text: str) -> None:
    fake = FakeSnapTrade()
    fake.fail("/accounts/all", status, body, headers)
    with pytest.raises(error, match=text):
        fake.factory(creds(fake)).list_accounts()


def test_client_network_failures_never_expose_the_secret(caplog: pytest.LogCaptureFixture) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"connection refused for {request.url}")

    def garbage(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>")

    fake = FakeSnapTrade()
    c = creds(fake)
    caplog.set_level(logging.DEBUG)
    for transport, message in ((broken, "could not be reached"), (garbage, "invalid response")):
        with pytest.raises(SnapTradeError, match=message) as exc:
            SnapTradeClient(c, base_url=BASE_URL, transport=httpx.MockTransport(transport)).list_accounts()
        assert fake.user_secret not in str(exc.value) and exc.value.__cause__ is None or transport is garbage
    fake.fail("/accounts/all", 500, {"detail": "boom"})
    with pytest.raises(SnapTradeError):
        fake.factory(c).list_accounts()
    assert fake.user_secret not in caplog.text and fake.consumer_key not in caplog.text


def test_client_rejects_unexpected_shapes() -> None:
    client = SnapTradeClient(SnapTradeCredentials(client_id="c", consumer_key="k", user_id="u", user_secret="s"),
                             base_url=BASE_URL, transport=httpx.MockTransport(lambda r: httpx.Response(200, json=[1])))
    with pytest.raises(SnapTradeError, match="unexpected account list"):
        client.list_accounts()
    with pytest.raises(SnapTradeError, match="unexpected positions list"):
        client.account_positions("a")


# -- instrument mapping -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("instrument", "ticker"),
    [
        ({"kind": "stock", "symbol": "AAPL", "raw_symbol": "AAPL", "exchange": "XNAS", "currency": "USD"}, "AAPL"),
        ({"kind": "stock", "symbol": "BRK.B", "raw_symbol": "BRK.B", "exchange": "XNYS", "currency": "USD"}, "BRK-B"),
        ({"kind": "etf", "symbol": "VUSA.L", "raw_symbol": "VUSA", "exchange": "XLON", "currency": "GBP"}, "VUSA.L"),
        ({"kind": "stock", "symbol": "SHOP.TO", "raw_symbol": "SHOP", "exchange": "XTSE", "currency": "CAD"}, "SHOP.TO"),
        ({"kind": "stock", "symbol": "RCI.B.TO", "raw_symbol": "RCI.B", "exchange": "XTSE", "currency": "CAD"}, "RCI-B.TO"),
        ({"kind": "stock", "symbol": "SAP", "raw_symbol": "SAP", "exchange": "XETR", "currency": "EUR"}, "SAP.DE"),
        ({"kind": "stock", "symbol": "AAPL", "raw_symbol": "AAPL", "exchange": None, "currency": "USD"}, "AAPL"),
        ({"kind": "stock", "symbol": "XYZ.SW2", "raw_symbol": "XYZ", "exchange": "XQQQ", "currency": "CHF"}, "XYZ.SW2"),
        ({"kind": "stock", "symbol": "XYZ", "raw_symbol": "XYZ", "exchange": "XQQQ", "currency": "CHF"}, None),
        ({"kind": "crypto", "symbol": "BTC", "raw_symbol": "BTC", "currency": "USD"}, "BTC-USD"),
        ({"kind": "option", "symbol": "AAPL  261218C00240000", "raw_symbol": "AAPL", "exchange": "XNAS"}, None),
        ({"kind": "cash", "symbol": "USD", "raw_symbol": "USD"}, None),
        ({"kind": "stock", "symbol": "", "raw_symbol": None}, None),
    ],
)
def test_market_ticker(instrument: dict, ticker: str | None) -> None:
    assert market_ticker(instrument) == ticker


def test_to_position_parses_strings_and_skips_unusable_items() -> None:
    p = to_position("a", stock("AAPL  261218C00240000", "-2", "5.5", None, kind="option", multiplier=100))
    assert p is not None and p.units == Decimal("-2") and p.price == Decimal("5.5") and p.cost_basis is None
    assert p.multiplier == Decimal(100) and p.ticker is None and p.kind == "option"
    assert to_position("a", {"instrument": {"kind": "stock", "symbol": "X"}, "units": None}) is None
    assert to_position("a", {"units": "1"}) is None
    weird = to_position("a", {"instrument": {"kind": "stock", "symbol": "X"}, "units": "1", "price": "NaN", "cost_basis": "abc"})
    assert weird is not None and weird.price is None and weird.cost_basis is None and weird.multiplier == 1


# -- valuation -----------------------------------------------------------------------------------------


def _position(**overrides: object) -> BrokerPosition:
    fields: dict[str, object] = dict(account_id="a", symbol="AAPL", ticker="AAPL", description=None, kind="stock",
                                     units=Decimal(10), price=Decimal(99), cost_basis=Decimal("90.5"),
                                     multiplier=Decimal(1), currency="USD", cash_equivalent=False)
    return BrokerPosition(**(fields | overrides))  # type: ignore[arg-type]


def _quote(price: float, previous: float | None, currency: str = "USD") -> LatestPrice:
    return LatestPrice(ticker="AAPL", price=price, previous_close=previous, currency=currency, timestamp=NOW,
                       trading_date=NOW.date(), provider="fake", delayed=True, fetched_at=NOW,
                       daily_change=None if previous is None else price - previous, daily_change_pct=None, stale=False)


def test_valuation_prefers_the_live_quote() -> None:
    p = _position()
    view = position_view(p, live_quote(p, {"AAPL": _quote(100.0, 98.0)}))
    assert (view.current_price, view.price_source, view.market_value) == (100.0, "market", 1000.0)
    assert (view.cost_basis, view.unrealised_pnl, view.unrealised_pnl_pct) == (905.0, 95.0, pytest.approx(10.49723757))
    assert (view.daily_change, view.daily_pnl) == (2.0, 20.0)


def test_valuation_falls_back_to_the_broker_price() -> None:
    p = _position()
    for prices in ({}, {"AAPL": None}, {"AAPL": _quote(100.0, 98.0, currency="CAD")}):
        view = position_view(p, live_quote(p, prices), as_of=NOW)
        assert (view.current_price, view.price_source, view.price_timestamp) == (99.0, "broker", NOW)
        assert view.daily_pnl is None and view.market_value == 990.0
    no_price = position_view(_position(price=None, ticker=None), None)
    assert no_price.price_source is None and no_price.market_value is None and no_price.unrealised_pnl is None


def test_valuation_converts_pence_quotes_to_pounds() -> None:
    p = _position(ticker="VOD.L", currency="GBP", units=Decimal(1000), cost_basis=Decimal("0.6"))
    quote = live_quote(p, {"VOD.L": _quote(70.0, 71.0, currency="GBp")})
    assert quote is not None and quote.currency == "GBP" and quote.price == 0.7 and quote.previous_close == 0.71
    view = position_view(p, quote)
    assert (view.market_value, view.unrealised_pnl, view.daily_pnl) == (700.0, 100.0, -10.0)
    # A pence quote is never applied to a position in another currency.
    assert live_quote(_position(currency="EUR"), {"AAPL": _quote(70.0, 71.0, currency="GBp")}) is None


def test_options_use_the_multiplier_and_shorts_have_positive_cost_percent() -> None:
    option = position_view(_position(ticker=None, units=Decimal(-1), price=Decimal(5), cost_basis=Decimal(4),
                                     multiplier=Decimal(100)), None)
    assert (option.market_value, option.cost_basis, option.unrealised_pnl) == (-500.0, -400.0, -100.0)
    assert option.unrealised_pnl_pct == -25.0  # a short that lost money shows a loss


def test_currency_totals() -> None:
    views = [
        position_view(_position(), _quote(100.0, 98.0)),
        position_view(_position(symbol="OPT", ticker=None, price=Decimal(5), cost_basis=None), None),
        position_view(_position(symbol="VOD", ticker=None, currency="GBP", price=Decimal(2)), None),
        position_view(_position(symbol="CASH", ticker=None, currency=None), None),
    ]
    totals = {t.currency: t for t in currency_totals(views)}
    assert set(totals) == {"USD", "GBP"}  # never combined; no-currency rows are not totalled
    usd = totals["USD"]
    assert (usd.positions, usd.market_value, usd.cost_basis, usd.unrealised_pnl) == (2, 1050.0, 905.0, 95.0)
    assert usd.daily_pnl == 20.0 and usd.incomplete is True


# -- credentials ---------------------------------------------------------------------------------------


def test_credentials_are_stored_privately_and_never_returned(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path)
    assert store.load() is None and store.status().configured is False
    fake = FakeSnapTrade()
    store.save(creds(fake))
    assert store.path.stat().st_mode & 0o777 == 0o600 and store.directory.stat().st_mode & 0o777 == 0o700
    loaded = store.load()
    assert loaded is not None and loaded.user_secret.get_secret_value() == fake.user_secret
    status = store.status()
    assert status.configured and status.consumer_key_hint == "9876" and status.user_secret_hint == "4321"
    assert fake.user_secret not in status.model_dump_json() and fake.consumer_key not in repr(loaded)
    assert not list(store.directory.glob("*.tmp"))
    # Short secrets give no hint at all.
    store.save(SnapTradeCredentials(client_id="c", consumer_key="short", user_id="u", user_secret="tiny"))
    assert store.status().consumer_key_hint == ""
    assert store.delete() is True and store.load() is None and store.delete() is False


def test_personal_credentials_are_stored_without_a_user(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path)
    store.save(SnapTradeCredentials(client_id="cid", consumer_key="consumer-key-0001-9876"))
    loaded = store.load()
    assert loaded is not None and loaded.personal and loaded.user_secret is None
    status = store.status()
    assert (status.personal, status.user_id, status.user_secret_hint, status.consumer_key_hint) == (True, None, None, "9876")
    assert json.loads(store.path.read_text())["user_secret"] is None


def test_credentials_permissions_are_repaired_and_corruption_reported(tmp_path: Path) -> None:
    store = CredentialStore(tmp_path)
    store.save(creds(FakeSnapTrade()))
    store.path.chmod(0o644)
    assert store.load() is not None and store.path.stat().st_mode & 0o777 == 0o600
    store.path.write_text(json.dumps({"client_id": "only"}))
    with pytest.raises(CorruptFileError, match="set up SnapTrade again"):
        store.load()


# -- service ---------------------------------------------------------------------------------------------


@pytest.fixture
def snaptrade() -> FakeSnapTrade:
    fake = FakeSnapTrade()
    fake.accounts = [account("a1", "Main"), account("a2", "Second")]
    fake.positions = {"a1": [stock("AAPL", "1", "100", "90")], "a2": [stock("MSFT", "2", "400", "300")]}
    return fake


@pytest.fixture
def service(tmp_path: Path, snaptrade: FakeSnapTrade):  # type: ignore[no-untyped-def]
    from app.brokers.repository import BrokerRepository
    from app.brokers.service import BrokerService
    from app.persistence import open_persistence

    p = open_persistence(tmp_path / "data", lock_timeout=5, backup_retention=3, backup_on_startup=False)

    class NoPrices:
        def get_latest_prices(self, tickers: list[str]) -> dict:
            return {}

    return BrokerService(BrokerRepository(p.store), CredentialStore(tmp_path / "data"), NoPrices(),  # type: ignore[arg-type]
                         snaptrade.factory, clock=lambda: NOW)


def test_service_requires_setup(service) -> None:  # type: ignore[no-untyped-def]
    from app.brokers.service import SnapTradeNotConfiguredError

    assert service.accounts().configured is False and service.all_tickers() == []
    with pytest.raises(SnapTradeNotConfiguredError):
        service.refresh_all()
    with pytest.raises(SnapTradeNotConfiguredError):
        service.positions("a1")


def test_rejected_credentials_are_not_saved(service, snaptrade: FakeSnapTrade) -> None:  # type: ignore[no-untyped-def]
    from app.brokers.service import SnapTradeCredentialsRejectedError

    with pytest.raises(SnapTradeCredentialsRejectedError, match="Check the values you entered"):
        service.configure(creds(snaptrade, user_secret="wrong-secret"))
    assert service.status().configured is False


def test_refresh_lists_accounts_first_then_positions_per_account(service, snaptrade: FakeSnapTrade) -> None:  # type: ignore[no-untyped-def]
    result = service.configure(creds(snaptrade))
    assert snaptrade.calls == ["/accounts/all", "/accounts/a1/positions/all", "/accounts/a2/positions/all"]
    assert [a.name for a in result.accounts] == ["Main", "Second"] and result.errors == []
    assert result.accounts_refreshed_at == NOW and service.all_tickers() == ["AAPL", "MSFT"]
    account = service.positions("a1").account
    assert account.positions_refreshed_at == NOW and account.data_as_of == datetime(2026, 11, 16, 14, 30, tzinfo=UTC)

    snaptrade.calls.clear()
    snaptrade.positions["a1"] = [stock("NVDA", "3", "150", "100")]
    view = service.refresh_account("a1")
    assert snaptrade.calls == ["/accounts/all", "/accounts/a1/positions/all"]  # only this account's positions
    assert [p.symbol for p in view.positions] == ["NVDA"]
    assert [p.symbol for p in service.positions("a2").positions] == ["MSFT"]  # other accounts untouched


def test_partial_failure_and_removed_accounts(service, snaptrade: FakeSnapTrade) -> None:  # type: ignore[no-untyped-def]
    service.configure(creds(snaptrade))
    snaptrade.fail("/accounts/a2/positions/all", 503, {"detail": "Brokerage unavailable"})
    result = service.refresh_all()
    assert [(e.account_name, "Brokerage unavailable" in e.message) for e in result.errors] == [("Second", True)]
    assert [p.symbol for p in service.positions("a2").positions] == ["MSFT"]  # keeps the last good positions

    snaptrade.accounts = [account("a1", "Main")]  # a2 disconnected at the broker
    service.refresh_all()
    assert [a.id for a in service.accounts().accounts] == ["a1"] and service.all_tickers() == ["AAPL"]
    from app.schemas.errors import NotFoundError

    with pytest.raises(NotFoundError):
        service.positions("a2")
    with pytest.raises(NotFoundError, match="no longer listed"):
        service.refresh_account("a2")


def test_one_refresh_at_a_time(service, snaptrade: FakeSnapTrade) -> None:  # type: ignore[no-untyped-def]
    from app.brokers.service import BrokerRefreshInProgressError

    service.configure(creds(snaptrade))
    service._refreshing.acquire()
    try:
        with pytest.raises(BrokerRefreshInProgressError):
            service.refresh_all()
    finally:
        service._refreshing.release()
    assert service.refresh_all().errors == []
    assert isinstance(service._refreshing, type(threading.Lock()))


def test_disconnect_forgets_everything(service, snaptrade: FakeSnapTrade) -> None:  # type: ignore[no-untyped-def]
    service.configure(creds(snaptrade))
    service.disconnect()
    assert service.status().configured is False and service.accounts().accounts == []
    service.configure(creds(snaptrade))
    assert len(service.accounts().accounts) == 2
