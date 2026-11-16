from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.market_data.base import ProviderError
from app.market_data.cache import PRICE_HISTORY, HistoricalCache
from app.market_data.models import HistoryStatus, RefreshOutcome, TickerSearchResult
from app.market_data.service import MarketDataProviderUnavailable, MarketDataService
from app.persistence.derived import derived_registry
from app.persistence.parquet import ParquetStore
from tests.fakes import FIXED_NOW, FakeProvider, OtherFakeProvider

D = date
TODAY = FIXED_NOW.date()  # Monday 2026-11-16


def weekdays(start: date, end: date, base: float = 100.0) -> dict[date, float]:
    out, day, i = {}, start, 0
    while day <= end:
        if day.weekday() < 5:
            out[day] = base + i
            i += 1
        day += timedelta(days=1)
    return out


@pytest.fixture
def provider() -> FakeProvider:
    p = FakeProvider()
    p.set_closes("AAPL", weekdays(D(2026, 9, 1), TODAY))  # includes today's (incomplete) bar
    p.set_closes("MSFT", weekdays(D(2026, 9, 1), TODAY, base=400))
    return p


def make_service(store: ParquetStore, provider: FakeProvider, now: datetime = FIXED_NOW, threshold: int = 1000):  # type: ignore[no-untyped-def]
    clock = {"now": now}
    service = MarketDataService(provider, store, derived_registry, archive_threshold=threshold, clock=lambda: clock["now"])
    return service, clock


# -- search ------------------------------------------------------------------------------------


def test_search_passes_through_normalised_results(store: ParquetStore, provider: FakeProvider) -> None:
    provider.search_results = [TickerSearchResult(ticker="AAPL", name="Apple Inc.", exchange="NASDAQ",
                                                  currency=None, instrument_type="EQUITY", provider="fake")]
    service, _ = make_service(store, provider)
    assert service.search(" apple ")[0].ticker == "AAPL"


def test_search_provider_failure_is_reported(store: ParquetStore, provider: FakeProvider) -> None:
    provider.search_error = ProviderError("down")
    service, _ = make_service(store, provider)
    with pytest.raises(MarketDataProviderUnavailable):
        service.search("apple")


# -- history ---------------------------------------------------------------------------------------


def test_history_is_fetched_once_then_served_from_cache(store: ParquetStore, provider: FakeProvider) -> None:
    service, _ = make_service(store, provider)
    first = service.get_history(["AAPL"], D(2026, 11, 2), D(2026, 11, 13))["AAPL"]
    assert first.status is HistoryStatus.OK
    assert len(first.bars) == 10
    assert provider.history_calls == [("AAPL", D(2026, 11, 2), D(2026, 11, 13))]

    again = service.get_history(["AAPL"], D(2026, 11, 2), D(2026, 11, 13))["AAPL"]
    assert again.bars == first.bars
    assert len(provider.history_calls) == 1  # cache reused, no download


def test_only_missing_range_is_downloaded(store: ParquetStore, provider: FakeProvider) -> None:
    service, _ = make_service(store, provider)
    service.get_history(["AAPL"], D(2026, 11, 9), D(2026, 11, 13))
    result = service.get_history(["AAPL"], D(2026, 11, 2), D(2026, 11, 13))["AAPL"]
    assert provider.history_calls[-1] == ("AAPL", D(2026, 11, 2), D(2026, 11, 8))
    assert [b.trading_date for b in result.bars][:2] == [D(2026, 11, 2), D(2026, 11, 3)]
    assert len(result.bars) == 10


def test_current_session_is_never_cached_or_returned(store: ParquetStore, provider: FakeProvider) -> None:
    service, clock = make_service(store, provider)
    result = service.get_history(["AAPL"], D(2026, 11, 9), D(2026, 11, 30))["AAPL"]
    assert result.bars[-1].trading_date == D(2026, 11, 13)  # Friday; Monday 16th is today
    assert provider.history_calls == [("AAPL", D(2026, 11, 9), D(2026, 11, 15))]

    clock["now"] = FIXED_NOW + timedelta(days=1)  # next day: Monday is now complete
    result = service.get_history(["AAPL"], D(2026, 11, 9), D(2026, 11, 30))["AAPL"]
    assert result.bars[-1].trading_date == D(2026, 11, 16)
    assert provider.history_calls[-1] == ("AAPL", D(2026, 11, 16), D(2026, 11, 16))


def test_no_data_is_cached_and_not_refetched(store: ParquetStore, provider: FakeProvider) -> None:
    service, _ = make_service(store, provider)
    result = service.get_history(["NEWCO"], D(2026, 11, 2), D(2026, 11, 13))["NEWCO"]
    assert result.status is HistoryStatus.NO_DATA and result.bars == []
    service.get_history(["NEWCO"], D(2026, 11, 2), D(2026, 11, 13))
    assert len(provider.history_calls) == 1


