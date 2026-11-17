"""Data directory layout and initialisation."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

logger = logging.getLogger(__name__)

# Bump when the persisted data layout or any Parquet schema changes incompatibly.
DATA_SCHEMA_VERSION = 1

SCHEMA_VERSION_FILE = Path("metadata") / "schema_version.json"

DATA_SUBDIRECTORIES: tuple[Path, ...] = (
    Path("market_data/close_prices"),
    Path("market_data/current"),
    Path("market_data/history"),
    Path("portfolios"),
    Path("brokers"),
    Path("strategies"),
    Path("backups"),
    Path("metadata"),
)


class DataDirectoryError(RuntimeError):
    """The data directory cannot be used (unwritable, incompatible, corrupt)."""


@dataclass(frozen=True)
class DataDirectoryInfo:
    root: Path
    schema_version: int
    created: bool


def initialise_data_dirs(root: Path) -> DataDirectoryInfo:
    """Create the data directory tree and validate/record the schema version.

    Never overwrites an existing schema version file: an unreadable or
    incompatible file raises ``DataDirectoryError`` instead.
    """
    try:
        root.mkdir(parents=True, exist_ok=True)
        for sub in DATA_SUBDIRECTORIES:
            (root / sub).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise DataDirectoryError(f"Cannot create data directory {root}: {exc}") from exc

    version_path = root / SCHEMA_VERSION_FILE
    if not version_path.exists():
        _write_json_atomic(
            version_path,
            {
                "schema_version": DATA_SCHEMA_VERSION,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )
        logger.info("data directory initialised", extra={"data_dir": str(root)})
        return DataDirectoryInfo(root=root, schema_version=DATA_SCHEMA_VERSION, created=True)

    version = read_schema_version(version_path)
    if version != DATA_SCHEMA_VERSION:
        raise DataDirectoryError(
            f"Data directory {root} has schema version {version}, "
            f"but this application requires version {DATA_SCHEMA_VERSION}. "
            "A migration is required; existing data was left untouched."
        )
    return DataDirectoryInfo(root=root, schema_version=version, created=False)


def read_schema_version(path: Path) -> int:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        version = data["schema_version"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DataDirectoryError(f"Schema version file {path} is unreadable: {exc}") from exc
    if not isinstance(version, int) or isinstance(version, bool):
        raise DataDirectoryError(f"Schema version file {path} has invalid version {version!r}")
    return version


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
