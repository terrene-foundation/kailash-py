# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""#2107 in `src/dataflow` — the last sibling the landed sweeps could not reach.

Issue #2107 removed cleanup calls from every ``__del__`` under ``src/kailash``,
and a follow-up did the same for ``src/kaizen``. Both guards walk their own
package only, so the same defect in this package was invisible to both. Two
finalizers here still carried it, measured on this tree before the fix with the
landed guard's own banned-call set:

    adapters/sqlite.py:1174               rollback() + swallowing handler
    cache/async_redis_adapter.py:439      shutdown() + swallowing handler

Neither is reported by the issue's *stated* predicate, which looks for a call
named ``close`` specifically — which is precisely why they outlived two sweeps.

Why cleanup in a finalizer is the defect, in one line: ``__del__`` fires at an
arbitrary bytecode boundary on whichever thread drops the last reference, so it
can re-enter a non-reentrant lock held by the thread it interrupted — and a
deadlock is not an exception, so the enclosing swallow-and-continue guard never
ran and bought no safety, while hiding real release failures
(``zero-tolerance.md`` Rule 3).

What is EVIDENCE here, and what is only a guard
-----------------------------------------------
The two sites have *different* hazards, so they get different evidence:

* ``AsyncRedisCacheAdapter`` carries the textbook #2107 deadlock.
  ``ThreadPoolExecutor.shutdown()`` opens with ``with self._shutdown_lock:``,
  and that attribute is a plain ``_thread.lock`` — NOT reentrant (verified on
  this interpreter by ``test_the_executor_shutdown_lock_is_really_non_reentrant``
  below, so this file does not merely assert the claim it depends on).
  ``ThreadPoolExecutor.submit()`` holds that same lock across its body, so a GC
  pass that drops the adapter's last reference inside ``submit`` runs the
  finalizer on a thread already holding it. Pre-fix that deadlocks 100% of the
  time, which is real evidence rather than a best-effort guard.

* ``SQLiteTransaction`` has no Python-level lock in its path, so claiming a
  deadlock for it would be false. Its hazard is that it runs **blocking database
  I/O from a GC callback**: the adapter opens its connections with
  ``check_same_thread=False``, so ``_conn.rollback()`` really does execute on
  whatever thread finalized the object, where it can block on ``SQLITE_BUSY``
  for the full busy-timeout. That is pinned deterministically by making the
  rollback block and asserting the finalizer returns anyway.

