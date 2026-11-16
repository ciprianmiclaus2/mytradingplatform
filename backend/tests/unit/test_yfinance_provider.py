"""yfinance normalisation, using stubbed yfinance objects (no network)."""

from __future__ import annotations

import time
from datetime import UTC, date, datetime
from typing import Any

import pandas as pd
import pytest
from yfinance.exceptions import YFPricesMissingError, YFTzMissingError

from app.market_data.base import NoPriceDataError, ProviderError
from app.market_data.providers import yfinance_provider as yp
from app.market_data.providers.registry import available_providers, create_provider
from app.market_data.providers.yfinance_provider import YFinanceProvider

# -- stubs ----------------------------------------------------------------------------


class HTTPError(Exception):
    def __init__(self, status: int) -> None:
        super().__init__(f"HTTP Error {status}")
        self.response = type("R", (), {"status_code": status})()


def history_frame(rows: dict[str, tuple[float, float]], tz: str = "America/New_York") -> pd.DataFrame:
    index = pd.DatetimeIndex([pd.Timestamp(d, tz=tz) for d in rows], name="Date")
    return pd.DataFrame(
        {
            "Open": [c for c, _ in rows.values()],
            "Close": [c for c, _ in rows.values()],
            "Adj Close": [a for _, a in rows.values()],
            "Volume": [1000] * len(rows),
        },
        index=index,
    )


class StubTicker:
    frame: Any = None
    history_error: BaseException | None = None
    metadata: dict[str, Any] = {"currency": "USD"}
    infos: dict[str, Any] = {}
    calls: list[dict[str, Any]] = []
    delay: float = 0

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol

    def history(self, **kwargs: Any) -> Any:
        StubTicker.calls.append(kwargs)
        if StubTicker.history_error:
            raise StubTicker.history_error
        return StubTicker.frame

    def get_history_metadata(self) -> dict[str, Any]:
        return StubTicker.metadata

    def get_info(self) -> dict[str, Any]:
        if StubTicker.delay:
            time.sleep(StubTicker.delay)
        info = StubTicker.infos.get(self.symbol)
        if isinstance(info, BaseException):
            raise info
        return info or {"trailingPegRatio": None}


class StubSearch:
    quotes: list[dict[str, Any]] = []
    error: BaseException | None = None

    def __init__(self, query: str, **kwargs: Any) -> None:
        if StubSearch.error:
            raise StubSearch.error
        self.quotes = StubSearch.quotes


@pytest.fixture(autouse=True)
def stub_yfinance(monkeypatch: pytest.MonkeyPatch) -> None:
    StubTicker.frame, StubTicker.history_error, StubTicker.delay = None, None, 0
    StubTicker.metadata, StubTicker.infos, StubTicker.calls = {"currency": "USD"}, {}, []
    StubSearch.quotes, StubSearch.error = [], None
    monkeypatch.setattr(yp.yf, "Ticker", StubTicker)
    monkeypatch.setattr(yp.yf, "Search", StubSearch)


@pytest.fixture
def provider() -> YFinanceProvider:
    return YFinanceProvider(timeout=2)


# -- registry ------------------------------------------------------------------------------


def test_registry_creates_yfinance_and_rejects_unknown() -> None:
    assert available_providers() == ["yfinance"]
    assert isinstance(create_provider("yfinance", 5), YFinanceProvider)
    with pytest.raises(ValueError, match="Unknown market data provider 'bloomberg'"):
        create_provider("bloomberg", 5)


# -- search --------------------------------------------------------------------------------


