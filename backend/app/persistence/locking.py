"""Data-store write lock.

V1 uses a single write lock for all application state. Writes are rare in a
single-user application, and one lock makes multi-file updates (for example a
portfolio plus the positions that belong to it) trivially consistent.

The lock combines:

* a re-entrant thread lock, serialising writers inside the backend process;
* an OS file lock, serialising the backend with maintenance scripts
  (backup / rebuild) that may run in a separate process.

Readers do not take the lock: every file is replaced atomically, so a reader
always sees either the old or the new complete file.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import filelock

from app.persistence.errors import LockTimeoutError

logger = logging.getLogger(__name__)

LOCK_FILE = Path("metadata") / ".write.lock"


class DataLock:
    def __init__(self, data_dir: Path, timeout: float = 10.0) -> None:
        self._path = data_dir / LOCK_FILE
        self._timeout = timeout
        self._thread_lock = threading.RLock()
        # thread_local=False: ownership is managed by the RLock above, and the
        # OS lock is held for as long as any re-entrant acquisition is active.
        self._file_lock = filelock.FileLock(self._path, thread_local=False)
        self._depth = 0

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def hold(self, timeout: float | None = None) -> Iterator[None]:
        """Hold the write lock; re-entrant within the same thread."""
        timeout = self._timeout if timeout is None else timeout
        start = time.monotonic()
        if not self._thread_lock.acquire(timeout=timeout):
            raise LockTimeoutError("Timed out waiting for the data write lock")
        try:
            if self._depth == 0:
                remaining = max(0.0, timeout - (time.monotonic() - start))
                try:
                    self._file_lock.acquire(timeout=remaining)
                except filelock.Timeout as exc:
                    raise LockTimeoutError(
                        "Timed out waiting for the data write lock "
                        "(another process, such as a maintenance script, is writing)"
                    ) from exc
            self._depth += 1
            try:
                yield
            finally:
                self._depth -= 1
                if self._depth == 0:
                    self._file_lock.release()
        finally:
            self._thread_lock.release()

    def is_held_by_current_thread(self) -> bool:
        # RLock has no public owner check; _is_owned is stable across CPython versions.
        return bool(self._thread_lock._is_owned()) and self._depth > 0  # type: ignore[attr-defined]
