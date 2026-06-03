# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #1245.

``SQLitePostureStore.close()`` (and the sibling ``SqliteTrustStore._sync_close``)
previously closed only the *calling thread's* SQLite connection. Because
connections are cached per-thread via ``threading.local``, any connection opened
on a worker thread (e.g. via ``asyncio.to_thread`` running the synchronous store
methods off the event loop) was never closed — leaking the SQLite connection /
file descriptor until GC, surfacing as ``ResourceWarning: unclosed database`` and
blocking downstreams from enabling ``-W error::ResourceWarning``.

The fix tracks every per-thread connection in a lock-guarded ``_all_conns`` set
and closes them all on close(); ``check_same_thread=False`` permits the
cross-thread close at teardown.
"""

from __future__ import annotations

import gc
import sqlite3
import threading
import warnings

import pytest

from kailash.trust.chain_store.sqlite import SqliteTrustStore
from kailash.trust.plane.store.sqlite import SqliteTrustPlaneStore
from kailash.trust.posture.posture_store import SQLitePostureStore


@pytest.mark.regression
def test_issue_1245_posture_store_close_releases_cross_thread_connection(tmp_path):
    """close() on the main thread releases a connection opened on a worker thread."""
    store = SQLitePostureStore(str(tmp_path / "posture.db"))
    captured: dict[str, sqlite3.Connection] = {}

    def worker() -> None:
        # Public API; opens + caches a connection on THIS worker thread.
        store.get_posture("agent-1")
        captured["conn"] = store._local.conn

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    worker_conn = captured["conn"]
    assert worker_conn is not None
    assert worker_conn in store._all_conns

    store.close()  # called from the MAIN thread

    # The worker thread's connection MUST now be closed (the leak the bug left).
    with pytest.raises(sqlite3.ProgrammingError):
        worker_conn.execute("SELECT 1")
    assert len(store._all_conns) == 0


@pytest.mark.regression
def test_issue_1245_posture_store_no_resourcewarning_after_cross_thread_use(tmp_path):
    """No `unclosed database` ResourceWarning after cross-thread use + close().

    The issue's acceptance criterion: cross-thread (`asyncio.to_thread`-style)
    usage followed by close(), under `-W error::ResourceWarning` + gc.collect(),
    produces no warning.
    """
    store = SQLitePostureStore(str(tmp_path / "posture2.db"))

    def worker() -> None:
        store.get_posture("agent-1")

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    store.close()
    del store

    with warnings.catch_warnings():
        warnings.simplefilter("error", ResourceWarning)
        # If any connection leaked unclosed, its finalizer raises here.
        gc.collect()


@pytest.mark.regression
def test_issue_1245_trust_plane_store_close_releases_cross_thread_connection(tmp_path):
    """SqliteTrustPlaneStore.close() releases connections opened on other threads.

    The third trust SQLite store with the same per-thread-connection pattern
    (surfaced during the #1245 review); fixed the same way.
    """
    store = SqliteTrustPlaneStore(str(tmp_path / "plane.db"))
    captured: dict[str, sqlite3.Connection] = {}

    def worker() -> None:
        captured["conn"] = store._get_connection()

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    worker_conn = captured["conn"]
    assert worker_conn is not None
    assert worker_conn in store._all_conns

    store.close()  # from the MAIN thread

    with pytest.raises(sqlite3.ProgrammingError):
        worker_conn.execute("SELECT 1")
    assert len(store._all_conns) == 0


@pytest.mark.regression
def test_issue_1245_trust_store_close_releases_cross_thread_connection(tmp_path):
    """SqliteTrustStore._sync_close (wrapped by async close) releases all threads' conns."""
    store = SqliteTrustStore(str(tmp_path / "trust.db"))
    captured: dict[str, sqlite3.Connection] = {}

    def worker() -> None:
        # _get_connection is the shared per-thread mechanism the async ops use
        # via asyncio.to_thread; open + register a connection on this thread.
        captured["conn"] = store._get_connection()

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    worker_conn = captured["conn"]
    assert worker_conn is not None
    assert worker_conn in store._all_conns

    store._sync_close()  # what the public async close() wraps

    with pytest.raises(sqlite3.ProgrammingError):
        worker_conn.execute("SELECT 1")
    assert len(store._all_conns) == 0


@pytest.mark.regression
def test_issue_1245_close_releases_many_thread_connections(tmp_path):
    """close() releases connections opened across MANY worker threads, not just one."""
    store = SQLitePostureStore(str(tmp_path / "posture3.db"))
    conns: list[sqlite3.Connection] = []
    lock = threading.Lock()

    def worker() -> None:
        store.get_posture("agent-x")
        with lock:
            conns.append(store._local.conn)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len({id(c) for c in conns}) == 4  # 4 distinct per-thread connections
    store.close()
    for conn in conns:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")
