"""Portfolio persistence: data/portfolios/portfolios.parquet."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

import pyarrow as pa

from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema, register_dataset
from app.portfolio.models import Portfolio, PortfolioType

UTC_TS = pa.timestamp("us", tz="UTC")

PORTFOLIOS = register_dataset(
    DatasetSchema(
        "portfolios",
        1,
        pa.schema(
            [
                pa.field("id", pa.string(), nullable=False),
                pa.field("name", pa.string(), nullable=False),
                pa.field("description", pa.string(), nullable=False),
                pa.field("type", pa.string(), nullable=False),
                # Watchlists only; empty for positions portfolios (derived from positions).
                pa.field("tickers", pa.list_(pa.string()), nullable=False),
                pa.field("favourites", pa.list_(pa.string()), nullable=False),
                pa.field("created_at", UTC_TS, nullable=False),
                pa.field("updated_at", UTC_TS, nullable=False),
            ]
        ),
        key=("id",),
        path=PurePosixPath("portfolios/portfolios.parquet"),
    )
)


class PortfolioRepository:
    """Reads and writes portfolio records (stored tickers, not derived ones)."""

    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def exists(self) -> bool:
        return self.store.exists(PORTFOLIOS)

    def load(self) -> list[Portfolio]:
        return [_from_row(r) for r in self.store.read(PORTFOLIOS).to_pylist()]

    def save(self, portfolios: list[Portfolio]) -> None:
        self.store.write(PORTFOLIOS, _to_table(portfolios))

    def modify(self, change: Callable[[list[Portfolio]], list[Portfolio]]) -> list[Portfolio]:
        """Read-modify-write under the data lock. ``change`` may raise to abort."""
        result: list[Portfolio] = []

        def transform(table: pa.Table) -> pa.Table:
            nonlocal result
            result = change([_from_row(r) for r in table.to_pylist()])
            return _to_table(result)

        self.store.update(PORTFOLIOS, transform)
        return result


def _from_row(row: dict) -> Portfolio:
    return Portfolio(**{**row, "type": PortfolioType(row["type"])})


def _to_table(portfolios: list[Portfolio]) -> pa.Table:
    rows = [p.model_dump(mode="python") | {"type": p.type.value} for p in portfolios]
    return pa.Table.from_pylist(rows, schema=PORTFOLIOS.schema)