def test_search_normalises_and_filters_derivatives(provider: YFinanceProvider) -> None:
    StubSearch.quotes = [
        {"symbol": "AAPL", "shortname": "Apple", "longname": "Apple Inc.", "exchange": "NMS",
         "exchDisp": "NASDAQ", "quoteType": "EQUITY"},
        {"symbol": "SAAPL=F", "shortname": "Apple futures", "exchange": "CME", "quoteType": "FUTURE"},
        {"symbol": "spy", "shortname": "SPDR S&P 500", "exchange": "PCX", "quoteType": "etf"},
        {"shortname": "no symbol", "quoteType": "EQUITY"},
    ]
    results = provider.search_ticker("apple")
    assert [r.model_dump() for r in results] == [
        {"ticker": "AAPL", "name": "Apple Inc.", "exchange": "NASDAQ", "currency": None,
         "instrument_type": "EQUITY", "provider": "yfinance"},
        {"ticker": "SPY", "name": "SPDR S&P 500", "exchange": "PCX", "currency": None,
         "instrument_type": "ETF", "provider": "yfinance"},
    ]


def test_search_failure_is_provider_error(provider: YFinanceProvider) -> None:
    StubSearch.error = ConnectionError("down")
    with pytest.raises(ProviderError, match="Ticker search failed"):
        provider.search_ticker("apple")


# -- history -------------------------------------------------------------------------------


def test_history_normalises_bars(provider: YFinanceProvider) -> None:
    StubTicker.frame = history_frame(
        {"2026-11-12": (354.88, 354.0), "2026-11-13": (356.27, 355.5), "2026-11-14": (float("nan"), 1.0)}
    )
    result = provider.get_historical_prices("AAPL", date(2026, 11, 12), date(2026, 11, 14))

    assert StubTicker.calls[0]["start"] == "2026-11-12"
    assert StubTicker.calls[0]["end"] == "2026-11-15"  # exclusive end
    assert StubTicker.calls[0]["auto_adjust"] is False
    assert [(b.trading_date, b.close, b.adjusted_close, b.currency, b.provider) for b in result.bars] == [
        (date(2026, 11, 12), 354.88, 354.0, "USD", "yfinance"),
        (date(2026, 11, 13), 356.27, 355.5, "USD", "yfinance"),
    ]  # NaN close dropped


def test_history_session_date_uses_exchange_timezone(provider: YFinanceProvider) -> None:
    # Tokyo midnight is the previous day in UTC; the session date must stay local.
    StubTicker.frame = history_frame({"2026-11-13": (100.0, 100.0)}, tz="Asia/Tokyo")
    result = provider.get_historical_prices("7203.T", date(2026, 11, 13), date(2026, 11, 13))
    assert result.bars[0].trading_date == date(2026, 11, 13)


def test_history_drops_bars_outside_requested_range(provider: YFinanceProvider) -> None:
    StubTicker.frame = history_frame({"2026-11-11": (1.0, 1.0), "2026-11-12": (2.0, 2.0)})
    result = provider.get_historical_prices("AAPL", date(2026, 11, 12), date(2026, 11, 12))
    assert [b.trading_date for b in result.bars] == [date(2026, 11, 12)]


@pytest.mark.parametrize(
    "error",
    [YFPricesMissingError("ZZZ", ""), YFTzMissingError("ZZZ")],
)
def test_history_no_data_is_empty_result(provider: YFinanceProvider, error: BaseException) -> None:
    StubTicker.history_error = error
    assert provider.get_historical_prices("ZZZ", date(2026, 11, 1), date(2026, 11, 5)).bars == []


def test_history_empty_frame_is_empty_result(provider: YFinanceProvider) -> None:
    StubTicker.frame = pd.DataFrame()
    assert provider.get_historical_prices("AAPL", date(2026, 11, 1), date(2026, 11, 5)).bars == []


def test_history_network_failure_is_provider_error(provider: YFinanceProvider) -> None:
    StubTicker.history_error = ConnectionError("Failed to connect")
    with pytest.raises(ProviderError, match="History request for AAPL failed"):
        provider.get_historical_prices("AAPL", date(2026, 11, 1), date(2026, 11, 5))


def test_history_without_currency_is_provider_error(provider: YFinanceProvider) -> None:
    StubTicker.frame = history_frame({"2026-11-12": (1.0, 1.0)})
    StubTicker.metadata = {}
    with pytest.raises(ProviderError, match="no currency"):
        provider.get_historical_prices("AAPL", date(2026, 11, 12), date(2026, 11, 12))


