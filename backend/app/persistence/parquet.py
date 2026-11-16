"""Parquet read/write utilities with validation and atomic replacement.

Write protocol (plan §14.1):

1. Acquire the data write lock.
2. Validate the incoming table against the dataset schema.
3. Write to a temporary file in the same directory.
4. Flush and fsync the file.
5. Atomically replace the target (``os.replace``) and fsync the directory.
6. Release the lock.

Failures at any step leave the original file untouched and remove the
temporary file.
"""

from __future__ import annotations

import logging
import os
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath

import pyarrow as pa
import pyarrow.parquet as pq

from app.persistence.errors import (
    CorruptFileError,
    IncompatibleSchemaError,
    PersistenceError,
)
from app.persistence.locking import DataLock
from app.persistence.schemas import DatasetSchema, check_stored_schema, validate_table

logger = logging.getLogger(__name__)

TEMP_PREFIX = ".tmp-"


def fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_parquet_atomic(path: Path, table: pa.Table) -> None:
    """Write ``table`` to ``path`` atomically. Caller is responsible for locking."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{TEMP_PREFIX}{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            pq.write_table(table, fh, compression="zstd")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
        fsync_directory(path.parent)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def read_parquet_validated(path: Path, dataset: DatasetSchema, display_name: str) -> pa.Table:
    """Read and verify a stored file. Missing files are the caller's concern."""
    try:
        pf = pq.ParquetFile(path)
        stored_schema = pf.schema_arrow
    except (OSError, pa.ArrowException) as exc:
        raise CorruptFileError(f"{display_name} cannot be read: {exc}") from exc

    problem = check_stored_schema(stored_schema, dataset)
    if problem:
        raise IncompatibleSchemaError(f"{display_name} is incompatible: {problem}")

    try:
        table = pf.read()
    except (OSError, pa.ArrowException) as exc:
        raise CorruptFileError(f"{display_name} cannot be read: {exc}") from exc
    return table.select(dataset.schema.names)


