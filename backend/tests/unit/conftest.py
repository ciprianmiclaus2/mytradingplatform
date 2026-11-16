from __future__ import annotations

from pathlib import Path

import pytest

from app.persistence.data_dirs import initialise_data_dirs
from app.persistence.locking import DataLock
from app.persistence.parquet import ParquetStore


@pytest.fixture
def initialised_dir(data_dir: Path) -> Path:
    initialise_data_dirs(data_dir)
    return data_dir


@pytest.fixture
def lock(initialised_dir: Path) -> DataLock:
    return DataLock(initialised_dir, timeout=5)


@pytest.fixture
def store(initialised_dir: Path, lock: DataLock) -> ParquetStore:
    return ParquetStore(initialised_dir, lock)
