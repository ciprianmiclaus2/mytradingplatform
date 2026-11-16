from __future__ import annotations

import multiprocessing as mp
import threading
from pathlib import Path

import pytest

from app.persistence.errors import LockTimeoutError
from app.persistence.locking import DataLock
from app.persistence.parquet import ParquetStore
from tests.helpers import (
    SAMPLE,
    append_rows,
    hold_lock_worker,
    process_increment_worker,
    sample_rows,
)


def test_lock_is_reentrant(lock: DataLock) -> None:
    assert not lock.is_held_by_current_thread()
    with lock.hold():
        with lock.hold():
            assert lock.is_held_by_current_thread()
        assert lock.is_held_by_current_thread()
    assert not lock.is_held_by_current_thread()


def test_concurrent_thread_writes_are_serialised(store: ParquetStore) -> None:
    threads, per_thread = 8, 20
    errors: list[BaseException] = []

    def worker(w: int) -> None:
        try:
            for n in range(per_thread):
                store.update(SAMPLE, lambda t, n=n: append_rows(t, sample_rows((f"t{w}-{n}", "1"))))
        except BaseException as exc:  # pragma: no cover - surfaced by assertion
            errors.append(exc)

    pool = [threading.Thread(target=worker, args=(w,)) for w in range(threads)]
    for t in pool:
        t.start()
    for t in pool:
        t.join()

    assert not errors
    assert store.read(SAMPLE).num_rows == threads * per_thread  # no lost updates


def test_concurrent_process_writes_are_serialised(store: ParquetStore) -> None:
    ctx = mp.get_context("spawn")
    processes, per_process = 3, 10
    procs = [
        ctx.Process(target=process_increment_worker, args=(str(store.data_dir), w, per_process))
        for w in range(processes)
    ]
    for p in procs:
        p.start()
    # The backend process writes at the same time as the "scripts".
    for n in range(per_process):
        store.update(SAMPLE, lambda t, n=n: append_rows(t, sample_rows((f"main-{n}", "1"))))
    for p in procs:
        p.join(60)
        assert p.exitcode == 0

    assert store.read(SAMPLE).num_rows == (processes + 1) * per_process


def test_lock_timeout_when_other_process_holds_lock(initialised_dir: Path) -> None:
    ctx = mp.get_context("spawn")
    ready, release = ctx.Event(), ctx.Event()
    proc = ctx.Process(target=hold_lock_worker, args=(str(initialised_dir), ready, release))
    proc.start()
    try:
        assert ready.wait(30)
        with pytest.raises(LockTimeoutError, match="another process"):
            with DataLock(initialised_dir).hold(timeout=0.2):
                pass
    finally:
        release.set()
        proc.join(30)
    with DataLock(initialised_dir).hold(timeout=5):
        pass  # acquirable once released


def test_lock_timeout_when_other_thread_holds_lock(lock: DataLock) -> None:
    holding, release = threading.Event(), threading.Event()

    def holder() -> None:
        with lock.hold():
            holding.set()
            release.wait(5)

    t = threading.Thread(target=holder)
    t.start()
    try:
        holding.wait(5)
        with pytest.raises(LockTimeoutError):
            with lock.hold(timeout=0.1):
                pass
    finally:
        release.set()
        t.join()
