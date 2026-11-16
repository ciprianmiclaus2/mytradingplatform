"""Shared test helpers (importable by spawned subprocesses)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path, PurePosixPath

import pyarrow as pa

from app.persistence.locking import DataLock
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema

MONEY = pa.decimal128(20, 8)

SAMPLE = DatasetSchema(
    name="sample",
    version=1,
    schema=pa.schema(
        [
            pa.field("id", pa.string(), nullable=False),
            pa.field("amount", MONEY, nullable=False),
            pa.field("note", pa.string(), nullable=True),
            pa.field("created_at", pa.timestamp("us", tz="UTC"), nullable=False),
        ]
    ),
    key=("id",),
    path=PurePosixPath("positions/sample.parquet"),
)

SAMPLE_V2 = DatasetSchema(
    name="sample", version=2, schema=SAMPLE.schema, key=SAMPLE.key, path=SAMPLE.path
)


def sample_rows(*items: tuple[str, str], note: str | None = None) -> pa.Table:
    ts = datetime(2026, 11, 16, 12, 0, tzinfo=UTC)
    return pa.table(
        {
            "id": [i for i, _ in items],
            "amount": pa.array([Decimal(a) for _, a in items], MONEY),
            "note": pa.array([note] * len(items), pa.string()),
            "created_at": pa.array([ts] * len(items), pa.timestamp("us", tz="UTC")),
        }
    )


def append_rows(table: pa.Table, rows: pa.Table) -> pa.Table:
    return pa.concat_tables([table, rows.cast(table.schema)])


def process_increment_worker(data_dir: str, worker: int, count: int) -> None:
    """Append ``count`` rows via read-modify-write from a separate process."""
    store = ParquetStore(Path(data_dir), DataLock(Path(data_dir), timeout=60))
    for n in range(count):
        store.update(SAMPLE, lambda t, n=n: append_rows(t, sample_rows((f"p{worker}-{n}", "1"))))


def hold_lock_worker(data_dir: str, ready, release) -> None:  # type: ignore[no-untyped-def]
    lock = DataLock(Path(data_dir), timeout=5)
    with lock.hold():
        ready.set()
        release.wait(10)
