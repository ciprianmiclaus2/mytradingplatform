from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from app.market_data.cache import (
    CLOSE_PRICES,
    CURRENT_PRICES,
    PRICE_HISTORY,
    CurrentPriceCache,
    HistoricalCache,
    build_price_history,
    close_file,
    merge_ranges,
    subtract_ranges,
)
from app.market_data.models import DailyBar, PriceQuote
from app.persistence.parquet import ParquetStore

D = date


def bar(ticker: str, day: date, close: float) -> DailyBar:
    return DailyBar(
        ticker=ticker, trading_date=day, close=close, adjusted_close=None, currency="USD",
        provider="fake", fetched_at=datetime(2026, 11, 16, tzinfo=UTC),
    )


def quote(ticker: str, price: float, minute: int) -> PriceQuote:
    ts = datetime(2026, 11, 16, 15, minute, tzinfo=UTC)
    return PriceQuote(
        ticker=ticker, price=price, previous_close=100.0, currency="USD", timestamp=ts,
        trading_date=ts.date(), provider="fake", delayed=True, fetched_at=ts,
    )


# -- range arithmetic ---------------------------------------------------------------------


def test_merge_ranges_merges_overlapping_and_adjacent() -> None:
    assert merge_ranges([(D(2026, 1, 5), D(2026, 1, 9)), (D(2026, 1, 1), D(2026, 1, 4)),
                         (D(2026, 1, 20), D(2026, 1, 25)), (D(2026, 1, 8), D(2026, 1, 10))]) == [
        (D(2026, 1, 1), D(2026, 1, 10)), (D(2026, 1, 20), D(2026, 1, 25))]


@pytest.mark.parametrize(
    ("covered", "expected"),
    [
        ([], [(D(2026, 1, 1), D(2026, 1, 31))]),
        ([(D(2026, 1, 1), D(2026, 1, 31))], []),
        ([(D(2025, 12, 1), D(2026, 2, 1))], []),
        ([(D(2026, 1, 10), D(2026, 1, 20))], [(D(2026, 1, 1), D(2026, 1, 9)), (D(2026, 1, 21), D(2026, 1, 31))]),
        ([(D(2026, 1, 1), D(2026, 1, 5)), (D(2026, 1, 25), D(2026, 2, 5))], [(D(2026, 1, 6), D(2026, 1, 24))]),
    ],
)
def test_subtract_ranges(covered, expected) -> None:  # type: ignore[no-untyped-def]
    assert subtract_ranges(D(2026, 1, 1), D(2026, 1, 31), covered) == expected


# -- historical cache -------------------------------------------------------------------------


def test_store_fetch_writes_one_file_per_date_with_multiple_tickers(store: ParquetStore) -> None:
    cache = HistoricalCache(store)
    cache.store_fetch("AAPL", "fake", D(2026, 11, 12), D(2026, 11, 13),
                      [bar("AAPL", D(2026, 11, 12), 1.0), bar("AAPL", D(2026, 11, 13), 2.0)])
    cache.store_fetch("MSFT", "fake", D(2026, 11, 13), D(2026, 11, 13), [bar("MSFT", D(2026, 11, 13), 3.0)])

    assert store.resolve(close_file(D(2026, 11, 13))).name == "20261113.parquet"
    day = store.read(CLOSE_PRICES, close_file(D(2026, 11, 13)))
    assert sorted(day.column("ticker").to_pylist()) == ["AAPL", "MSFT"]
    got = cache.read(["AAPL", "MSFT", "NONE"], D(2026, 11, 1), D(2026, 11, 30))
    assert [b.close for b in got["AAPL"]] == [1.0, 2.0]
    assert [b.close for b in got["MSFT"]] == [3.0]
    assert got["NONE"] == []


def test_refetch_replaces_ticker_row_not_duplicates(store: ParquetStore) -> None:
    cache = HistoricalCache(store)
    cache.store_fetch("AAPL", "fake", D(2026, 11, 13), D(2026, 11, 13), [bar("AAPL", D(2026, 11, 13), 1.0)])
    cache.store_fetch("AAPL", "fake", D(2026, 11, 13), D(2026, 11, 13), [bar("AAPL", D(2026, 11, 13), 1.5)])
    assert [b.close for b in cache.read(["AAPL"], D(2026, 11, 13), D(2026, 11, 13))["AAPL"]] == [1.5]


def test_coverage_tracks_no_data_dates(store: ParquetStore) -> None:
    cache = HistoricalCache(store)
    # Weekend fetched with no bars: covered, no data.
    cache.store_fetch("AAPL", "fake", D(2026, 11, 14), D(2026, 11, 15), [])
    assert cache.coverage("AAPL", "fake") == [(D(2026, 11, 14), D(2026, 11, 15))]
    assert cache.missing_ranges("AAPL", "fake", D(2026, 11, 13), D(2026, 11, 16)) == [
        (D(2026, 11, 13), D(2026, 11, 13)), (D(2026, 11, 16), D(2026, 11, 16))]
    cache.store_fetch("AAPL", "fake", D(2026, 11, 16), D(2026, 11, 16), [])
    assert cache.coverage("AAPL", "fake") == [(D(2026, 11, 14), D(2026, 11, 16))]
    assert cache.coverage("AAPL", "other") == []  # coverage is per provider


