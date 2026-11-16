from __future__ import annotations

import os
from decimal import Decimal
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from app.persistence import parquet as parquet_mod
from app.persistence.errors import (
    CorruptFileError,
    IncompatibleSchemaError,
    PersistenceError,
    SchemaValidationError,
)
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema, validate_table
from tests.helpers import SAMPLE, SAMPLE_V2, append_rows, sample_rows


def _file(store: ParquetStore) -> Path:
    return store.resolve(SAMPLE.path)


def _no_temp_files(store: ParquetStore) -> bool:
    return not list(store.data_dir.rglob(".tmp-*"))


# -- create / read ------------------------------------------------------------------


def test_write_then_read_roundtrip(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "123.45678901"), ("b", "0.1"), note="hello"))

    table = store.read(SAMPLE)

    assert table.schema.remove_metadata().equals(SAMPLE.schema)
    assert table.column("amount").to_pylist() == [Decimal("123.45678901"), Decimal("0.10000000")]
    assert table.column("note").to_pylist() == ["hello", "hello"]
    meta = pq.read_schema(_file(store)).metadata
    assert meta[b"mtp_dataset"] == b"sample" and meta[b"mtp_schema_version"] == b"1"
    assert _no_temp_files(store)


def test_decimal_sum_is_exact(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(*[(str(i), "0.1") for i in range(10)]))
    total = sum(store.read(SAMPLE).column("amount").to_pylist(), Decimal(0))
    assert total == Decimal("1")


def test_read_missing_file_returns_empty_table_with_schema(store: ParquetStore) -> None:
    table = store.read(SAMPLE)
    assert table.num_rows == 0
    assert table.schema.remove_metadata().equals(SAMPLE.schema)
    assert not store.exists(SAMPLE)


def test_column_order_is_normalised(store: ParquetStore) -> None:
    rows = sample_rows(("a", "1"))
    store.write(SAMPLE, rows.select(list(reversed(rows.column_names))))
    assert store.read(SAMPLE).column_names == SAMPLE.schema.names


def test_partitioned_dataset_requires_explicit_path(store: ParquetStore) -> None:
    partitioned = DatasetSchema("part", 1, SAMPLE.schema)
    with pytest.raises(PersistenceError, match="partitioned"):
        store.read(partitioned)
    store.write(partitioned, sample_rows(("a", "1")), "market_data/close_prices/20261116.parquet")
    assert store.read(partitioned, "market_data/close_prices/20261116.parquet").num_rows == 1


# -- updates -------------------------------------------------------------------


def test_update_existing_file(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")))
    written = store.update(SAMPLE, lambda t: append_rows(t, sample_rows(("b", "2"))))
    assert written.num_rows == 2
    assert store.read(SAMPLE).column("id").to_pylist() == ["a", "b"]


def test_failed_transform_leaves_file_untouched(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")))
    before = _file(store).read_bytes()

    def boom(_: pa.Table) -> pa.Table:
        raise ValueError("bad transform")

    with pytest.raises(ValueError):
        store.update(SAMPLE, boom)
    assert _file(store).read_bytes() == before


# -- validation ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda t: t.drop_columns(["note"]), "missing=\\['note'\\]"),
        (lambda t: t.append_column("extra", pa.array([1])), "unexpected=\\['extra'\\]"),
        (
            lambda t: t.set_column(1, "amount", pa.array([1.5], pa.float64())),
            "'amount' has type double",
        ),
        (
            lambda t: t.set_column(0, "id", pa.array([None], pa.string())),
            "'id' contains 1 null",
        ),
        (lambda t: pa.concat_tables([t, t]), "duplicate values for key"),
    ],
)
def test_invalid_data_is_rejected_and_file_untouched(store: ParquetStore, mutate, match: str) -> None:  # type: ignore[no-untyped-def]
    store.write(SAMPLE, sample_rows(("a", "1")))
    before = _file(store).read_bytes()

    with pytest.raises(SchemaValidationError, match=match):
        store.write(SAMPLE, mutate(sample_rows(("x", "9"))))

    assert _file(store).read_bytes() == before
    assert _no_temp_files(store)


def test_nullable_column_accepts_nulls() -> None:
    validate_table(sample_rows(("a", "1"), note=None), SAMPLE)


# -- failure during write -------------------------------------------------------------


