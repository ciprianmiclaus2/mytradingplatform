"""Signal history: data/strategies/signals.parquet.

Only changes of signal state are recorded, per (instance_id, ticker). The
current state of a series is the ``new_signal`` of its latest event; a series
with no events is in the "no signal" state.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath

import pyarrow as pa

from app.persistence.duckdb import ParquetSource, query
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema, register_dataset
from app.strategies.models import Signal, SignalEvent, SignalHistoryPage

UTC_TS = pa.timestamp("us", tz="UTC")

SIGNALS = register_dataset(
    DatasetSchema(
        "signals",
        1,
        pa.schema(
            [
                pa.field("id", pa.string(), nullable=False),
                pa.field("instance_id", pa.string(), nullable=False),
                pa.field("strategy", pa.string(), nullable=False),
                pa.field("ticker", pa.string(), nullable=False),
                pa.field("previous_signal", pa.string(), nullable=True),
                pa.field("new_signal", pa.string(), nullable=True),
                pa.field("metric_name", pa.string(), nullable=True),
                pa.field("metric_value", pa.float64(), nullable=True),
                pa.field("current_price", pa.float64(), nullable=True),
                pa.field("timestamp", UTC_TS, nullable=False),
            ]
        ),
        key=("id",),
        path=PurePosixPath("strategies/signals.parquet"),
    )
)


@dataclass(frozen=True)
class SignalState:
    signal: Signal | None
    previous: Signal | None
    since: datetime

    @property
    def baseline(self) -> bool:
        """The state was recorded when the instance first saw the ticker, not at a change.

        Baseline rows have ``previous_signal == new_signal``; a real
        transition never does. When the state began is then unknown.
        """
        return self.signal == self.previous


@dataclass(frozen=True)
class Transition:
    ticker: str
    previous: Signal | None
    new: Signal | None
    metric_name: str | None
    metric_value: float | None
    current_price: float | None


def _signal(value: str | None) -> Signal | None:
    return Signal(value) if value else None


class SignalStore:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def _source(self) -> ParquetSource:
        return ParquetSource("signals", self.store.resolve(SIGNALS.path), SIGNALS)  # type: ignore[arg-type]

    def current_states(self, instance_id: str, tickers: list[str]) -> dict[str, SignalState]:
        """Latest recorded state per ticker; tickers with no events are omitted."""
        if not tickers:
            return {}
        table = query(
            "SELECT ticker, new_signal, previous_signal, timestamp FROM signals "
            "WHERE instance_id = $instance AND list_contains($tickers, ticker) "
            "QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY timestamp DESC, id DESC) = 1",
            [self._source()],
            {"instance": instance_id, "tickers": tickers},
        )
        return {
            r["ticker"]: SignalState(_signal(r["new_signal"]), _signal(r["previous_signal"]), r["timestamp"])
            for r in table.to_pylist()
        }

    def record(self, instance_id: str, strategy: str, at: datetime, transitions: list[Transition]) -> None:
        if not transitions:
            return
        rows = pa.Table.from_pylist(
            [
                {
                    "id": uuid.uuid4().hex,
                    "instance_id": instance_id,
                    "strategy": strategy,
                    "ticker": t.ticker,
                    "previous_signal": t.previous.value if t.previous else None,
                    "new_signal": t.new.value if t.new else None,
                    "metric_name": t.metric_name,
                    "metric_value": t.metric_value,
                    "current_price": t.current_price,
                    "timestamp": at,
                }
                for t in transitions
            ],
            schema=SIGNALS.schema,
        )
        self.store.update(SIGNALS, lambda current: pa.concat_tables([current, rows]))

    def history(
        self,
        *,
        instance_id: str | None = None,
        strategy: str | None = None,
        ticker: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> SignalHistoryPage:
        """Signal changes newest first, filtered and paginated. Baseline rows are excluded."""
        clauses, params = ["previous_signal IS DISTINCT FROM new_signal"], {}
        for column, value in (("instance_id", instance_id), ("strategy", strategy), ("ticker", ticker)):
            if value is not None:
                clauses.append(f"{column} = ${column}")
                params[column] = value
        where = f"WHERE {' AND '.join(clauses)}"
        total = query(f"SELECT count(*) AS n FROM signals {where}", [self._source()], params or None)
        page = query(
            f"SELECT * FROM signals {where} ORDER BY timestamp DESC, id DESC LIMIT $limit OFFSET $offset",
            [self._source()],
            {**params, "limit": limit, "offset": offset},
        )
        items = [
            SignalEvent(**{**r, "previous_signal": _signal(r["previous_signal"]), "new_signal": _signal(r["new_signal"])})
            for r in page.to_pylist()
        ]
        return SignalHistoryPage(items=items, total=total.column("n")[0].as_py(), limit=limit, offset=offset)
