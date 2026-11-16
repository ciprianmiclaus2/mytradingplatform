"""Market data caches stored as Parquet.

* Daily closes: ``market_data/close_prices/YYYYMMDD.parquet`` — one file per
  trading date, one row per ticker. Authoritative historical cache.
* Coverage: ``market_data/coverage.parquet`` — the date ranges already
  requested from a provider per ticker. A date inside a covered range with no
  close row means "no data available" (weekend, holiday, not yet listed); a
  date outside every range has simply not been fetched. Provider failures are
  never recorded as coverage.
* Current prices: ``market_data/current/current.parquet`` — append-only time
  series, rotated to ``current.YYYYMMDDHHMMSS.parquet`` at a row threshold.
* History: ``market_data/history/history.parquet`` — rebuildable consolidated
  view of all close-price files (derived dataset, not authoritative).
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import PurePosixPath

import pyarrow as pa
import pyarrow.compute as pc

from app.market_data.models import DailyBar, PriceQuote, TickerRefreshState
from app.persistence.derived import DerivedDataset, derived_registry
from app.persistence.duckdb import ParquetSource, query
from app.persistence.jsonfile import read_json, write_json
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema, register_dataset

logger = logging.getLogger(__name__)

UTC_TS = pa.timestamp("us", tz="UTC")

CLOSE_PRICES_DIR = PurePosixPath("market_data/close_prices")
CURRENT_DIR = PurePosixPath("market_data/current")
REFRESH_STATUS_FILE = PurePosixPath("market_data/refresh_status.json")

_CLOSE_FIELDS = [
    pa.field("ticker", pa.string(), nullable=False),
    pa.field("trading_date", pa.date32(), nullable=False),
    pa.field("close", pa.float64(), nullable=False),
    pa.field("adjusted_close", pa.float64(), nullable=True),
    pa.field("currency", pa.string(), nullable=False),
    pa.field("provider", pa.string(), nullable=False),
    pa.field("fetched_at", UTC_TS, nullable=False),
]

CLOSE_PRICES = register_dataset(
    DatasetSchema("close_prices", 1, pa.schema(_CLOSE_FIELDS), key=("ticker",))
)

COVERAGE = register_dataset(
    DatasetSchema(
        "close_price_coverage",
        1,
        pa.schema(
            [
                pa.field("ticker", pa.string(), nullable=False),
                pa.field("provider", pa.string(), nullable=False),
                pa.field("start_date", pa.date32(), nullable=False),
                pa.field("end_date", pa.date32(), nullable=False),
                pa.field("fetched_at", UTC_TS, nullable=False),
            ]
        ),
        key=("ticker", "provider", "start_date"),
        path=PurePosixPath("market_data/coverage.parquet"),
    )
)

CURRENT_PRICES = register_dataset(
    DatasetSchema(
        "current_prices",
        1,
        pa.schema(
            [
                pa.field("timestamp", UTC_TS, nullable=False),
                pa.field("ticker", pa.string(), nullable=False),
                pa.field("price", pa.float64(), nullable=False),
                pa.field("currency", pa.string(), nullable=False),
                pa.field("provider", pa.string(), nullable=False),
                pa.field("previous_close", pa.float64(), nullable=True),
                pa.field("trading_date", pa.date32(), nullable=True),
                pa.field("delayed", pa.bool_(), nullable=True),
                pa.field("fetched_at", UTC_TS, nullable=False),
            ]
        ),
        key=("ticker", "timestamp"),
        path=CURRENT_DIR / "current.parquet",
    )
)

PRICE_HISTORY = register_dataset(
    DatasetSchema(
        "price_history",
        1,
        pa.schema(_CLOSE_FIELDS),
        key=("ticker", "trading_date"),
        path=PurePosixPath("market_data/history/history.parquet"),
    )
)


def close_file(trading_date: date) -> PurePosixPath:
    return CLOSE_PRICES_DIR / f"{trading_date:%Y%m%d}.parquet"


# -- historical cache -----------------------------------------------------------------


Range = tuple[date, date]


def merge_ranges(ranges: list[Range]) -> list[Range]:
    """Merge overlapping or adjacent inclusive date ranges."""
    merged: list[Range] = []
    for start, end in sorted(ranges):
        if merged and start <= merged[-1][1] + timedelta(days=1):
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def subtract_ranges(start: date, end: date, covered: list[Range]) -> list[Range]:
    """Parts of [start, end] not inside any covered range."""
    gaps: list[Range] = []
    cursor = start
    for c_start, c_end in merge_ranges(covered):
        if c_end < cursor:
            continue
        if c_start > end:
            break
        if c_start > cursor:
            gaps.append((cursor, c_start - timedelta(days=1)))
        cursor = max(cursor, c_end + timedelta(days=1))
        if cursor > end:
            break
    if cursor <= end:
        gaps.append((cursor, end))
    return gaps


class HistoricalCache:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def coverage(self, ticker: str, provider: str) -> list[Range]:
        table = self.store.read(COVERAGE)
        mask = pc.and_(pc.equal(table["ticker"], ticker), pc.equal(table["provider"], provider))
        rows = table.filter(mask).to_pylist()
        return merge_ranges([(r["start_date"], r["end_date"]) for r in rows])

    def missing_ranges(self, ticker: str, provider: str, start: date, end: date) -> list[Range]:
        if end < start:
            return []
        return subtract_ranges(start, end, self.coverage(ticker, provider))

    def store_fetch(self, ticker: str, provider: str, start: date, end: date, bars: list[DailyBar]) -> int:
        """Persist a successful provider response for [start, end].

        Close files are written first, coverage last, so coverage never claims
        data that was not stored. Returns the number of bars written.
        """
        by_date: dict[date, list[DailyBar]] = defaultdict(list)
        for bar in bars:
            if bar.ticker != ticker or not start <= bar.trading_date <= end:
                raise ValueError(f"Bar {bar.ticker}@{bar.trading_date} outside fetched range")
            by_date[bar.trading_date].append(bar)

        with self.store.lock.hold():
            for trading_date, day_bars in sorted(by_date.items()):
                new_rows = _bars_table(day_bars)
                self.store.update(
                    CLOSE_PRICES,
                    lambda current, new=new_rows: pa.concat_tables(
                        [current.filter(pc.invert(pc.is_in(current["ticker"], new["ticker"]))), new]
                    ),
                    close_file(trading_date),
                )
            self._add_coverage(ticker, provider, start, end)
        logger.info(
            "historical cache updated",
            extra={"ticker": ticker, "start": str(start), "end": str(end), "bars": len(bars)},
        )
        return len(bars)

    def _add_coverage(self, ticker: str, provider: str, start: date, end: date) -> None:
        now = datetime.now(UTC)

        def merge(table: pa.Table) -> pa.Table:
            mine = pc.and_(pc.equal(table["ticker"], ticker), pc.equal(table["provider"], provider))
            others = table.filter(pc.invert(mine))
            ranges = [(r["start_date"], r["end_date"]) for r in table.filter(mine).to_pylist()]
            merged = merge_ranges([*ranges, (start, end)])
            new = pa.table(
                {
                    "ticker": [ticker] * len(merged),
                    "provider": [provider] * len(merged),
                    "start_date": pa.array([s for s, _ in merged], pa.date32()),
                    "end_date": pa.array([e for _, e in merged], pa.date32()),
                    "fetched_at": pa.array([now] * len(merged), UTC_TS),
                },
                schema=COVERAGE.schema,
            )
            return pa.concat_tables([others, new])

        self.store.update(COVERAGE, merge)

    def read(self, tickers: list[str], start: date, end: date) -> dict[str, list[DailyBar]]:
        result: dict[str, list[DailyBar]] = {t: [] for t in tickers}
        if end < start or not tickers:
            return result
        wanted = pa.array(tickers, pa.string())
        day = start
        while day <= end:
            rel = close_file(day)
            if self.store.resolve(rel).exists():
                table = self.store.read(CLOSE_PRICES, rel)
                for row in table.filter(pc.is_in(table["ticker"], wanted)).to_pylist():
                    result[row["ticker"]].append(DailyBar(**row))
            day += timedelta(days=1)
        return result


def _bars_table(bars: list[DailyBar]) -> pa.Table:
    return pa.Table.from_pylist([b.model_dump() for b in bars], schema=CLOSE_PRICES.schema)


# -- history materialised view ----------------------------------------------------------


def build_price_history(store: ParquetStore) -> pa.Table:
    source = ParquetSource("closes", store.resolve(CLOSE_PRICES_DIR) / "*.parquet", CLOSE_PRICES)
    table = query("SELECT * FROM closes ORDER BY ticker, trading_date", [source])
    return table.select(PRICE_HISTORY.schema.names).cast(PRICE_HISTORY.schema)


PRICE_HISTORY_DERIVED = derived_registry.register(
    DerivedDataset(PRICE_HISTORY, (f"{CLOSE_PRICES_DIR}/*.parquet",), build_price_history)
)


# -- current prices -------------------------------------------------------------------------


class CurrentPriceCache:
    def __init__(self, store: ParquetStore, archive_threshold: int) -> None:
        self.store = store
        self.archive_threshold = archive_threshold

    def append(self, quotes: list[PriceQuote]) -> int:
        """Append new observations; an identical (ticker, timestamp) is not duplicated.

        Returns the number of rows added. Rotates the file at the threshold.
        """
        if not quotes:
            return 0
        new = pa.Table.from_pylist([q.model_dump() for q in quotes], schema=CURRENT_PRICES.schema)
        added = 0
        with self.store.lock.hold():

            def merge(current: pa.Table) -> pa.Table:
                nonlocal added
                existing = {(r["ticker"], r["timestamp"]) for r in current.select(["ticker", "timestamp"]).to_pylist()}
                rows = [r for r in new.to_pylist() if (r["ticker"], r["timestamp"]) not in existing]
                added = len(rows)
                if not rows:
                    return current
                return pa.concat_tables(
                    [current, pa.Table.from_pylist(rows, schema=CURRENT_PRICES.schema)]
                )

            table = self.store.update(CURRENT_PRICES, merge)
            if table.num_rows >= self.archive_threshold:
                self.rotate()
        return added

    def rotate(self) -> PurePosixPath | None:
        """Archive the active file and start a new one seeded with the latest row per ticker.

        Seeding keeps the latest-price view correct while only reading the active file.
        """
        with self.store.lock.hold():
            if not self.store.exists(CURRENT_PRICES):
                return None
            latest = self._latest_table(None)
            stamp = datetime.now(UTC).strftime("%Y%m%d%H%M%S")
            archive = CURRENT_DIR / f"current.{stamp}.parquet"
            n = 1
            while self.store.resolve(archive).exists():
                archive = CURRENT_DIR / f"current.{stamp}-{n}.parquet"
                n += 1
            self.store.archive(CURRENT_PRICES, archive)
            self.store.write(CURRENT_PRICES, latest)
        logger.info("current price file rotated", extra={"archive": str(archive), "seeded": latest.num_rows})
        return archive

    def _latest_table(self, tickers: list[str] | None) -> pa.Table:
        source = ParquetSource("current", self.store.resolve(CURRENT_PRICES.path), CURRENT_PRICES)  # type: ignore[arg-type]
        sql = (
            "SELECT * FROM current "
            + ("WHERE list_contains($tickers, ticker) " if tickers is not None else "")
            + "QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY timestamp DESC, fetched_at DESC) = 1 "
            "ORDER BY ticker"
        )
        params = {"tickers": tickers} if tickers is not None else None
        table = query(sql, [source], params)
        return table.select(CURRENT_PRICES.schema.names).cast(CURRENT_PRICES.schema)

    def latest(self, tickers: list[str] | None = None) -> dict[str, PriceQuote]:
        """Most recent observation per ticker (all tickers if None)."""
        return {r["ticker"]: PriceQuote(**r) for r in self._latest_table(tickers).to_pylist()}


# -- refresh status ----------------------------------------------------------------------------


class RefreshStatusStore:
    """Last refresh result plus per-ticker refresh state (JSON)."""

    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def load(self) -> dict:
        doc = read_json(self.store, REFRESH_STATUS_FILE)
        return doc if isinstance(doc, dict) else {}

    def ticker_states(self) -> dict[str, TickerRefreshState]:
        return {
            t: TickerRefreshState.model_validate(s) for t, s in (self.load().get("tickers") or {}).items()
        }

    def save(self, doc: dict) -> None:
        write_json(self.store, REFRESH_STATUS_FILE, doc)
