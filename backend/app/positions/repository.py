"""Position persistence: data/positions/positions.parquet."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import PurePosixPath

import pyarrow as pa

from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema, register_dataset
from app.positions.models import Position, PositionStatus

UTC_TS = pa.timestamp("us", tz="UTC")
DECIMAL = pa.decimal128(20, 8)

POSITIONS = register_dataset(
    DatasetSchema(
        "positions",
        1,
        pa.schema(
            [
                pa.field("id", pa.string(), nullable=False),
                pa.field("portfolio_id", pa.string(), nullable=False),
                pa.field("ticker", pa.string(), nullable=False),
                pa.field("currency", pa.string(), nullable=False),
                pa.field("quantity", DECIMAL, nullable=False),
                pa.field("entry_price", DECIMAL, nullable=False),
                pa.field("entry_date", pa.date32(), nullable=True),
                pa.field("status", pa.string(), nullable=False),
                pa.field("exit_price", DECIMAL, nullable=True),
                pa.field("exit_date", pa.date32(), nullable=True),
                pa.field("notes", pa.string(), nullable=False),
                pa.field("created_at", UTC_TS, nullable=False),
                pa.field("updated_at", UTC_TS, nullable=False),
            ]
        ),
        key=("id",),
        path=PurePosixPath("positions/positions.parquet"),
    )
)


class PositionRepository:
    def __init__(self, store: ParquetStore) -> None:
        self.store = store

    def load(self) -> list[Position]:
        return [_from_row(r) for r in self.store.read(POSITIONS).to_pylist()]

    def modify(self, change: Callable[[list[Position]], list[Position]]) -> list[Position]:
        """Read-modify-write under the data lock. ``change`` may raise to abort."""
        result: list[Position] = []

        def transform(table: pa.Table) -> pa.Table:
            nonlocal result
            result = change([_from_row(r) for r in table.to_pylist()])
            return _to_table(result)

        self.store.update(POSITIONS, transform)
        return result


def _from_row(row: dict) -> Position:
    return Position(**{**row, "status": PositionStatus(row["status"])})


def _to_table(positions: list[Position]) -> pa.Table:
    rows = [p.model_dump(mode="python") | {"status": p.status.value} for p in positions]
    return pa.Table.from_pylist(rows, schema=POSITIONS.schema)
