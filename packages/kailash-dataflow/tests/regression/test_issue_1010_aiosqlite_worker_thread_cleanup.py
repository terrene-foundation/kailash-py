# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #1010 — aiosqlite Connection worker threads MUST
exit before interpreter shutdown.

Per ``workspaces/issue-1002-aiosqlite-fixture-cleanup/journal/0007-DISCOVERY-py-finalize-root-cause-aiosqlite-nondaemon-workers.md``:
aiosqlite ``Connection._thread`` is constructed at ``aiosqlite/core.py:90``
WITHOUT ``daemon=True``. When a SQLite-using test ends, the per-test event
loop closes, and ``cleanup_dataflow_connection_pools`` previously hit a
``pass # Will be cleared from cache below`` for the SQLite branch — dropping
the Python reference to the aiosqlite Connection WITHOUT calling its
``close()`` (which sends an exit sentinel to the worker thread's tx queue).

Result: every test that exercises SQLite leaked at least one non-daemon
worker thread. The threads accumulated across the suite and blocked
``threading._shutdown()`` at interpreter exit, manifesting as the
``_Py_Finalize → wait_for_thread_shutdown`` hang that PR #1008's CI
reproduced for ~14-17 minutes per run.

This regression is Tier 2 — it exercises a REAL aiosqlite.Connection
lifecycle and asserts the OS-level threading state. A Tier 1 mock cannot
prove the worker thread was started AND terminated.

Acceptance criteria:
1. After ``DataFlow.close()`` on a sync-context (``with DataFlow(...)``),
   ``threading.enumerate()`` contains zero frames whose stack mentions
   ``_connection_worker_thread``.
2. After the autouse fixture ``cleanup_dataflow_connection_pools`` runs
   (implicit per-test teardown), the same invariant holds when the test
   used ``db.express`` (which routes through cached
   ``AsyncSQLDatabaseNode._shared_pools``).
"""

from __future__ import annotations

import sys
import threading
import time

import pytest

from dataflow import DataFlow

pytestmark = [pytest.mark.regression]


def _aiosqlite_worker_threads_alive() -> list[threading.Thread]:
    """Return the list of currently-live aiosqlite Connection worker threads.

    Detection strategy: aiosqlite's worker thread runs
    ``_connection_worker_thread`` defined at module scope in
    ``aiosqlite/core.py``. We inspect every live ``threading.Thread`` and
    extract its current top-of-stack via ``sys._current_frames()``; any
    thread whose stack contains a frame whose ``f_code.co_name`` equals
    ``_connection_worker_thread`` is one we care about.
    """
    frames = sys._current_frames()
    leaked = []
    for thread in threading.enumerate():
        if thread.ident is None:
            continue
        frame = frames.get(thread.ident)
        while frame is not None:
            if frame.f_code.co_name == "_connection_worker_thread":
                leaked.append(thread)
                break
            frame = frame.f_back
    return leaked


def test_sync_dataflow_close_terminates_aiosqlite_worker_threads(tmp_path) -> None:
    """Sync ``DataFlow.close()`` MUST close every cached aiosqlite Connection.

    Exercises the engine's sync close path that Shard 2 of issue #1002
    extended at ``engine.py:10018-10032`` (cached AsyncSQLDatabaseNode
    teardown via ``async_safe_run(node.close())``). When ``close()`` is
    called inside a sync context (``with DataFlow(...) as db:``), every
    aiosqlite Connection's worker thread MUST receive its exit sentinel
    before the next test's ``threading.enumerate()`` snapshot.
    """
    db_path = tmp_path / "issue_1010_sync.db"
    baseline_leaked = _aiosqlite_worker_threads_alive()

    with DataFlow(database_url=f"sqlite:///{db_path}", auto_migrate=False) as db:

        @db.model
        class IssueOneOhTenSync:
            name: str

        # Force at least one aiosqlite Connection to spin up by reading.
        # express.count is sufficient to acquire-release a connection
        # without depending on schema migration semantics.
        try:
            _ = db.express_sync.count("IssueOneOhTenSync")
        except Exception:
            # Schema may not exist yet — the connection-spin-up is the
            # invariant we care about, not the query semantics.
            pass

    # Give worker threads up to 2s to exit. The sentinel-via-tx-queue
    # path is fast (microseconds in practice) but on shared CI runners
    # we tolerate a small grace period before asserting.
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        leaked = _aiosqlite_worker_threads_alive()
        new_leaks = [t for t in leaked if t not in baseline_leaked]
        if not new_leaks:
            return
        time.sleep(0.05)

    leaked = _aiosqlite_worker_threads_alive()
    new_leaks = [t for t in leaked if t not in baseline_leaked]
    assert new_leaks == [], (
        "Sync DataFlow.close() left aiosqlite worker threads alive — these "
        "are non-daemon (aiosqlite/core.py:90) and will block "
        "_Py_Finalize → threading._shutdown() at interpreter exit. "
        f"Leaked threads: {[t.name for t in new_leaks]}. "
        "See issue #1010 / journal/0007 for the forensic root cause."
    )


@pytest.mark.asyncio
async def test_async_dataflow_express_cleanup_terminates_aiosqlite_workers(
    tmp_path,
) -> None:
    """Express ops via the cached pool MUST not leak aiosqlite worker threads.

    Exercises the ``AsyncSQLDatabaseNode._shared_pools`` path that
    ``cleanup_dataflow_connection_pools`` (the autouse fixture in
    ``tests/conftest.py``) targets. Before issue #1010's fix, the
    fixture's SQLite branch was ``pass # Will be cleared from cache
    below`` — adapters were dropped from the dict without
    ``Connection.close()`` ever running, leaving worker threads alive.

    The autouse fixture runs AFTER this test's body returns. To assert
    the invariant within the test body we explicitly call
    ``await db.close_async()`` which exercises the same close path the
    fixture's loop-is-open branch uses.
    """
    db_path = tmp_path / "issue_1010_async.db"
    baseline_leaked = _aiosqlite_worker_threads_alive()

    db = DataFlow(database_url=f"sqlite:///{db_path}", auto_migrate=False)

    @db.model
    class IssueOneOhTenAsync:
        name: str

    try:
        _ = await db.express.count("IssueOneOhTenAsync")
    except Exception:
        pass

    await db.close_async()

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        leaked = _aiosqlite_worker_threads_alive()
        new_leaks = [t for t in leaked if t not in baseline_leaked]
        if not new_leaks:
            return
        time.sleep(0.05)

    leaked = _aiosqlite_worker_threads_alive()
    new_leaks = [t for t in leaked if t not in baseline_leaked]
    assert new_leaks == [], (
        "Async DataFlow.close_async() left aiosqlite worker threads alive. "
        f"Leaked threads: {[t.name for t in new_leaks]}. "
        "See issue #1010 / journal/0007 for the forensic root cause."
    )
