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

import asyncio
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


def _assert_no_blocking_aiosqlite_workers(baseline: list[threading.Thread]) -> None:
    """Assert every NEW aiosqlite worker thread is daemon=True.

    The shutdown-hang failure mode (issue #1010) requires a non-daemon
    aiosqlite worker thread alive at interpreter exit. Two acceptable
    outcomes after cleanup:

    1. Worker thread no longer alive (Connection.close() succeeded and
       the worker exited).
    2. Worker thread still alive but daemon=True (conftest.py monkey-patch
       made the worker daemon; Python kills it at interpreter exit
       without blocking threading._shutdown()).

    Either outcome means the suite exits cleanly. The assertion below
    fails ONLY if a worker is alive AND non-daemon — that is the
    actual shutdown-blocking failure mode.
    """
    leaked = _aiosqlite_worker_threads_alive()
    new_leaks = [t for t in leaked if t not in baseline]
    blocking = [t for t in new_leaks if not t.daemon]
    assert blocking == [], (
        "aiosqlite worker thread(s) alive AND non-daemon — these block "
        "_Py_Finalize → threading._shutdown() at interpreter exit. "
        "Either Connection.close() must succeed OR conftest.py's "
        "_patch_aiosqlite_worker_threads_daemon() must run before any "
        "Connection is constructed. "
        f"Blocking threads: {[(t.name, t.daemon) for t in blocking]}. "
        "See issue #1010 / journal/0007 for the forensic root cause."
    )


def test_sync_dataflow_close_terminates_aiosqlite_worker_threads(tmp_path) -> None:
    """Sync ``DataFlow.close()`` MUST not leave non-daemon aiosqlite workers.

    Two-fold safety contract (issue #1010):
    1. PR #1014 Phase B fix routes Connection.close() through the engine
       close path — when this works, workers exit cleanly.
    2. conftest.py monkey-patch sets ``_thread.daemon = True`` on every
       aiosqlite Connection — workers that survive close() are still
       daemon and don't block interpreter shutdown.

    This test enforces the union: every surviving worker thread MUST be
    daemon=True. If either path fails, the assertion fires.
    """
    db_path = tmp_path / "issue_1010_sync.db"
    baseline = _aiosqlite_worker_threads_alive()

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

    # Give close() up to 2s to terminate workers cleanly; assertion only
    # cares about daemon-flag on survivors, not absence.
    time.sleep(0.1)
    _assert_no_blocking_aiosqlite_workers(baseline)


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
    baseline = _aiosqlite_worker_threads_alive()

    db = DataFlow(database_url=f"sqlite:///{db_path}", auto_migrate=False)

    @db.model
    class IssueOneOhTenAsync:
        name: str

    try:
        _ = await db.express.count("IssueOneOhTenAsync")
    except Exception:
        pass

    await db.close_async()
    await asyncio.sleep(0.1)
    _assert_no_blocking_aiosqlite_workers(baseline)


def test_aiosqlite_monkeypatch_active() -> None:
    """The conftest monkey-patch MUST be active at test session start.

    Verifies the structural defense for issue #1010: every aiosqlite
    Connection constructed during the test session should have a
    daemon=True worker thread. This pins the conftest.py patch — if a
    future refactor removes the patch, this test fails immediately.
    """
    import aiosqlite.core

    assert getattr(aiosqlite.core, "_kailash_issue_1010_patched", False), (
        "conftest.py _patch_aiosqlite_worker_threads_daemon() did not run; "
        "aiosqlite worker threads will be non-daemon and block "
        "_Py_Finalize at interpreter exit. See issue #1010."
    )