def test_provider_failure_is_not_cached_as_empty(store: ParquetStore, provider: FakeProvider) -> None:
    service, _ = make_service(store, provider)
    service.get_history(["AAPL"], D(2026, 11, 9), D(2026, 11, 13))
    provider.history_failures["AAPL"] = ProviderError("Yahoo is down")

    result = service.get_history(["AAPL"], D(2026, 11, 2), D(2026, 11, 13))["AAPL"]

    assert result.status is HistoryStatus.ERROR and "Yahoo is down" in (result.error or "")
    assert len(result.bars) == 5  # previously cached data is intact and still returned
    assert HistoricalCache(store).coverage("AAPL", "fake") == [(D(2026, 11, 9), D(2026, 11, 13))]

    del provider.history_failures["AAPL"]  # provider recovers: the gap is fetched
    result = service.get_history(["AAPL"], D(2026, 11, 2), D(2026, 11, 13))["AAPL"]
    assert result.status is HistoryStatus.OK and len(result.bars) == 10


def test_failure_for_one_ticker_does_not_affect_others(store: ParquetStore, provider: FakeProvider) -> None:
    provider.history_failures["MSFT"] = ProviderError("timeout")
    service, _ = make_service(store, provider)
    results = service.get_history(["AAPL", "MSFT"], D(2026, 11, 9), D(2026, 11, 13))
    assert results["AAPL"].status is HistoryStatus.OK
    assert results["MSFT"].status is HistoryStatus.ERROR


