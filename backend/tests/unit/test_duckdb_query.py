from __future__ import annotations

from decimal import Decimal

import pytest

from app.persistence.duckdb import ParquetSource, query
from app.persistence.errors import PersistenceError
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema
from tests.helpers import SAMPLE, sample_rows

PARTITIONED = DatasetSchema("partitioned_sample", 1, SAMPLE.schema)


def test_query_single_file_with_params(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "1.5"), ("b", "2.25"), ("c", "3")))
    src = ParquetSource("sample", store.resolve(SAMPLE.path), SAMPLE)

    result = query("SELECT id FROM sample WHERE amount > ? ORDER BY id", [src], [Decimal("2")])

    assert result.column("id").to_pylist() == ["b", "c"]


def test_query_preserves_decimal_precision(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(*[(str(i), "0.1") for i in range(10)]))
    src = ParquetSource("sample", store.resolve(SAMPLE.path), SAMPLE)
    total = query("SELECT sum(amount) AS total FROM sample", [src]).column("total")[0].as_py()
    assert total == Decimal("1")


def test_query_glob_across_partition_files(store: ParquetStore) -> None:
    folder = "market_data/close_prices"
    store.write(PARTITIONED, sample_rows(("a", "1")), f"{folder}/20261113.parquet")
    store.write(PARTITIONED, sample_rows(("b", "2"), ("c", "3")), f"{folder}/20261116.parquet")
    src = ParquetSource("prices", store.resolve(folder) / "*.parquet", PARTITIONED)

    result = query("SELECT count(*) AS n, sum(amount) AS total FROM prices", [src])

    assert result.to_pylist() == [{"n": 3, "total": Decimal("6")}]


def test_query_ignores_temp_files_in_glob(store: ParquetStore) -> None:
    folder = store.resolve("market_data/close_prices")
    store.write(PARTITIONED, sample_rows(("a", "1")), "market_data/close_prices/20261113.parquet")
    (folder / ".tmp-20261116.parquet.x.tmp").write_bytes(b"partial")
    src = ParquetSource("prices", folder / "*.parquet", PARTITIONED)
    assert query("SELECT count(*) AS n FROM prices", [src]).to_pylist() == [{"n": 1}]


def test_query_on_missing_files_returns_empty_result(store: ParquetStore) -> None:
    src = ParquetSource("prices", store.resolve("market_data/close_prices") / "*.parquet", PARTITIONED)
    result = query("SELECT id, amount FROM prices", [src])
    assert result.num_rows == 0
    assert result.schema.field("amount").type == SAMPLE.schema.field("amount").type
    assert query("SELECT count(*) AS n FROM prices", [src]).to_pylist() == [{"n": 0}]


def test_query_joins_multiple_sources(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "1"), ("b", "2")))
    store.write(PARTITIONED, sample_rows(("b", "5")), "strategies/other.parquet")
    sources = [
        ParquetSource("s", store.resolve(SAMPLE.path), SAMPLE),
        ParquetSource("o", store.resolve("strategies/other.parquet"), PARTITIONED),
    ]
    result = query("SELECT s.id, o.amount FROM s JOIN o USING (id)", sources)
    assert result.to_pylist() == [{"id": "b", "amount": Decimal("5")}]


def test_invalid_sql_raises_persistence_error(store: ParquetStore) -> None:
    src = ParquetSource("sample", store.resolve(SAMPLE.path), SAMPLE)
    with pytest.raises(PersistenceError, match="Query failed"):
        query("SELECT nope FROM sample", [src])


def test_invalid_view_name_rejected(store: ParquetStore) -> None:
    src = ParquetSource("bad name; drop", store.resolve(SAMPLE.path), SAMPLE)
    with pytest.raises(PersistenceError, match="Invalid view name"):
        query("SELECT 1", [src])
