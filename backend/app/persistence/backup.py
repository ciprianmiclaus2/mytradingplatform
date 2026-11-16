"""Backups of application state.

A backup is a timestamped directory under ``backups/`` containing copies of
the application-state directories plus a ``manifest.json`` with SHA-256
checksums. Market data is excluded: it can be downloaded again.

Backups are written to a staging directory and renamed into place, so a
crash never leaves a half-written backup that looks complete.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from app.persistence.data_dirs import DATA_SCHEMA_VERSION
from app.persistence.errors import BackupError
from app.persistence.locking import LOCK_FILE, DataLock
from app.persistence.parquet import TEMP_PREFIX, fsync_directory

logger = logging.getLogger(__name__)

BACKUP_DIR = "backups"
BACKED_UP_DIRS: tuple[str, ...] = ("portfolios", "positions", "strategies", "metadata")
MANIFEST = "manifest.json"
_NAME_RE = re.compile(r"^\d{8}T\d{12}Z-[a-z0-9-]+$")
_STAGING_PREFIX = f"{TEMP_PREFIX}backup-"


@dataclass(frozen=True)
class BackupInfo:
    name: str
    path: Path
    created_at: datetime
    reason: str
    schema_version: int
    file_count: int


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _slug(reason: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", reason.lower()).strip("-")
    return slug[:40] or "manual"


class BackupManager:
    def __init__(self, data_dir: Path, lock: DataLock, retention: int) -> None:
        if retention < 1:
            raise ValueError("retention must be >= 1")
        self.data_dir = data_dir.resolve()
        self.backup_root = self.data_dir / BACKUP_DIR
        self.lock = lock
        self.retention = retention

    # -- inventory ---------------------------------------------------------------

    def _state_files(self) -> dict[str, Path]:
        """Application-state files to back up, keyed by data-relative POSIX path."""
        lock_rel = LOCK_FILE.as_posix()
        files: dict[str, Path] = {}
        for sub in BACKED_UP_DIRS:
            root = self.data_dir / sub
            if not root.is_dir():
                continue
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.name.startswith(TEMP_PREFIX):
                    continue
                rel = path.relative_to(self.data_dir).as_posix()
                if rel == lock_rel:
                    continue
                files[rel] = path
        return files

    def list_backups(self) -> list[BackupInfo]:
        """Completed backups, oldest first."""
        if not self.backup_root.is_dir():
            return []
        result = []
        for entry in sorted(self.backup_root.iterdir()):
            if entry.is_dir() and _NAME_RE.match(entry.name):
                try:
                    manifest = self._load_manifest(entry)
                except BackupError:
                    logger.warning("ignoring backup with invalid manifest", extra={"backup": entry.name})
                    continue
                result.append(
                    BackupInfo(
                        name=entry.name,
                        path=entry,
                        created_at=datetime.fromisoformat(manifest["created_at"]),
                        reason=manifest["reason"],
                        schema_version=manifest["schema_version"],
                        file_count=len(manifest["files"]),
                    )
                )
        return result

    # -- create ----------------------------------------------------------------

    def create_backup(
        self, reason: str = "manual", *, skip_if_unchanged: bool = False, prune: bool = True
    ) -> BackupInfo | None:
        """Back up application state. Returns None if skipped as unchanged."""
        with self.lock.hold():
            files = self._state_files()
            checksums = {rel: _sha256(p) for rel, p in files.items()}

            if skip_if_unchanged:
                latest = self.list_backups()
                if latest and self._load_manifest(latest[-1].path)["files"] == {
                    rel: {"sha256": c, "size": files[rel].stat().st_size} for rel, c in checksums.items()
                }:
                    logger.info("backup skipped: state unchanged", extra={"reason": reason})
                    return None

            now = datetime.now(UTC)
            name = f"{now.strftime('%Y%m%dT%H%M%S%f')}Z-{_slug(reason)}"
            self.backup_root.mkdir(parents=True, exist_ok=True)
            staging = self.backup_root / f"{_STAGING_PREFIX}{name}"
            final = self.backup_root / name
            try:
                staging.mkdir()
                manifest_files = {}
                for rel, src in files.items():
                    dst = staging / rel
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(src, dst)
                    if _sha256(dst) != checksums[rel]:
                        raise BackupError(f"File {rel} changed while being backed up")
                    manifest_files[rel] = {"sha256": checksums[rel], "size": dst.stat().st_size}
                manifest = {
                    "created_at": now.isoformat(),
                    "reason": reason,
                    "schema_version": DATA_SCHEMA_VERSION,
                    "files": manifest_files,
                }
                with (staging / MANIFEST).open("w", encoding="utf-8") as fh:
                    json.dump(manifest, fh, indent=2, sort_keys=True)
                    fh.flush()
                    os.fsync(fh.fileno())
                os.rename(staging, final)
                fsync_directory(self.backup_root)
            except Exception as exc:
                shutil.rmtree(staging, ignore_errors=True)
                logger.error("backup failed", extra={"reason": reason, "error": str(exc)})
                if isinstance(exc, BackupError):
                    raise
                raise BackupError(f"Backup failed: {exc}") from exc

            logger.info("backup created", extra={"backup": name, "reason": reason, "files": len(files)})
            if prune:
                self.prune()
            return BackupInfo(name, final, now, reason, DATA_SCHEMA_VERSION, len(files))

    def prune(self, protect: str | None = None) -> list[str]:
        """Delete the oldest backups beyond the retention count and stale staging dirs."""
        removed: list[str] = []
        with self.lock.hold():
            if self.backup_root.is_dir():
                for entry in self.backup_root.iterdir():
                    if entry.is_dir() and entry.name.startswith(_STAGING_PREFIX):
                        shutil.rmtree(entry, ignore_errors=True)
            backups = [b for b in self.list_backups() if b.name != protect]
            keep = self.retention - (1 if protect else 0)
            for info in backups[: max(0, len(backups) - keep)]:
                shutil.rmtree(info.path)
                removed.append(info.name)
        if removed:
            logger.info("old backups pruned", extra={"removed": removed})
        return removed

    # -- verify / restore -----------------------------------------------------------

    def _load_manifest(self, backup_path: Path) -> dict:
        try:
            manifest = json.loads((backup_path / MANIFEST).read_text(encoding="utf-8"))
            missing = [k for k in ("created_at", "reason", "schema_version", "files") if k not in manifest]
            if missing:
                raise KeyError(", ".join(missing))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise BackupError(f"Backup {backup_path.name} has an invalid manifest: {exc}") from exc
        return manifest

    def _get(self, name: str) -> Path:
        path = self.backup_root / name
        if not _NAME_RE.match(name) or not path.is_dir():
            raise BackupError(f"Backup {name!r} not found")
        return path

    def verify_backup(self, name: str) -> dict:
        """Check every file against the manifest; return the manifest."""
        path = self._get(name)
        manifest = self._load_manifest(path)
        for rel, meta in manifest["files"].items():
            f = path / rel
            if not f.is_file():
                raise BackupError(f"Backup {name}: file {rel} is missing")
            if _sha256(f) != meta["sha256"]:
                raise BackupError(f"Backup {name}: file {rel} fails checksum verification")
        return manifest

    def restore_backup(self, name: str) -> BackupInfo | None:
        """Restore application state from a backup.

        The current state is backed up first ("pre-restore"). Files present now
        but absent from the backup are removed. Returns the pre-restore backup.
        """
        with self.lock.hold():
            manifest = self.verify_backup(name)
            if manifest["schema_version"] != DATA_SCHEMA_VERSION:
                raise BackupError(
                    f"Backup {name} has schema version {manifest['schema_version']}, "
                    f"current version is {DATA_SCHEMA_VERSION}; it cannot be restored directly"
                )
            src_root = self._get(name)
            pre = self.create_backup(f"pre-restore-{name[:15]}", prune=False)

            backup_files = set(manifest["files"])
            for rel, current in self._state_files().items():
                if rel not in backup_files:
                    current.unlink()
            for rel in sorted(backup_files):
                dst = self.data_dir / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.parent / f"{TEMP_PREFIX}{dst.name}.restore.tmp"
                shutil.copy2(src_root / rel, tmp)
                os.replace(tmp, dst)
            for sub in BACKED_UP_DIRS:
                if (self.data_dir / sub).is_dir():
                    fsync_directory(self.data_dir / sub)

            logger.warning("backup restored", extra={"backup": name, "files": len(backup_files)})
            self.prune(protect=pre.name if pre else None)
            return pre

