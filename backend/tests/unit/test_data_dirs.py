from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.persistence.data_dirs import (
    DATA_SCHEMA_VERSION,
    DATA_SUBDIRECTORIES,
    SCHEMA_VERSION_FILE,
    DataDirectoryError,
    initialise_data_dirs,
)


def test_creates_full_tree_and_schema_version(data_dir: Path) -> None:
    info = initialise_data_dirs(data_dir)

    assert info.created is True
    assert info.schema_version == DATA_SCHEMA_VERSION
    for sub in DATA_SUBDIRECTORIES:
        assert (data_dir / sub).is_dir(), sub
    stored = json.loads((data_dir / SCHEMA_VERSION_FILE).read_text())
    assert stored["schema_version"] == DATA_SCHEMA_VERSION
    assert "created_at" in stored
    assert not list((data_dir / "metadata").glob("*.tmp")), "temp file left behind"


def test_is_idempotent_and_preserves_existing_files(data_dir: Path) -> None:
    initialise_data_dirs(data_dir)
    version_file = data_dir / SCHEMA_VERSION_FILE
    original = version_file.read_text()
    marker = data_dir / "portfolios" / "keep.txt"
    marker.write_text("x")

    info = initialise_data_dirs(data_dir)

    assert info.created is False
    assert version_file.read_text() == original
    assert marker.read_text() == "x"


def test_recreates_missing_subdirectory(data_dir: Path) -> None:
    initialise_data_dirs(data_dir)
    (data_dir / "backups").rmdir()
    initialise_data_dirs(data_dir)
    assert (data_dir / "backups").is_dir()


def test_incompatible_schema_version_is_rejected_and_not_overwritten(data_dir: Path) -> None:
    (data_dir / "metadata").mkdir(parents=True)
    version_file = data_dir / SCHEMA_VERSION_FILE
    content = json.dumps({"schema_version": DATA_SCHEMA_VERSION + 1})
    version_file.write_text(content)

    with pytest.raises(DataDirectoryError, match="migration is required"):
        initialise_data_dirs(data_dir)
    assert version_file.read_text() == content


@pytest.mark.parametrize("content", ["not json", "{}", '{"schema_version": "1"}'])
def test_corrupt_schema_version_is_rejected(data_dir: Path, content: str) -> None:
    (data_dir / "metadata").mkdir(parents=True)
    (data_dir / SCHEMA_VERSION_FILE).write_text(content)
    with pytest.raises(DataDirectoryError):
        initialise_data_dirs(data_dir)


def test_unwritable_location_reports_clear_error(tmp_path: Path) -> None:
    blocker = tmp_path / "file"
    blocker.write_text("not a directory")
    with pytest.raises(DataDirectoryError, match="Cannot create data directory"):
        initialise_data_dirs(blocker / "data")