def test_invalid_provider_prices_are_rejected_and_not_cached(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_closes("BAD", {D(2026, 11, 12): 10.0, D(2026, 11, 13): -1.0})
    service, _ = make_service(store, provider)
    result = service.get_history(["BAD"], D(2026, 11, 12), D(2026, 11, 13))["BAD"]
    assert result.status is HistoryStatus.ERROR and "invalid price" in (result.error or "")
    assert HistoricalCache(store).coverage("BAD", "fake") == []
    assert not list(store.resolve("market_data/close_prices").glob("*.parquet"))


def test_history_view_is_maintained(store: ParquetStore, provider: FakeProvider) -> None:
    service, _ = make_service(store, provider)
    service.get_history(["AAPL", "MSFT"], D(2026, 11, 9), D(2026, 11, 13))
    view = store.read(PRICE_HISTORY)
    assert view.num_rows == 10
    assert not derived_registry.is_stale(store, "price_history")


def test_closes_before_returns_last_n_sessions(store: ParquetStore, provider: FakeProvider) -> None:
    service, _ = make_service(store, provider)
    result = service.get_closes_before(["AAPL"], before=D(2026, 11, 16), sessions=20)["AAPL"]
    assert len(result.bars) == 20
    assert result.bars[-1].trading_date == D(2026, 11, 13)
    assert result.bars[0].trading_date == D(2026, 10, 19)


def test_closes_before_with_insufficient_history(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_closes("IPO", weekdays(D(2026, 11, 10), TODAY))
    service, _ = make_service(store, provider)
    result = service.get_closes_before(["IPO"], before=D(2026, 11, 16), sessions=20)["IPO"]
    assert result.status is HistoryStatus.OK and len(result.bars) == 4


def test_a_different_provider_works_without_service_changes(store: ParquetStore) -> None:
    other = OtherFakeProvider()
    other.set_closes("AAPL", weekdays(D(2026, 11, 2), TODAY, base=1))
    service, _ = make_service(store, other)
    bars = service.get_history(["AAPL"], D(2026, 11, 2), D(2026, 11, 13))["AAPL"].bars
    assert bars[0].provider == "other" and len(bars) == 10


# -- current prices / refresh ------------------------------------------------------------------------


def test_refresh_stores_timestamped_prices(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_quote("AAPL", 215.42, previous_close=218.10)
    service, _ = make_service(store, provider)

    result = service.refresh(["AAPL"])

    assert result.status is RefreshOutcome.COMPLETED
    assert (result.tickers_requested, result.tickers_updated, result.tickers_failed) == (1, 1, 0)
    price = service.get_latest_prices(["AAPL"])["AAPL"]
    assert price is not None
    assert price.price == 215.42 and price.currency == "USD" and price.provider == "fake"
    assert price.timestamp == FIXED_NOW and price.delayed is True
    assert price.daily_change == pytest.approx(-2.68)
    assert price.daily_change_pct == pytest.approx(-1.2288, abs=1e-4)
    assert price.stale is False


def test_refresh_requests_each_ticker_once(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_quote("AAPL", 1.0)
    provider.set_quote("MSFT", 2.0)
    service, _ = make_service(store, provider)
    result = service.refresh(["AAPL", "MSFT", "AAPL", "MSFT"])
    assert provider.quote_calls == [["AAPL", "MSFT"]]
    assert result.tickers_requested == 2


def test_partial_failure_keeps_previous_price_as_stale(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_quote("AAPL", 100.0)
    provider.set_quote("MSFT", 200.0)
    service, clock = make_service(store, provider)
    service.refresh(["AAPL", "MSFT"])

    clock["now"] = FIXED_NOW + timedelta(minutes=10)
    provider.set_quote("AAPL", 101.0, timestamp=FIXED_NOW + timedelta(minutes=10))
    provider.quotes["MSFT"] = ProviderError("timeout")
    result = service.refresh(["AAPL", "MSFT", "NOPE"])

    assert result.status is RefreshOutcome.PARTIAL
    assert (result.tickers_updated, result.tickers_failed) == (1, 2)
    assert {(e.ticker, e.code) for e in result.errors} == {("MSFT", "provider_error"), ("NOPE", "no_data")}
    prices = service.get_latest_prices(["AAPL", "MSFT", "NOPE"])
    assert prices["AAPL"].price == 101.0 and prices["AAPL"].stale is False  # type: ignore[union-attr]
    assert prices["MSFT"].price == 200.0 and prices["MSFT"].stale is True  # type: ignore[union-attr]
    assert prices["MSFT"].last_error == "timeout"  # type: ignore[union-attr]
    assert prices["NOPE"] is None  # never fabricated

    provider.set_quote("MSFT", 201.0, timestamp=FIXED_NOW + timedelta(minutes=20))
    service.refresh(["MSFT"])
    assert service.get_latest_prices(["MSFT"])["MSFT"].stale is False  # type: ignore[union-attr]


def test_all_failed_refresh(store: ParquetStore, provider: FakeProvider) -> None:
    provider.quotes["AAPL"] = ProviderError("down")
    service, _ = make_service(store, provider)
    result = service.refresh(["AAPL"])
    assert result.status is RefreshOutcome.FAILED
    status = service.status()
    assert status.last_refresh == result and status.last_successful_refresh_at is None


def test_invalid_quote_is_rejected(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_quote("AAPL", 1.0)
    provider.quotes["AAPL"] = provider.quotes["AAPL"].model_copy(update={"price": -5.0})  # type: ignore[union-attr]
    service, _ = make_service(store, provider)
    result = service.refresh(["AAPL"])
    assert result.errors[0].code == "invalid_price"
    assert service.get_latest_prices(["AAPL"])["AAPL"] is None


def test_missing_previous_close_gives_no_daily_change(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_quote("AAPL", 10.0, previous_close=None)
    service, _ = make_service(store, provider)
    service.refresh(["AAPL"])
    price = service.get_latest_prices(["AAPL"])["AAPL"]
    assert price is not None and price.daily_change is None and price.daily_change_pct is None


def test_status_tracks_last_successful_refresh(store: ParquetStore, provider: FakeProvider) -> None:
    provider.set_quote("AAPL", 1.0)
    service, clock = make_service(store, provider)
    assert service.status().last_refresh is None
    service.refresh(["AAPL"])
    clock["now"] = FIXED_NOW + timedelta(hours=1)
    provider.quotes["AAPL"] = ProviderError("down")
    service.refresh(["AAPL"])
    status = service.status()
    assert status.provider == "fake"
    assert status.last_refresh.status is RefreshOutcome.FAILED  # type: ignore[union-attr]
    assert status.last_successful_refresh_at == FIXED_NOW


def test_empty_refresh(store: ParquetStore, provider: FakeProvider) -> None:
    service, _ = make_service(store, provider)
    result = service.refresh([])
    assert result.status is RefreshOutcome.COMPLETED and result.tickers_requested == 0


def test_refresh_rotates_current_file(store: ParquetStore, provider: FakeProvider) -> None:
    service, clock = make_service(store, provider, threshold=3)
    for minute in range(4):
        clock["now"] = FIXED_NOW + timedelta(minutes=minute)
        provider.set_quote("AAPL", 100.0 + minute, timestamp=datetime(2026, 11, 16, 15, minute, tzinfo=UTC))
        service.refresh(["AAPL"])
    assert list(store.resolve("market_data/current").glob("current.2*.parquet"))
    assert service.get_latest_prices(["AAPL"])["AAPL"].price == 103.0  # type: ignore[union-attr]