def test_write_failure_preserves_original_and_cleans_up(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")))
    before = _file(store).read_bytes()

    def failing_write(*_a, **_k):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr(parquet_mod.pq, "write_table", failing_write)
    with pytest.raises(PersistenceError, match="Failed to write positions/sample.parquet: disk full"):
        store.write(SAMPLE, sample_rows(("b", "2")))

    assert _file(store).read_bytes() == before
    assert _no_temp_files(store)


def test_replace_failure_preserves_original_and_cleans_up(
    store: ParquetStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")))
    before = _file(store).read_bytes()

    def failing_replace(*_a, **_k):  # type: ignore[no-untyped-def]
        raise OSError("replace failed")

    monkeypatch.setattr(parquet_mod.os, "replace", failing_replace)
    with pytest.raises(PersistenceError):
        store.write(SAMPLE, sample_rows(("b", "2")))

    monkeypatch.undo()
    assert _file(store).read_bytes() == before
    assert _no_temp_files(store)


def test_stale_temp_files_are_removed(store: ParquetStore) -> None:
    leftover = store.data_dir / "positions" / ".tmp-sample.parquet.abc.tmp"
    leftover.write_bytes(b"partial")
    keep = store.data_dir / "positions" / "keep.parquet"
    keep.write_bytes(b"x")

    assert store.remove_stale_temp_files() == 1
    assert not leftover.exists() and keep.exists()


# -- incompatible / corrupt files -------------------------------------------------------


def test_newer_schema_version_is_rejected_not_overwritten(store: ParquetStore) -> None:
    store.write(SAMPLE_V2, sample_rows(("a", "1")))
    before = _file(store).read_bytes()

    with pytest.raises(IncompatibleSchemaError, match="schema version 2, expected 1"):
        store.read(SAMPLE)
    with pytest.raises(IncompatibleSchemaError):
        store.update(SAMPLE, lambda t: t)
    with pytest.raises(IncompatibleSchemaError):
        store.validate_registered([SAMPLE])
    assert _file(store).read_bytes() == before


def test_file_from_other_dataset_is_rejected(store: ParquetStore) -> None:
    other = DatasetSchema("other", 1, SAMPLE.schema, path=SAMPLE.path)
    store.write(other, sample_rows(("a", "1")))
    with pytest.raises(IncompatibleSchemaError, match="belongs to dataset 'other'"):
        store.read(SAMPLE)


def test_file_without_metadata_is_rejected(store: ParquetStore) -> None:
    _file(store).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(sample_rows(("a", "1")), _file(store))
    with pytest.raises(IncompatibleSchemaError, match="<unknown>"):
        store.read(SAMPLE)


def test_column_type_drift_is_rejected(store: ParquetStore) -> None:
    drifted_schema = SAMPLE.schema.set(1, pa.field("amount", pa.float64(), nullable=False))
    drifted = DatasetSchema("sample", 1, drifted_schema, path=SAMPLE.path)
    table = sample_rows(("a", "1")).set_column(1, "amount", pa.array([1.0]))
    store.write(drifted, table)
    with pytest.raises(IncompatibleSchemaError, match="columns/types differ"):
        store.read(SAMPLE)


def test_corrupt_file_is_reported(store: ParquetStore) -> None:
    _file(store).parent.mkdir(parents=True, exist_ok=True)
    _file(store).write_bytes(b"this is not parquet")
    with pytest.raises(CorruptFileError, match="positions/sample.parquet cannot be read"):
        store.read(SAMPLE)
    with pytest.raises(CorruptFileError):
        store.read_metadata(SAMPLE)


def test_validate_registered_checks_existing_files_only(store: ParquetStore) -> None:
    assert store.validate_registered([SAMPLE]) == []
    store.write(SAMPLE, sample_rows(("a", "1")))
    assert store.validate_registered([SAMPLE]) == ["positions/sample.parquet"]


# -- paths / metadata / delete -------------------------------------------------------------


@pytest.mark.parametrize("bad", ["../escape.parquet", "/etc/passwd", "a/../../b.parquet", ""])
def test_paths_cannot_escape_data_dir(store: ParquetStore, bad: str) -> None:
    with pytest.raises(PersistenceError, match="Invalid data path"):
        store.resolve(bad)


def test_extra_metadata_is_stored_and_namespaced(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")), extra_metadata={"x_note": "v"})
    meta = store.read_metadata(SAMPLE)
    assert meta is not None and meta["x_note"] == "v" and meta["mtp_dataset"] == "sample"
    with pytest.raises(PersistenceError, match="must start with 'x_'"):
        store.write(SAMPLE, sample_rows(("a", "1")), extra_metadata={"mtp_dataset": "evil"})


def test_delete(store: ParquetStore) -> None:
    assert store.delete(SAMPLE) is False
    store.write(SAMPLE, sample_rows(("a", "1")))
    assert store.delete(SAMPLE) is True
    assert not _file(store).exists()


def test_write_preserves_file_permissions_default(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")))
    mode = os.stat(_file(store)).st_mode & 0o777
    assert mode & 0o600 == 0o600
