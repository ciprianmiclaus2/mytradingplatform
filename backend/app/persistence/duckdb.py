"""DuckDB analytical queries over Parquet files.

Each query runs in a short-lived in-memory DuckDB connection: there is no
persistent database file. Datasets are exposed to SQL as named views over
their Parquet file(s). A dataset with no files yet is exposed as an empty
view with its declared schema, so queries never fail just because nothing
has been written.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from app.persistence.errors import PersistenceError
from app.persistence.schemas import DatasetSchema

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParquetSource:
    """A SQL view name bound to Parquet files matching ``pattern``.

    ``pattern`` is a path or glob (e.g. ``.../close_prices/*.parquet``).
    """

    view: str
    pattern: Path
    dataset: DatasetSchema


def _files(pattern: Path) -> list[str]:
    if any(ch in pattern.name for ch in "*?["):
        return sorted(str(p) for p in pattern.parent.glob(pattern.name) if p.is_file())
    return [str(pattern)] if pattern.is_file() else []


def query(
    sql: str,
    sources: Iterable[ParquetSource],
    params: Sequence[Any] | dict[str, Any] | None = None,
) -> pa.Table:
    """Run ``sql`` against the given sources and return an Arrow table."""
    con = duckdb.connect(":memory:")
    try:
        for src in sources:
            if not src.view.isidentifier():
                raise PersistenceError(f"Invalid view name {src.view!r}")
            files = _files(src.pattern)
            if files:
                rel = con.read_parquet(files, union_by_name=True)
            else:
                rel = con.from_arrow(src.dataset.schema.empty_table())
            rel.create_view(src.view)
        return con.sql(sql, params=params).to_arrow_table()
    except duckdb.Error as exc:
        logger.error("duckdb query failed", extra={"error": str(exc)})
        raise PersistenceError(f"Query failed: {exc}") from exc
    finally:
        con.close()
