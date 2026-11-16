"""Rebuildable derived datasets (materialised views).

A derived dataset (e.g. ``history.parquet`` from the daily close-price files) is computed entirely from
its source files. When it is written, a fingerprint of the sources is stored
in its metadata. If the sources later change without the derived file being
updated (e.g. a crash between the two writes), the fingerprints no longer
match, the derived file is reported stale, and it can be rebuilt.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import PurePosixPath

import pyarrow as pa

from app.persistence.errors import PersistenceError
from app.persistence.parquet import TEMP_PREFIX, ParquetStore
from app.persistence.schemas import DatasetSchema

logger = logging.getLogger(__name__)

FINGERPRINT_KEY = "x_source_fingerprint"


@dataclass(frozen=True)
class DerivedDataset:
    output: DatasetSchema  # must be a single-file dataset
    # Data-relative paths or globs of the source files, e.g. "market_data/close_prices/*.parquet".
    sources: tuple[str, ...]
    build: Callable[[ParquetStore], pa.Table]

    def __post_init__(self) -> None:
        if self.output.path is None:
            raise ValueError(f"Derived dataset {self.output.name} must have a fixed output path")

    @property
    def name(self) -> str:
        return self.output.name


def source_fingerprint(store: ParquetStore, sources: tuple[str, ...]) -> str:
    """SHA-256 over the relative path and content of every source file."""
    files: set[PurePosixPath] = set()
    for pattern in sources:
        rel = PurePosixPath(pattern)
        base = store.resolve(rel.parent) if rel.parent != PurePosixPath(".") else store.data_dir
        for path in base.glob(rel.name):
            if path.is_file() and not path.name.startswith(TEMP_PREFIX):
                files.add(PurePosixPath(path.relative_to(store.data_dir).as_posix()))
    digest = hashlib.sha256()
    for rel in sorted(files):
        digest.update(str(rel).encode() + b"\0")
        with store.resolve(rel).open("rb") as fh:
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                digest.update(chunk)
        digest.update(b"\0")
    return digest.hexdigest()


class DerivedRegistry:
    def __init__(self) -> None:
        self._items: dict[str, DerivedDataset] = {}

    def register(self, derived: DerivedDataset) -> DerivedDataset:
        if derived.name in self._items:
            raise ValueError(f"Derived dataset {derived.name!r} already registered")
        self._items[derived.name] = derived
        return derived

    def names(self) -> list[str]:
        return list(self._items)

    def get(self, name: str) -> DerivedDataset:
        try:
            return self._items[name]
        except KeyError:
            raise PersistenceError(f"Unknown derived dataset {name!r}") from None

    def is_stale(self, store: ParquetStore, name: str) -> bool:
        derived = self.get(name)
        meta = store.read_metadata(derived.output)
        if meta is None:
            return True
        return meta.get(FINGERPRINT_KEY) != source_fingerprint(store, derived.sources)

    def rebuild(self, store: ParquetStore, name: str) -> int:
        """Rebuild one derived dataset from its sources; returns the row count."""
        derived = self.get(name)
        with store.lock.hold():  # sources cannot change during the rebuild
            fingerprint = source_fingerprint(store, derived.sources)
            table = derived.build(store)
            store.write(derived.output, table, extra_metadata={FINGERPRINT_KEY: fingerprint})
        logger.info("derived dataset rebuilt", extra={"dataset": name, "rows": table.num_rows})
        return table.num_rows

    def write(self, store: ParquetStore, name: str, table: pa.Table) -> None:
        """Write an incrementally maintained derived table, stamping the fingerprint.

        Call while holding the write lock, after the source files are written,
        so the fingerprint reflects exactly the sources the table was built from.
        """
        derived = self.get(name)
        if not store.lock.is_held_by_current_thread():
            raise PersistenceError("Derived datasets must be written while holding the write lock")
        fingerprint = source_fingerprint(store, derived.sources)
        store.write(derived.output, table, extra_metadata={FINGERPRINT_KEY: fingerprint})

    def missing(self, store: ParquetStore) -> list[str]:
        """Derived datasets whose output file does not exist yet (e.g. a new data directory)."""
        return [name for name in self._items if store.read_metadata(self.get(name).output) is None]

    def rebuild_stale(self, store: ParquetStore) -> list[str]:
        rebuilt = []
        for name in self._items:
            with store.lock.hold():
                if self.is_stale(store, name):
                    self.rebuild(store, name)
                    rebuilt.append(name)
        return rebuilt


# Process-wide registry; entity modules register their derived datasets here.
derived_registry = DerivedRegistry()
