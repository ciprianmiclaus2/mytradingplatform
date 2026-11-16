"""Persistence layer: the only code that touches files in the data directory."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.persistence.backup import BackupManager
from app.persistence.data_dirs import DataDirectoryInfo, initialise_data_dirs
from app.persistence.derived import DerivedRegistry, derived_registry
from app.persistence.locking import DataLock
from app.persistence.parquet import ParquetStore
from app.persistence.schemas import registered_datasets

logger = logging.getLogger(__name__)


@dataclass
class Persistence:
    """Bundle of persistence services shared by the application."""

    info: DataDirectoryInfo
    lock: DataLock
    store: ParquetStore
    backups: BackupManager
    derived: DerivedRegistry


def open_persistence(
    data_dir: Path,
    *,
    lock_timeout: float,
    backup_retention: int,
    backup_on_startup: bool,
    derived: DerivedRegistry = derived_registry,
) -> Persistence:
    """Initialise and validate the data directory. Never overwrites incompatible data.

    Startup sequence:
      1. create directories / check data schema version;
      2. remove temp files left by an interrupted write;
      3. validate every registered dataset file (raises on incompatibility);
      4. rebuild derived datasets whose sources changed (deterministic from sources);
      5. back up the now-consistent state (skipped if unchanged since the last backup).
    """
    info = initialise_data_dirs(data_dir)
    lock = DataLock(data_dir, timeout=lock_timeout)
    store = ParquetStore(data_dir, lock)
    backups = BackupManager(data_dir, lock, backup_retention)

    store.remove_stale_temp_files()
    checked = store.validate_registered(registered_datasets())
    logger.info("data files validated", extra={"files": checked})
    rebuilt = derived.rebuild_stale(store)
    if rebuilt:
        logger.warning("stale derived datasets rebuilt", extra={"datasets": rebuilt})
    if backup_on_startup:
        backups.create_backup("startup", skip_if_unchanged=True)

    return Persistence(info=info, lock=lock, store=store, backups=backups, derived=derived)
