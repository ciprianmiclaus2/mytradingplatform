#!/usr/bin/env python3
"""Create, list, verify and restore application-state backups.

Run with the backend virtual environment, e.g.:

    backend/.venv/bin/python scripts/backup_data.py create --reason before-upgrade
    backend/.venv/bin/python scripts/backup_data.py list
    backend/.venv/bin/python scripts/backup_data.py verify <name>
    backend/.venv/bin/python scripts/backup_data.py restore <name>

DATA_DIR and BACKUP_RETENTION_COUNT are read from the same settings as the
backend. Stop the backend before restoring.
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.logging_config import configure_logging
from app.persistence.backup import BackupManager
from app.persistence.data_dirs import initialise_data_dirs
from app.persistence.errors import PersistenceError
from app.persistence.locking import DataLock


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create", help="create a backup now")
    create.add_argument("--reason", default="manual")
    sub.add_parser("list", help="list backups, oldest first")
    verify = sub.add_parser("verify", help="verify a backup's checksums")
    verify.add_argument("name")
    restore = sub.add_parser("restore", help="restore a backup (current state is backed up first)")
    restore.add_argument("name")
    restore.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging("WARNING")
    try:
        initialise_data_dirs(settings.data_dir)
        manager = BackupManager(
            settings.data_dir,
            DataLock(settings.data_dir, timeout=settings.persistence_lock_timeout),
            settings.backup_retention_count,
        )
        print(f"Data directory: {settings.data_dir}")

        if args.command == "create":
            info = manager.create_backup(args.reason)
            assert info is not None
            print(f"Created {info.name} ({info.file_count} files)")
        elif args.command == "list":
            backups = manager.list_backups()
            if not backups:
                print("No backups.")
            for b in backups:
                print(f"{b.name}  {b.created_at:%Y-%m-%d %H:%M:%S}Z  files={b.file_count}  reason={b.reason}")
        elif args.command == "verify":
            manifest = manager.verify_backup(args.name)
            print(f"OK: {args.name} ({len(manifest['files'])} files verified)")
        elif args.command == "restore":
            if not args.yes:
                answer = input(f"Restore {args.name}? Current state will be backed up first. [y/N] ")
                if answer.strip().lower() not in ("y", "yes"):
                    print("Cancelled.")
                    return 1
            pre = manager.restore_backup(args.name)
            print(f"Restored {args.name}. Previous state saved as {pre.name if pre else '-'}.")
    except PersistenceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
