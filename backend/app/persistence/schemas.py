"""Dataset schema declarations and validation.

Every persisted dataset is described by a ``DatasetSchema``: an Arrow schema,
a version and (optionally) unique key columns. The name and version are
stored in each Parquet file's metadata so incompatible files are detected on
read instead of being silently misinterpreted or overwritten.

Entity modules register their datasets with ``register_dataset`` (portfolios
in Phase 4, transactions/positions in Phase 5, ...).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath

import pyarrow as pa

from app.persistence.errors import SchemaValidationError

META_DATASET = b"mtp_dataset"
META_VERSION = b"mtp_schema_version"


@dataclass(frozen=True)
class DatasetSchema:
    name: str
    version: int
    schema: pa.Schema
    key: tuple[str, ...] = ()
    # Path relative to the data directory for single-file datasets; None for
    # partitioned datasets (e.g. one close-price file per trading date).
    path: PurePosixPath | None = None
    description: str = field(default="", compare=False)

    def __post_init__(self) -> None:
        missing = [k for k in self.key if k not in self.schema.names]
        if missing:
            raise ValueError(f"Dataset {self.name}: key columns {missing} not in schema")
        if self.path is not None and (self.path.is_absolute() or ".." in self.path.parts):
            raise ValueError(f"Dataset {self.name}: path must be relative to the data directory")

    def metadata(self) -> dict[bytes, bytes]:
        return {META_DATASET: self.name.encode(), META_VERSION: str(self.version).encode()}

    def empty_table(self) -> pa.Table:
        return self.schema.empty_table().replace_schema_metadata(self.metadata())


_REGISTRY: dict[str, DatasetSchema] = {}


def register_dataset(dataset: DatasetSchema) -> DatasetSchema:
    existing = _REGISTRY.get(dataset.name)
    if existing is not None and existing != dataset:
        raise ValueError(f"Dataset {dataset.name!r} is already registered with a different definition")
    _REGISTRY[dataset.name] = dataset
    return dataset


def registered_datasets() -> list[DatasetSchema]:
    return list(_REGISTRY.values())


def validate_table(table: pa.Table, dataset: DatasetSchema) -> pa.Table:
    """Return ``table`` conformed to the dataset schema, or raise.

    * Columns must match by name exactly (order may differ; it is normalised).
    * Types must match exactly; no implicit casting, so precision is never lost.
    * Non-nullable fields must not contain nulls.
    * Key columns, if declared, must be unique.
    """
    expected = dataset.schema
    actual_names = set(table.column_names)
    expected_names = set(expected.names)
    if actual_names != expected_names:
        missing = sorted(expected_names - actual_names)
        extra = sorted(actual_names - expected_names)
        raise SchemaValidationError(
            f"Dataset {dataset.name}: column mismatch (missing={missing}, unexpected={extra})"
        )

    table = table.select(expected.names)
    for fld in expected:
        column = table.column(fld.name)
        if not column.type.equals(fld.type):
            raise SchemaValidationError(
                f"Dataset {dataset.name}: column {fld.name!r} has type {column.type}, expected {fld.type}"
            )
        if not fld.nullable and column.null_count:
            raise SchemaValidationError(
                f"Dataset {dataset.name}: column {fld.name!r} contains {column.null_count} null value(s)"
            )

    if dataset.key and table.num_rows:
        unique = table.group_by(list(dataset.key)).aggregate([]).num_rows
        if unique != table.num_rows:
            raise SchemaValidationError(
                f"Dataset {dataset.name}: duplicate values for key {list(dataset.key)}"
            )

    # Rebuild with the declared schema so field nullability flags match exactly.
    return pa.Table.from_arrays(table.columns, schema=expected).replace_schema_metadata(
        dataset.metadata()
    )


def check_stored_schema(schema: pa.Schema, dataset: DatasetSchema) -> str | None:
    """Return a description of why a stored schema is incompatible, or None."""
    meta = schema.metadata or {}
    name = meta.get(META_DATASET, b"").decode()
    version = meta.get(META_VERSION, b"").decode()
    if name != dataset.name:
        return f"file belongs to dataset {name or '<unknown>'!r}, expected {dataset.name!r}"
    if version != str(dataset.version):
        return f"file has schema version {version or '<missing>'}, expected {dataset.version}"
    stored = pa.schema([schema.field(n) for n in schema.names])
    if not stored.remove_metadata().equals(dataset.schema.remove_metadata()):
        return "file columns/types differ from the declared schema"
    return None

