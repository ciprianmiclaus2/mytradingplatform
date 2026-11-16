#!/usr/bin/env python3
"""Rebuild market_data/history/history.parquet from the daily close-price files.

    backend/.venv/bin/python scripts/rebuild_history.py

history.parquet is a rebuildable materialised view; the authoritative cache is
market_data/close_prices/YYYYMMDD.parquet. Equivalent to
``scripts/rebuild_derived.py price_history``.
"""

from __future__ import annotations

import sys

import _bootstrap  # noqa: F401

from rebuild_derived import main

if __name__ == "__main__":
    sys.exit(main(["price_history", *sys.argv[1:]]))