A test that only asserts "a ResourceWarning was emitted" would NOT discriminate
either fix: the pre-fix ``SQLiteTransaction`` already warned, and the pre-fix
``AsyncRedisCacheAdapter`` already warned too. The discriminating assertions are
the hang tests and the "cleanup call was never invoked" recorders.
"""

from __future__ import annotations

import ast
import logging
import pathlib
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor

import pytest

pytestmark = pytest.mark.regression

# Pinned RELATIVE to this checkout: a hard-coded worktree path would silently
# audit a different tree. tests/regression/<file> -> package root -> src/dataflow
SRC = pathlib.Path(__file__).resolve().parents[2] / "src" / "dataflow"

# Taken verbatim from the landed guard for `src/kailash`
# (`tests/regression/test_issue_2107_del_finalizers_no_close.py`) rather than
# re-derived. The issue's own predicate names only `close`; both sites in this
# package use a different verb, which is how they survived two sweeps.
BANNED_CALLS = frozenset(
    {
        "close",
        "aclose",
        "stop",
        "shutdown",
        "disconnect",
        "release",
        "terminate",
        "rollback",
        "cancel",
    }
)

TIMEOUT = 5.0


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def _run_with_timeout(body, name):
    """Run ``body`` in a daemon thread; return True if it finished in time.

    Daemon so that a genuine deadlock is reported as a failing assertion rather
    than wedging the whole suite at interpreter exit.
    """
    finished = threading.Event()

    def _target():
        body()
        finished.set()

    t = threading.Thread(target=_target, daemon=True, name=f"issue2107-df-{name}")
    t.start()
    t.join(TIMEOUT)
    return finished.is_set()


class _RecordingHandler(logging.Handler):
    """Captures every record emitted while installed."""

    def __init__(self):
        super().__init__(level=0)
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _make_adapter():
    """An AsyncRedisCacheAdapter with no live Redis behind it.

    ``__init__`` only stores the manager and builds a ThreadPoolExecutor, so a
    stand-in manager is enough to exercise the finalizer.
    """
    from dataflow.cache.async_redis_adapter import AsyncRedisCacheAdapter

    return AsyncRedisCacheAdapter(redis_manager=object(), max_workers=1)


def _make_transaction(rollback_hook=None):
    """A SQLiteTransaction holding a stand-in connection that records rollbacks."""
    from dataflow.adapters.sqlite import SQLiteTransaction

    calls = []

    class _RawConn:
        def rollback(self):
            calls.append("rollback")
            if rollback_hook is not None:
                rollback_hook()

    class _AioConn:
        def __init__(self):
            self._conn = _RawConn()

    tx = SQLiteTransaction(adapter=object())
    tx.connection = _AioConn()
    tx._committed = False
    tx._rolled_back = False
    return tx, calls


# ----------------------------------------------------------------------------
# The premise this file leans on, checked rather than asserted
# ----------------------------------------------------------------------------
def test_the_executor_shutdown_lock_is_really_non_reentrant():
    """The deadlock evidence below is only valid if this lock is non-reentrant.

    ``instrument-discipline.md`` MUST-1: name the falsifying result. If CPython
    ever made ``_shutdown_lock`` an ``RLock``, the hang test would go green for
    a reason that has nothing to do with #2107, and would silently stop being
    evidence. This fails loudly in that case instead.
    """
    ex = ThreadPoolExecutor(max_workers=1)
    try:
        lock = ex._shutdown_lock
        assert lock.acquire(blocking=False) is True
        try:
            assert lock.acquire(blocking=False) is False, (
                "ThreadPoolExecutor._shutdown_lock is reentrant on this "
                "interpreter -- the deadlock tests in this file no longer "
                "discriminate the #2107 fix and must be re-derived."
            )
        finally:
            lock.release()
    finally:
        ex.shutdown(wait=False)


# ----------------------------------------------------------------------------
# 1. Deterministic deadlock — the strongest evidence in this file
# ----------------------------------------------------------------------------
class TestFinalizerDoesNotReacquireTheExecutorLock:
    def test_async_redis_adapter_del_does_not_deadlock_on_shutdown_lock(self):
        adapter = _make_adapter()
        executor = adapter._executor
        finalizer = type(adapter).__del__

        def _body():
            # Exactly the state ThreadPoolExecutor.submit() is in across its
            # whole body. A GC pass here runs __del__ on THIS thread.
            with executor._shutdown_lock:
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore", ResourceWarning)
                    finalizer(adapter)

        finished = _run_with_timeout(_body, "redis-shutdown-lock")
        assert finished, (
            f"AsyncRedisCacheAdapter.__del__ did not return within {TIMEOUT}s "
            "while its executor's _shutdown_lock was held BY THE SAME THREAD "
            "-- it is deadlocked on a non-reentrant threading.Lock "
            "(issue #2107). ThreadPoolExecutor.submit() holds that lock across "
            "its body, so this is the state a GC pass during submit() leaves."
        )


# ----------------------------------------------------------------------------
# 2. Deterministic stall — the SQLiteTransaction analogue
# ----------------------------------------------------------------------------
class TestFinalizerDoesNotRunBlockingDatabaseIO:
    def test_sqlite_transaction_del_does_not_block_on_a_busy_rollback(self):
        """A rollback that blocks must not be able to stall the finalizer.

        Stands in for SQLITE_BUSY, which makes a real ``rollback()`` wait for
        the full busy-timeout on whichever thread GC happened to run on.
        """
        wedge = threading.Event()  # never set: the "database is locked" case

        tx, calls = _make_transaction(rollback_hook=wedge.wait)
        finalizer = type(tx).__del__

        def _body():
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                finalizer(tx)

        finished = _run_with_timeout(_body, "sqlite-busy-rollback")
        assert finished, (
            f"SQLiteTransaction.__del__ did not return within {TIMEOUT}s while "
            "its connection's rollback() was blocked -- the finalizer is "
            "running blocking database I/O from a GC callback (issue #2107). "
            "It must emit ResourceWarning and RETURN."
        )
        assert calls == [], (
            "SQLiteTransaction.__del__ invoked rollback() on the underlying "
            f"sqlite3 connection: {calls}. The finalizer must perform no "
            "cleanup -- sqlite3 rolls back an abandoned transaction from its "
            "own C-level deallocator (issue #2107)."
        )


# ----------------------------------------------------------------------------
# 3. No cleanup call is invoked at all
# ----------------------------------------------------------------------------
class TestFinalizerPerformsNoCleanup:
    def test_async_redis_adapter_del_does_not_shut_down_the_executor(self):
        adapter = _make_adapter()
        executor = adapter._executor
        calls = []
        object.__setattr__(executor, "shutdown", lambda *a, **k: calls.append((a, k)))
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                type(adapter).__del__(adapter)
            assert calls == [], (
                f"AsyncRedisCacheAdapter.__del__ called executor.shutdown{calls}. "
                "A finalizer must warn and RETURN -- ThreadPoolExecutor's own "
                "atexit hook drains worker threads at interpreter exit, so "
                "dropping this call leaks nothing (issue #2107)."
            )
        finally:
            ThreadPoolExecutor.shutdown(executor, wait=False)

    def test_sqlite_transaction_del_does_not_roll_back(self):
        tx, calls = _make_transaction()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            type(tx).__del__(tx)
        assert calls == [], (
            f"SQLiteTransaction.__del__ invoked rollback(): {calls} " "(issue #2107)."
        )


# ----------------------------------------------------------------------------
# 4. The finalizer emits no log record (the logging-lock re-entry path)
# ----------------------------------------------------------------------------
class TestFinalizerEmitsNoLogRecord:
    @pytest.mark.parametrize("which", ["adapter", "transaction"])
    def test_no_log_record_is_emitted_during_the_finalizer(self, which):
        """logging takes the root handler lock -- the other #2107 deadlock.

        A finalizer can fire from inside logging while that thread already
        holds that lock, so the finalizer must emit no record at all.
        """
        if which == "adapter":
            obj = _make_adapter()

            def cleanup() -> None:
                ThreadPoolExecutor.shutdown(obj._executor, wait=False)

        else:
            obj, _ = _make_transaction()

            def cleanup() -> None:
                return None

        finalizer = type(obj).__del__
        handler = _RecordingHandler()
        root = logging.getLogger()
        prev_level = root.level
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                finalizer(obj)
        finally:
            root.removeHandler(handler)
            root.setLevel(prev_level)
            cleanup()

        assert handler.records == [], (
            f"{type(obj).__name__}.__del__ emitted "
            f"{[r.getMessage() for r in handler.records]}. logging acquires a "
            "non-reentrant handler lock that the finalizing thread may already "
            "hold, so a finalizer must emit no log record (issue #2107)."
        )


# ----------------------------------------------------------------------------
# 5. The ResourceWarning contract is preserved (a guard, NOT evidence)
# ----------------------------------------------------------------------------
class TestResourceWarningContract:
    """Both sites warned before the fix too, so these do not discriminate it.

    They exist so that a future "simplify the finalizer" change cannot silently
    drop the leak signal along with the cleanup call.
    """

    def test_unclosed_adapter_warns_and_names_the_class(self):
        adapter = _make_adapter()
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                type(adapter).__del__(adapter)
            messages = [str(w.message) for w in caught if w.category is ResourceWarning]
            assert messages, "an unclosed adapter must emit a ResourceWarning"
            assert "AsyncRedisCacheAdapter" in messages[0]
        finally:
            ThreadPoolExecutor.shutdown(adapter._executor, wait=False)

    def test_closed_adapter_does_not_warn(self):
        adapter = _make_adapter()
        ThreadPoolExecutor.shutdown(adapter._executor, wait=False)
        adapter._closed = True
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            type(adapter).__del__(adapter)
        assert [
            w for w in caught if w.category is ResourceWarning
        ] == [], "a properly closed adapter must not warn"

    def test_uncompleted_transaction_warns(self):
        tx, _ = _make_transaction()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            type(tx).__del__(tx)
        messages = [str(w.message) for w in caught if w.category is ResourceWarning]
        assert messages, "an uncompleted transaction must emit a ResourceWarning"
        assert "SQLiteTransaction" in messages[0]

    def test_committed_transaction_does_not_warn(self):
        tx, _ = _make_transaction()
        tx._committed = True
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            type(tx).__del__(tx)
        assert [
            w for w in caught if w.category is ResourceWarning
        ] == [], "a committed transaction must not warn"


# ----------------------------------------------------------------------------
# 6. The durable shape pin over the whole package
# ----------------------------------------------------------------------------
def _finalizers():
    """Every ``__del__`` under src/dataflow, as (relative path, FunctionDef)."""
    for path in sorted(SRC.rglob("*.py")):
        rel = path.relative_to(SRC)
        if "__pycache__" in rel.parts:
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "__del__":
                    yield rel, node


class TestNoFinalizerUnderDataflowCleansUpOrSwallows:
    def test_the_walker_actually_finds_finalizers(self):
        """A zero-hit sweep from a broken walker is indistinguishable from a pass.

        ``instrument-discipline.md`` MUST-3: show the instrument fires HERE
        before reading its silence as a true negative. This was not hypothetical
        while authoring this file -- an exclusion list that tested the ABSOLUTE
        path for a component named "build" matched this checkout's own parent
        directory and silently scanned 0 of 2102 files, reporting a clean tree.
        """
        assert SRC.is_dir(), f"src/dataflow not found at {SRC}"
        found = list(_finalizers())
        assert len(found) >= 3, (
            f"the finalizer walker found only {len(found)} __del__ definitions "
            f"under {SRC} -- it is broken, and its silence proves nothing."
        )

    def test_no_finalizer_performs_cleanup(self):
        offenders = []
        for rel, node in _finalizers():
            for sub in ast.walk(node):
                if isinstance(sub, ast.Call):
                    fn = sub.func
                    name = (
                        fn.attr
                        if isinstance(fn, ast.Attribute)
                        else fn.id if isinstance(fn, ast.Name) else None
                    )
                    if name in BANNED_CALLS:
                        offenders.append(f"{rel}:{sub.lineno} -> {name}()")
        assert offenders == [], (
            "__del__ must emit ResourceWarning and RETURN, never perform "
            "cleanup -- it can re-enter a non-reentrant lock held by the "
            f"thread it interrupted (issue #2107). Offending calls: {offenders}"
        )

    def test_no_finalizer_swallows_silently(self):
        offenders = []
        for rel, node in _finalizers():
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Try):
                    continue
                for handler in sub.handlers:
                    if len(handler.body) == 1 and isinstance(handler.body[0], ast.Pass):
                        offenders.append(f"{rel}:{handler.lineno}")
        assert offenders == [], (
            "a handler whose entire body is `pass` hides genuine release "
            "failures (zero-tolerance.md Rule 3) while buying no safety "
            "against the hazard it resembles -- a deadlock is not an "
            f"exception. Offending handlers: {offenders}"
        )
