#!/usr/bin/env python3
"""Rebuild derived data (materialised views) from their authoritative sources.

    backend/.venv/bin/python scripts/rebuild_derived.py            # rebuild all
    backend/.venv/bin/python scripts/rebuild_derived.py --stale    # only stale ones
    backend/.venv/bin/python scripts/rebuild_derived.py --list
    backend/.venv/bin/python scripts/rebuild_derived.py <name> ...

Derived datasets are registered by the application modules that own them
(positions from the transaction ledger, market history from close prices).
"""

from __future__ import annotations

import argparse
import sys

import _bootstrap  # noqa: F401

from app.config import get_settings
from app.logging_config import configure_logging
from app.persistence.data_dirs import initialise_data_dirs
from app.persistence.derived import derived_registry
from app.persistence.errors import PersistenceError
from app.persistence.locking import DataLock
from app.persistence.parquet import ParquetStore


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help="derived datasets to rebuild (default: all)")
    parser.add_argument("--stale", action="store_true", help="only rebuild datasets whose sources changed")
    parser.add_argument("--list", action="store_true", help="list derived datasets and their state")
    args = parser.parse_args(argv)

    settings = get_settings()
    configure_logging("WARNING")
    try:
        initialise_data_dirs(settings.data_dir)
        store = ParquetStore(settings.data_dir, DataLock(settings.data_dir, settings.persistence_lock_timeout))
        names = args.names or derived_registry.names()
        print(f"Data directory: {settings.data_dir}")
        if not names:
            print("No derived datasets are registered yet.")
            return 0
        for name in names:
            stale = derived_registry.is_stale(store, name)
            if args.list:
                print(f"{name}: {'stale' if stale else 'up to date'}")
            elif stale or not args.stale:
                rows = derived_registry.rebuild(store, name)
                print(f"Rebuilt {name} ({rows} rows)")
            else:
                print(f"{name}: up to date")
    except PersistenceError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
