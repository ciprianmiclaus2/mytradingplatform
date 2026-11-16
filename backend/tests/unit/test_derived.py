from __future__ import annotations

from decimal import Decimal
from pathlib import Path, PurePosixPath

import pyarrow as pa
import pyarrow.compute as pc
import pytest

from app.persistence import open_persistence, schemas
from app.persistence.derived import FINGERPRINT_KEY, DerivedDataset, DerivedRegistry
from app.persistence.errors import PersistenceError
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import DatasetSchema
from tests.helpers import MONEY, SAMPLE, append_rows, sample_rows

TOTALS = DatasetSchema(
    name="sample_totals",
    version=1,
    schema=pa.schema(
        [pa.field("rows", pa.int64(), nullable=False), pa.field("total", MONEY, nullable=False)]
    ),
    path=PurePosixPath("positions/sample_totals.parquet"),
)


def build_totals(store: ParquetStore) -> pa.Table:
    src = store.read(SAMPLE)
    total = pc.sum(src.column("amount")).as_py() or Decimal(0)
    return pa.table(
        {"rows": pa.array([src.num_rows], pa.int64()), "total": pa.array([total], MONEY)}
    )


@pytest.fixture
def registry() -> DerivedRegistry:
    reg = DerivedRegistry()
    reg.register(DerivedDataset(TOTALS, (str(SAMPLE.path),), build_totals))
    return reg


def _totals(store: ParquetStore) -> dict:
    return store.read(TOTALS).to_pylist()[0]


def test_rebuild_from_sources(store: ParquetStore, registry: DerivedRegistry) -> None:
    store.write(SAMPLE, sample_rows(("a", "1.5"), ("b", "2.5")))
    assert registry.is_stale(store, "sample_totals")

    assert registry.rebuild(store, "sample_totals") == 1

    assert _totals(store) == {"rows": 2, "total": Decimal("4")}
    assert not registry.is_stale(store, "sample_totals")
    assert FINGERPRINT_KEY in store.read_metadata(TOTALS)  # type: ignore[operator]


def test_source_change_marks_derived_stale_and_rebuild_stale_fixes_it(
    store: ParquetStore, registry: DerivedRegistry
) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")))
    registry.rebuild(store, "sample_totals")

    # Simulate a crash after the source write but before the snapshot update.
    store.update(SAMPLE, lambda t: append_rows(t, sample_rows(("b", "2"))))
    assert registry.is_stale(store, "sample_totals")
    assert _totals(store)["rows"] == 1

    assert registry.rebuild_stale(store) == ["sample_totals"]
    assert _totals(store) == {"rows": 2, "total": Decimal("3")}
    assert registry.rebuild_stale(store) == []


def test_rebuild_is_deterministic_after_deleting_output(
    store: ParquetStore, registry: DerivedRegistry
) -> None:
    store.write(SAMPLE, sample_rows(("a", "1"), ("b", "2")))
    registry.rebuild(store, "sample_totals")
    first = _totals(store)
    store.delete(TOTALS)
    registry.rebuild(store, "sample_totals")
    assert _totals(store) == first


def test_incremental_write_stamps_fingerprint(store: ParquetStore, registry: DerivedRegistry) -> None:
    with store.lock.hold():
        store.write(SAMPLE, sample_rows(("a", "1")))
        registry.write(store, "sample_totals", build_totals(store))
    assert not registry.is_stale(store, "sample_totals")


def test_incremental_write_requires_lock(store: ParquetStore, registry: DerivedRegistry) -> None:
    with pytest.raises(PersistenceError, match="holding the write lock"):
        registry.write(store, "sample_totals", build_totals(store))


def test_unknown_and_duplicate_registration(registry: DerivedRegistry, store: ParquetStore) -> None:
    with pytest.raises(PersistenceError, match="Unknown derived dataset"):
        registry.rebuild(store, "nope")
    with pytest.raises(ValueError, match="already registered"):
        registry.register(DerivedDataset(TOTALS, (), build_totals))


def test_glob_sources_fingerprint(store: ParquetStore) -> None:
    part = DatasetSchema("part", 1, SAMPLE.schema)
    reg = DerivedRegistry()
    reg.register(DerivedDataset(TOTALS, ("market_data/close_prices/*.parquet",), lambda s: build_totals(s)))
    store.write(part, sample_rows(("a", "1")), "market_data/close_prices/20261113.parquet")
    reg.rebuild(store, "sample_totals")
    assert not reg.is_stale(store, "sample_totals")
    store.write(part, sample_rows(("b", "1")), "market_data/close_prices/20261116.parquet")
    assert reg.is_stale(store, "sample_totals")


# -- startup integration ---------------------------------------------------------------


def _open(data_dir: Path, registry: DerivedRegistry, **kw):  # type: ignore[no-untyped-def]
    args = dict(lock_timeout=5, backup_retention=5, backup_on_startup=True, derived=registry)
    args.update(kw)
    return open_persistence(data_dir, **args)


def test_startup_rebuilds_stale_derived_and_backs_up_once(
    data_dir: Path, registry: DerivedRegistry
) -> None:
    p = _open(data_dir, registry)
    assert len(p.backups.list_backups()) == 1  # first start
    p.store.write(SAMPLE, sample_rows(("a", "7")))

    p2 = _open(data_dir, registry)

    assert _totals(p2.store) == {"rows": 1, "total": Decimal("7")}
    backups = p2.backups.list_backups()
    assert len(backups) == 2  # state changed since first start
    _open(data_dir, registry)
    assert len(p2.backups.list_backups()) == 2  # unchanged state: no new backup


def test_startup_refuses_incompatible_registered_dataset(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(schemas, "_REGISTRY", {SAMPLE.name: SAMPLE})
    p = _open(data_dir, DerivedRegistry())
    newer = DatasetSchema(SAMPLE.name, 2, SAMPLE.schema, path=SAMPLE.path)
    p.store.write(newer, sample_rows(("a", "1")))
    before = p.store.resolve(SAMPLE.path).read_bytes()

    with pytest.raises(PersistenceError, match="schema version 2, expected 1"):
        _open(data_dir, DerivedRegistry())
    assert p.store.resolve(SAMPLE.path).read_bytes() == before


def test_startup_removes_stale_temp_files(data_dir: Path) -> None:
    p = _open(data_dir, DerivedRegistry(), backup_on_startup=False)
    leftover = p.store.data_dir / "transactions" / ".tmp-x.parquet.1.tmp"
    leftover.write_bytes(b"partial")
    _open(data_dir, DerivedRegistry(), backup_on_startup=False)
    assert not leftover.exists()