def test_store_fetch_rejects_bars_outside_range(store: ParquetStore) -> None:
    with pytest.raises(ValueError):
        HistoricalCache(store).store_fetch("AAPL", "fake", D(2026, 11, 13), D(2026, 11, 13),
                                           [bar("AAPL", D(2026, 11, 14), 1.0)])
    assert HistoricalCache(store).coverage("AAPL", "fake") == []


def test_history_view_build(store: ParquetStore) -> None:
    assert build_price_history(store).num_rows == 0  # no files yet
    cache = HistoricalCache(store)
    cache.store_fetch("MSFT", "fake", D(2026, 11, 12), D(2026, 11, 13),
                      [bar("MSFT", D(2026, 11, 13), 3.0), bar("MSFT", D(2026, 11, 12), 2.0)])
    cache.store_fetch("AAPL", "fake", D(2026, 11, 12), D(2026, 11, 12), [bar("AAPL", D(2026, 11, 12), 1.0)])

    table = build_price_history(store)
    assert table.schema.equals(PRICE_HISTORY.schema)
    assert [(r["ticker"], r["trading_date"], r["close"]) for r in table.to_pylist()] == [
        ("AAPL", D(2026, 11, 12), 1.0), ("MSFT", D(2026, 11, 12), 2.0), ("MSFT", D(2026, 11, 13), 3.0)]


# -- current prices -------------------------------------------------------------------------------


def test_current_append_and_latest(store: ParquetStore) -> None:
    cache = CurrentPriceCache(store, archive_threshold=1000)
    assert cache.latest() == {}
    assert cache.append([quote("AAPL", 1.0, 0), quote("MSFT", 2.0, 0)]) == 2
    assert cache.append([quote("AAPL", 1.5, 5)]) == 1

    latest = cache.latest()
    assert {t: q.price for t, q in latest.items()} == {"AAPL": 1.5, "MSFT": 2.0}
    assert latest["AAPL"].timestamp == datetime(2026, 11, 16, 15, 5, tzinfo=UTC)
    assert cache.latest(["MSFT", "NONE"]).keys() == {"MSFT"}
    assert store.read(CURRENT_PRICES).num_rows == 3  # full time series kept


def test_current_same_observation_not_duplicated(store: ParquetStore) -> None:
    cache = CurrentPriceCache(store, archive_threshold=1000)
    cache.append([quote("AAPL", 1.0, 0)])
    assert cache.append([quote("AAPL", 1.0, 0)]) == 0  # market closed: same quote again
    assert store.read(CURRENT_PRICES).num_rows == 1


def test_current_rotation(store: ParquetStore) -> None:
    cache = CurrentPriceCache(store, archive_threshold=4)
    cache.append([quote("AAPL", 1.0, 0), quote("MSFT", 2.0, 0)])
    cache.append([quote("AAPL", 1.1, 1)])
    assert not list(store.resolve("market_data/current").glob("current.*.parquet"))

    cache.append([quote("AAPL", 1.2, 2)])  # reaches the threshold of 4 rows

    archives = list(store.resolve("market_data/current").glob("current.2*.parquet"))
    assert len(archives) == 1
    assert len(archives[0].name) == len("current.20261116100000.parquet")
    assert store.read(CURRENT_PRICES, f"market_data/current/{archives[0].name}").num_rows == 4
    # Active file seeded with the latest row per ticker, so the latest view stays correct.
    assert store.read(CURRENT_PRICES).num_rows == 2
    assert {t: q.price for t, q in cache.latest().items()} == {"AAPL": 1.2, "MSFT": 2.0}

    cache.append([quote("MSFT", 2.5, 3)])
    assert {t: q.price for t, q in cache.latest().items()} == {"AAPL": 1.2, "MSFT": 2.5}


def test_rotation_twice_in_same_second_does_not_overwrite(store: ParquetStore) -> None:
    cache = CurrentPriceCache(store, archive_threshold=1000)
    cache.append([quote("AAPL", 1.0, 0)])
    first = cache.rotate()
    second = cache.rotate()
    assert first != second
    assert len(list(store.resolve("market_data/current").glob("current.2*.parquet"))) == 2


def test_latest_handles_many_rows_quickly(store: ParquetStore) -> None:
    cache = CurrentPriceCache(store, archive_threshold=100_000)
    base = datetime(2026, 11, 16, tzinfo=UTC)
    quotes = [
        quote("T%d" % (i % 50), float(i + 1), 0).model_copy(update={"timestamp": base + timedelta(seconds=i)})
        for i in range(2000)
    ]
    cache.append(quotes)
    latest = cache.latest()
    assert len(latest) == 50
    assert latest["T0"].price == 1951.0
