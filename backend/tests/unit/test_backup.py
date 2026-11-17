from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from app.persistence import backup as backup_mod
from app.persistence.backup import BackupManager
from app.persistence.errors import BackupError
from app.persistence.locking import DataLock
from app.persistence.parquet import ParquetStore
from tests.helpers import SAMPLE, sample_rows


@pytest.fixture
def backups(initialised_dir: Path, lock: DataLock) -> BackupManager:
    return BackupManager(initialised_dir, lock, retention=3)


def _seed(store: ParquetStore) -> None:
    store.write(SAMPLE, sample_rows(("a", "1")))
    (store.data_dir / "portfolios" / "p.json").write_text("{}")
    (store.data_dir / "market_data" / "current" / "current.parquet").write_bytes(b"md")


def test_backup_contains_state_and_excludes_market_data(
    store: ParquetStore, backups: BackupManager
) -> None:
    _seed(store)
    with store.lock.hold():  # creates the lock file
        pass

    info = backups.create_backup("manual")

    assert info is not None
    manifest = json.loads((info.path / "manifest.json").read_text())
    assert set(manifest["files"]) == {
        "strategies/sample.parquet",
        "portfolios/p.json",
        "metadata/schema_version.json",
    }
    assert manifest["reason"] == "manual" and manifest["schema_version"] == 1
    assert (info.path / "strategies/sample.parquet").read_bytes() == store.resolve(SAMPLE.path).read_bytes()
    assert not list(info.path.rglob("*.lock"))
    backups.verify_backup(info.name)


def test_skip_if_unchanged(store: ParquetStore, backups: BackupManager) -> None:
    _seed(store)
    assert backups.create_backup("startup", skip_if_unchanged=True) is not None
    assert backups.create_backup("startup", skip_if_unchanged=True) is None
    store.write(SAMPLE, sample_rows(("b", "2")))
    assert backups.create_backup("startup", skip_if_unchanged=True) is not None
    assert len(backups.list_backups()) == 2


def test_retention_prunes_oldest(store: ParquetStore, backups: BackupManager) -> None:
    _seed(store)
    names = [backups.create_backup(f"b{i}").name for i in range(5)]  # type: ignore[union-attr]
    assert [b.name for b in backups.list_backups()] == names[-3:]


def test_reason_is_sanitised(backups: BackupManager) -> None:
    info = backups.create_backup("Before DELETE position ../x")
    assert info is not None and info.name.endswith("-before-delete-position-x")
    assert info.path.parent == backups.backup_root


def test_failed_backup_leaves_no_partial_directory(
    store: ParquetStore, backups: BackupManager, monkeypatch: pytest.MonkeyPatch
) -> None:
    _seed(store)

    def failing_copy(*_a, **_k):  # type: ignore[no-untyped-def]
        raise OSError("disk full")

    monkeypatch.setattr(backup_mod.shutil, "copy2", failing_copy)
    with pytest.raises(BackupError, match="disk full"):
        backups.create_backup("manual")
    assert list(backups.backup_root.iterdir()) == []


def test_verify_detects_tampering_and_missing_files(store: ParquetStore, backups: BackupManager) -> None:
    _seed(store)
    info = backups.create_backup("manual")
    assert info is not None
    (info.path / "portfolios/p.json").write_text('{"tampered": true}')
    with pytest.raises(BackupError, match="fails checksum"):
        backups.verify_backup(info.name)
    (info.path / "portfolios/p.json").unlink()
    with pytest.raises(BackupError, match="missing"):
        backups.verify_backup(info.name)


def test_restore_returns_state_and_takes_pre_restore_backup(
    store: ParquetStore, backups: BackupManager
) -> None:
    _seed(store)
    info = backups.create_backup("good")
    assert info is not None

    # Damage the state after the backup.
    store.write(SAMPLE, sample_rows(("wrong", "999")))
    (store.data_dir / "portfolios" / "p.json").unlink()
    (store.data_dir / "portfolios" / "new.json").write_text("{}")
    market = store.data_dir / "market_data" / "current" / "current.parquet"

    pre = backups.restore_backup(info.name)

    assert store.read(SAMPLE).column("id").to_pylist() == ["a"]
    assert (store.data_dir / "portfolios" / "p.json").exists()
    assert not (store.data_dir / "portfolios" / "new.json").exists()
    assert market.read_bytes() == b"md"  # market data untouched
    assert pre is not None and "pre-restore" in pre.name
    pre_manifest = backups.verify_backup(pre.name)
    assert "portfolios/new.json" in pre_manifest["files"]


def test_restore_unknown_backup(backups: BackupManager) -> None:
    with pytest.raises(BackupError, match="not found"):
        backups.restore_backup("20990101T000000000000Z-nope")
    with pytest.raises(BackupError, match="not found"):
        backups.restore_backup("../../etc")


def test_restore_refuses_other_schema_version(store: ParquetStore, backups: BackupManager) -> None:
    _seed(store)
    info = backups.create_backup("manual")
    assert info is not None
    manifest_path = info.path / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["schema_version"] = 99
    manifest_path.write_text(json.dumps(manifest))
    before = store.resolve(SAMPLE.path).read_bytes()

    with pytest.raises(BackupError, match="schema version 99"):
        backups.restore_backup(info.name)
    assert store.resolve(SAMPLE.path).read_bytes() == before


def test_invalid_backups_and_staging_dirs_are_ignored(store: ParquetStore, backups: BackupManager) -> None:
    _seed(store)
    backups.backup_root.mkdir(exist_ok=True)
    (backups.backup_root / "random-folder").mkdir()
    (backups.backup_root / ".tmp-backup-20261116T000000000000Z-x").mkdir()
    broken = backups.backup_root / "20261116T000000000000Z-broken"
    broken.mkdir()

    assert backups.list_backups() == []
    backups.create_backup("manual")
    assert not (backups.backup_root / ".tmp-backup-20261116T000000000000Z-x").exists()
    assert (backups.backup_root / "random-folder").exists()
    shutil.rmtree(broken)