class ParquetStore:
    """Validated, locked, atomic access to Parquet files under the data directory."""

    def __init__(self, data_dir: Path, lock: DataLock) -> None:
        self.data_dir = data_dir.resolve()
        self.lock = lock

    # -- paths -----------------------------------------------------------------

    def resolve(self, relative: str | PurePosixPath) -> Path:
        rel = PurePosixPath(relative)
        if rel.is_absolute() or ".." in rel.parts or not rel.parts:
            raise PersistenceError(f"Invalid data path {str(relative)!r}")
        return self.data_dir / Path(*rel.parts)

    def _path_for(self, dataset: DatasetSchema, relative: str | PurePosixPath | None) -> tuple[Path, str]:
        rel = relative if relative is not None else dataset.path
        if rel is None:
            raise PersistenceError(f"Dataset {dataset.name} is partitioned; a file path is required")
        return self.resolve(rel), str(PurePosixPath(rel))

    # -- reads -----------------------------------------------------------------

    def exists(self, dataset: DatasetSchema, relative: str | PurePosixPath | None = None) -> bool:
        return self._path_for(dataset, relative)[0].exists()

    def read(self, dataset: DatasetSchema, relative: str | PurePosixPath | None = None) -> pa.Table:
        """Read a dataset file; a missing file yields an empty table."""
        path, display = self._path_for(dataset, relative)
        if not path.exists():
            return dataset.empty_table()
        return read_parquet_validated(path, dataset, display)

    # -- writes ----------------------------------------------------------------

    def read_metadata(
        self, dataset: DatasetSchema, relative: str | PurePosixPath | None = None
    ) -> dict[str, str] | None:
        """Return a stored file's key/value metadata, or None if it does not exist."""
        path, display = self._path_for(dataset, relative)
        if not path.exists():
            return None
        try:
            meta = pq.read_schema(path).metadata or {}
        except (OSError, pa.ArrowException) as exc:
            raise CorruptFileError(f"{display} cannot be read: {exc}") from exc
        return {k.decode(errors="replace"): v.decode(errors="replace") for k, v in meta.items()}

    def write(
        self,
        dataset: DatasetSchema,
        table: pa.Table,
        relative: str | PurePosixPath | None = None,
        *,
        extra_metadata: dict[str, str] | None = None,
    ) -> None:
        path, display = self._path_for(dataset, relative)
        validated = validate_table(table, dataset)
        if extra_metadata:
            merged = dict(validated.schema.metadata or {})
            for key, value in extra_metadata.items():
                if not key.startswith("x_"):
                    raise PersistenceError("Extra metadata keys must start with 'x_'")
                merged[key.encode()] = value.encode()
            validated = validated.replace_schema_metadata(merged)
        with self.lock.hold():
            self._write_locked(path, display, dataset, validated)

    def update(
        self,
        dataset: DatasetSchema,
        transform: Callable[[pa.Table], pa.Table],
        relative: str | PurePosixPath | None = None,
    ) -> pa.Table:
        """Read-modify-write under the lock. Returns the table that was written."""
        path, display = self._path_for(dataset, relative)
        with self.lock.hold():
            current = self.read(dataset, relative)
            validated = validate_table(transform(current), dataset)
            self._write_locked(path, display, dataset, validated)
            return validated

    def delete(self, dataset: DatasetSchema, relative: str | PurePosixPath | None = None) -> bool:
        path, display = self._path_for(dataset, relative)
        with self.lock.hold():
            if not path.exists():
                return False
            try:
                path.unlink()
                fsync_directory(path.parent)
            except OSError as exc:
                logger.error("parquet delete failed", extra={"file": display, "error": str(exc)})
                raise PersistenceError(f"Failed to delete {display}: {exc}") from exc
            logger.info("parquet deleted", extra={"file": display, "dataset": dataset.name})
            return True

    def archive(
        self,
        dataset: DatasetSchema,
        new_relative: str | PurePosixPath,
        relative: str | PurePosixPath | None = None,
    ) -> bool:
        """Atomically rename a dataset file (e.g. rotation). Never overwrites a target."""
        src, display = self._path_for(dataset, relative)
        dst = self.resolve(new_relative)
        with self.lock.hold():
            if not src.exists():
                return False
            if dst.exists():
                raise PersistenceError(f"Archive target {new_relative} already exists")
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                os.rename(src, dst)
                fsync_directory(dst.parent)
            except OSError as exc:
                raise PersistenceError(f"Failed to archive {display}: {exc}") from exc
        logger.info("parquet archived", extra={"file": display, "archive": str(new_relative)})
        return True

    def _write_locked(self, path: Path, display: str, dataset: DatasetSchema, table: pa.Table) -> None:
        try:
            write_parquet_atomic(path, table)
        except Exception as exc:
            logger.error(
                "parquet write failed",
                extra={"file": display, "dataset": dataset.name, "error": str(exc)},
            )
            raise PersistenceError(f"Failed to write {display}: {exc}") from exc
        logger.info(
            "parquet written",
            extra={"file": display, "dataset": dataset.name, "rows": table.num_rows},
        )

    # -- maintenance -----------------------------------------------------------

    def validate_registered(self, datasets: list[DatasetSchema]) -> list[str]:
        """Validate every existing single-file dataset; return the files checked.

        Raises on the first incompatible or corrupt file. Never modifies data.
        """
        checked: list[str] = []
        for ds in datasets:
            if ds.path is None:
                continue
            path, display = self._path_for(ds, None)
            if path.exists():
                read_parquet_validated(path, ds, display)
                checked.append(display)
        return checked

    def remove_stale_temp_files(self) -> int:
        """Delete temp files left by a crash mid-write. Call with no writers active."""
        removed = 0
        with self.lock.hold():
            for tmp in self.data_dir.rglob(f"{TEMP_PREFIX}*.tmp"):
                if tmp.is_file():
                    tmp.unlink(missing_ok=True)
                    removed += 1
        if removed:
            logger.warning("removed stale temporary files", extra={"count": removed})
        return removed