# -- current prices ------------------------------------------------------------------------------

AAPL_INFO = {
    "regularMarketPrice": 356.27,
    "regularMarketTime": 1794603601,  # 2026-11-13 21:00:01 UTC = 16:00:01 New York
    "regularMarketPreviousClose": 354.88,
    "currency": "USD",
    "exchangeTimezoneName": "America/New_York",
    "exchangeDataDelayedBy": 15,
    "quoteSourceName": "Nasdaq Real Time Price",
}


def test_quote_normalisation(provider: YFinanceProvider) -> None:
    StubTicker.infos = {"AAPL": AAPL_INFO}
    q = provider.get_current_price("AAPL")
    assert q.price == 356.27 and q.previous_close == 354.88 and q.currency == "USD"
    assert q.timestamp == datetime(2026, 11, 13, 21, 0, 1, tzinfo=UTC)
    assert q.trading_date == date(2026, 11, 13)
    assert q.delayed is True  # Yahoo reports a delay even when it says "Real Time"
    assert q.provider == "yfinance" and q.fetched_at.tzinfo is not None


def test_quote_never_claims_real_time(provider: YFinanceProvider) -> None:
    StubTicker.infos = {"AAPL": {**AAPL_INFO, "exchangeDataDelayedBy": 0}}
    assert provider.get_current_price("AAPL").delayed is None


def test_quote_session_date_late_evening_asia(provider: YFinanceProvider) -> None:
    # 2026-11-16 01:00 UTC is 10:00 on 2026-11-16 in Tokyo, while still 11-15 in New York.
    info = {**AAPL_INFO, "regularMarketTime": int(datetime(2026, 11, 16, 1, tzinfo=UTC).timestamp()),
            "exchangeTimezoneName": "Asia/Tokyo", "currency": "JPY"}
    StubTicker.infos = {"7203.T": info}
    assert provider.get_current_price("7203.T").trading_date == date(2026, 11, 16)


def test_quote_without_price_is_no_data(provider: YFinanceProvider) -> None:
    with pytest.raises(NoPriceDataError):
        provider.get_current_price("ZZZZ")  # info is {"trailingPegRatio": None}


def test_quote_404_is_no_data(provider: YFinanceProvider) -> None:
    StubTicker.infos = {"ZZZZ": HTTPError(404)}
    with pytest.raises(NoPriceDataError):
        provider.get_current_price("ZZZZ")


@pytest.mark.parametrize("error", [HTTPError(500), ConnectionError("down"), TimeoutError()])
def test_quote_failures_are_provider_errors(provider: YFinanceProvider, error: BaseException) -> None:
    StubTicker.infos = {"AAPL": error}
    with pytest.raises(ProviderError) as info:
        provider.get_current_price("AAPL")
    assert not isinstance(info.value, NoPriceDataError)


def test_quote_without_currency_is_provider_error(provider: YFinanceProvider) -> None:
    StubTicker.infos = {"AAPL": {**AAPL_INFO, "currency": None}}
    with pytest.raises(ProviderError, match="no currency"):
        provider.get_current_price("AAPL")


def test_current_prices_partial_success(provider: YFinanceProvider) -> None:
    StubTicker.infos = {"AAPL": AAPL_INFO, "BAD": ConnectionError("down")}
    results = provider.get_current_prices(["AAPL", "BAD", "NONE"])
    assert results["AAPL"].price == 356.27  # type: ignore[union-attr]
    assert type(results["BAD"]) is ProviderError
    assert isinstance(results["NONE"], NoPriceDataError)


def test_current_prices_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    StubTicker.infos = {"SLOW": AAPL_INFO}
    StubTicker.delay = 1.0
    provider = YFinanceProvider(timeout=0.2)
    start = time.monotonic()
    results = provider.get_current_prices(["SLOW"])
    assert time.monotonic() - start < 0.9
    assert isinstance(results["SLOW"], ProviderError) and "timed out" in str(results["SLOW"])
