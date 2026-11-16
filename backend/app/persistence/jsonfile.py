"""Small JSON documents (status files) with atomic, locked writes."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any

from app.persistence.errors import CorruptFileError, PersistenceError
from app.persistence.parquet import TEMP_PREFIX, ParquetStore, fsync_directory

logger = logging.getLogger(__name__)


def read_json(store: ParquetStore, relative: str | PurePosixPath) -> Any | None:
    """Return the parsed document, or None if the file does not exist."""
    path = store.resolve(relative)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise CorruptFileError(f"{relative} cannot be read: {exc}") from exc


def write_json(store: ParquetStore, relative: str | PurePosixPath, document: Any) -> None:
    path = store.resolve(relative)
    with store.lock.hold():
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f"{TEMP_PREFIX}{path.name}.", suffix=".tmp")
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(document, fh, indent=2, sort_keys=True, default=str)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
            fsync_directory(path.parent)
        except Exception as exc:
            tmp.unlink(missing_ok=True)
            raise PersistenceError(f"Failed to write {relative}: {exc}") from exc
