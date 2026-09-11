# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression pins for issue #2107: ``__del__`` finalizers must not call ``close()``.

Eight finalizers under ``src/kailash`` called ``self.close()`` (or reached into a
resource and closed it) inside a ``try`` whose only handler body was ``pass``.
``rules/patterns.md`` § "Async Resource Cleanup" BLOCKS exactly this: a finalizer
MUST emit ``ResourceWarning`` and return.

Why the old guard was inert
---------------------------
**A deadlock is not an exception.** The handler could never fire for the hazard
that motivated it; all it did was swallow genuine release failures
(``zero-tolerance.md`` Rule 3). And the usual Rule 3 remedy — logging in the
handler — would have made things strictly worse, because ``logging`` takes the
very lock whose re-entry is one of the two deadlocks. The fix is therefore to
DELETE the cleanup call: no call, no exception, no handler.

Two distinct deadlocks were live
--------------------------------
1. **Logging-lock re-entry.** ``LocalRuntime.close()`` emits ``logger.debug``
   and then ``_cleanup_event_loop()`` logs again. A finalizer can fire from
   inside ``logging`` during GC while that thread holds the root logging lock.
2. **``threading.Lock`` re-entry.** ``SQLiteStorage.close()``,
   ``PersistentDLQ.close()`` and ``SqliteEventStoreBackend.__del__`` each took
   ``self._lock``, and ``LocalRuntime.close()`` takes ``self._loop_lock``. A
   finalizer fires at an arbitrary bytecode boundary on whichever thread drops
   the last reference — including a thread already inside one of those locked
   sections. ``threading.Lock`` is not reentrant, so that thread blocks on
   itself, forever.

Deadlock (2) is what makes most of this file real evidence rather than a guard.
Unlike the logging race (which cannot be forced on demand), same-thread lock
re-entry is fully deterministic: hold the lock, run the finalizer body on that
same thread, and the pre-fix code hangs 100% of the time. That is what
``TestFinalizerDoesNotReacquireItsOwnLock`` does, inside a daemon worker so a
hang is reported as a test failure instead of wedging the suite.

Which tests here are EVIDENCE, and which are guards
---------------------------------------------------
MEASURED, not assumed: the fix was reverted (``git diff -- src/ > p; git apply
-R p``) with this file left in place, and the suite re-run. Result: **14 failed,
3 passed**. Those 14 are the discriminating set; the 3 that passed both ways are
labelled as guards below and MUST NOT be cited as proof.

DISCRIMINATING (red pre-fix, green post-fix) -- these carry the proof:

* ``TestFinalizerDoesNotReacquireItsOwnLock`` (all four cases) -- deterministic
  same-thread lock re-entry. Pre-fix each hung the full 5s timeout, e.g.
  "SQLiteStorage.__del__ did not return within 5.0s while its own _lock was
  held BY THE SAME THREAD". This is the strongest evidence in the file: unlike
  the logging race, it reproduces 100% of the time.
* ``TestFinalizerPerformsNoCleanup`` (all four cases) -- ``close`` patched to
  record invocations; pre-fix each recorded a call.
* ``TestResourceWarningContract`` unclosed-poles (3 cases) -- pre-fix
  ``SQLiteStorage``/``PersistentDLQ``/``SqliteEventStoreBackend`` emitted NO
  ResourceWarning at all (they closed silently instead), so "got []".
* ``TestRedisNodeHasADeterministicClosePath`` (both cases) -- pre-fix
  ``RedisNode`` had no ``close()`` at all ("AttributeError: 'RedisNode' object
  has no attribute 'close'"), and its finalizer DID close the client.
* ``test_no_del_under_src_kailash_calls_cleanup_or_swallows`` -- the class
  guard; pre-fix it named all eight offending sites by file and line.

NON-DISCRIMINATING (green BOTH ways) -- guards against over-correction, NOT
evidence the bug is fixed:

* ``test_async_local_runtime_warns_exactly_once`` -- it was EXPECTED to
  discriminate and MEASURED not to, so it is filed here honestly. Pre-fix the
  forced ``close()`` drove ``_ref_count`` to 0, so the chained
  ``super().__del__()`` found nothing to warn about and exactly one warning was
  emitted -- the same count as post-fix, for an entirely different reason. It
  is retained because it pins the invariant going FORWARD: now that both
  finalizers are warn-only with the same predicate, re-adding the
  ``super().__del__()`` chain would make it 2 and red this test.
* ``test_closed_sqlite_storage_does_not_warn`` -- the silent-on-clean-close
  pole. Pins behaviour the fix deliberately preserved.
* ``test_dropping_an_unclosed_store_still_releases_the_sqlite_handle`` -- pins
  that warn-and-return does not leak the OS handle (sqlite3's own C-level
  deallocator closes it). Passes pre-fix too, because pre-fix ALSO closed it,
  just dangerously. Kept because the obvious wrong "fix" for a leak worry is a
  global registry, which this would catch.

No discriminating test was constructible for ``AsyncSQLDatabaseNode.__del__``
------------------------------------------------------------------------------
Stated explicitly rather than papered over with a test that cannot fail. That
finalizer's removed block reached through ``self._adapter._connection._conn``
for a raw sqlite3 handle. Reproducing its hazard needs a live connected async
adapter mid-statement on another thread, which is a timing race, not a
deterministic lock re-entry -- any test would be asserting on scheduling luck.
The site IS covered by ``test_no_del_under_src_kailash_calls_cleanup_or_swallows``
(shape-level: it was one of the eight the guard named pre-fix), but nothing here
exercises its runtime behaviour, and that gap is real.

Sibling of ``tests/regression/test_cli_channel_and_mcp_server_del_no_close.py``
(issue #2105), which closed the two channel-shutdown sites of this same class.
"""

from __future__ import annotations

import ast
import gc
import os
import sqlite3
import threading
import warnings
from pathlib import Path

import pytest

from kailash.middleware.gateway.event_store_sqlite import SqliteEventStoreBackend
from kailash.nodes.data.redis import RedisNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.tracking.storage.database import SQLiteStorage
from kailash.workflow.dlq import PersistentDLQ

pytestmark = pytest.mark.regression

# How long to wait for a finalizer that must not block. Generous: a correct
# finalizer returns in microseconds, so a timeout here means it truly blocked.
_FINALIZER_TIMEOUT_S = 5.0


def _run_finalizer_while_holding(make_obj, lock_attr: str):
    """Run ``type(obj).__del__(obj)`` on a thread that ALREADY holds ``lock_attr``.

    This is the exact shape of the production hazard: GC drops the last
    reference at an arbitrary bytecode boundary, and the thread it happens on is
    sometimes one already inside a ``with self._lock:`` section of the very
    object being finalized. ``threading.Lock`` is not reentrant, so a finalizer
    that re-takes that lock blocks on itself permanently.

    The whole scenario runs in a DAEMON thread so that a pre-fix hang surfaces
    as an assertion failure here rather than wedging the test session. The
    wedged daemon is abandoned deliberately -- it owns only its own throwaway
    object, and the interpreter will not wait for it at exit.

    Returns:
        ``(completed, errors)`` -- whether the finalizer returned before the
        timeout, and any exception it raised.
    """
    completed = threading.Event()
    errors: list[BaseException] = []

    def _body() -> None:
        obj = make_obj()
        lock = getattr(obj, lock_attr)
        with lock:
            # Same thread, lock held, finalizer body now runs.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                try:
                    type(obj).__del__(obj)
                except BaseException as exc:  # noqa: BLE001 - reported, not hidden
                    errors.append(exc)
        completed.set()

    worker = threading.Thread(
        target=_body, daemon=True, name=f"issue2107-finalizer-{lock_attr}"
    )
    worker.start()
    return completed.wait(_FINALIZER_TIMEOUT_S), errors


class TestFinalizerDoesNotReacquireItsOwnLock:
    """Deterministic proof, one case per lock-taking finalizer.

    Pre-fix every case hangs on ``self._lock`` / ``self._loop_lock`` until the
    join timeout. Post-fix the finalizer warns and returns without touching the
    lock at all.
    """

    def _assert_no_deadlock(self, completed, errors, cls_name: str, lock_attr: str):
        assert not errors, (
            f"{cls_name}.__del__ raised {errors[0]!r} while {lock_attr} was "
            "held. The finalizer must warn and return, touching nothing."
        )
        assert completed, (
            f"{cls_name}.__del__ did not return within {_FINALIZER_TIMEOUT_S}s "
            f"while its own {lock_attr} was held BY THE SAME THREAD -- it is "
            "deadlocked on a non-reentrant threading.Lock. A finalizer fires "
            "at an arbitrary bytecode boundary on whichever thread drops the "
            "last reference, so this is reachable in production whenever GC "
            "runs inside one of this class's locked sections. The finalizer "
            "must emit ResourceWarning and return; real cleanup belongs to "
            "close(). See rules/patterns.md § 'Async Resource Cleanup' and "
            "issue #2107."
        )

    def test_sqlite_storage_finalizer_does_not_deadlock_on_its_lock(self, tmp_path):
        completed, errors = _run_finalizer_while_holding(
            lambda: SQLiteStorage(str(tmp_path / "tracking.db")), "_lock"
        )
        self._assert_no_deadlock(completed, errors, "SQLiteStorage", "_lock")

    def test_persistent_dlq_finalizer_does_not_deadlock_on_its_lock(self, tmp_path):
        completed, errors = _run_finalizer_while_holding(
            lambda: PersistentDLQ(db_path=str(tmp_path / "dlq.db")), "_lock"
        )
        self._assert_no_deadlock(completed, errors, "PersistentDLQ", "_lock")

    def test_sqlite_event_store_finalizer_does_not_deadlock_on_its_lock(self, tmp_path):
        completed, errors = _run_finalizer_while_holding(
            lambda: SqliteEventStoreBackend(str(tmp_path / "events.db")), "_lock"
        )
        self._assert_no_deadlock(completed, errors, "SqliteEventStoreBackend", "_lock")

    def test_local_runtime_finalizer_does_not_deadlock_on_its_loop_lock(self):
        completed, errors = _run_finalizer_while_holding(LocalRuntime, "_loop_lock")
        self._assert_no_deadlock(completed, errors, "LocalRuntime", "_loop_lock")


class TestFinalizerPerformsNoCleanup:
    """The finalizer must invoke no cleanup by any route.

    Patching ``close`` catches the direct call; the runtime ref-count assertions
    catch a hand-rolled ``release()`` that would reach the same logging path
    without going through ``close()``.
    """

    def _del_with_close_recorded(self, cls, obj):
        """Run ``obj``'s finalizer with ``cls.close`` recording invocations."""
        calls: list[str] = []
        real_close = cls.close

        def _recording_close(self, *args, **kwargs):
            calls.append("close")
            return real_close(self, *args, **kwargs)

        cls.close = _recording_close
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                type(obj).__del__(obj)
        finally:
            cls.close = real_close
        return calls

    def test_sqlite_storage_del_does_not_invoke_close(self, tmp_path):
        store = SQLiteStorage(str(tmp_path / "t.db"))
        try:
            calls = self._del_with_close_recorded(SQLiteStorage, store)
            assert calls == [], (
                f"SQLiteStorage.__del__ called close() {len(calls)} time(s). "
                "close() takes self._lock, which deadlocks when the finalizer "
                "fires on a thread already holding it (issue #2107)."
            )
        finally:
            store.close()

    def test_persistent_dlq_del_does_not_invoke_close(self, tmp_path):
        dlq = PersistentDLQ(db_path=str(tmp_path / "d.db"))
        try:
            calls = self._del_with_close_recorded(PersistentDLQ, dlq)
            assert calls == [], (
                f"PersistentDLQ.__del__ called close() {len(calls)} time(s). "
                "close() takes self._lock -- see issue #2107."
            )
        finally:
            dlq.close()

    def test_local_runtime_del_does_not_invoke_close(self):
        runtime = LocalRuntime()
        try:
            calls = self._del_with_close_recorded(LocalRuntime, runtime)
            assert calls == [], (
                f"LocalRuntime.__del__ called close() {len(calls)} time(s). "
                "close() emits logger.debug, takes self._loop_lock and drives "
                "_cleanup_event_loop() -- the documented deadlock path "
                "(issue #2107)."
            )
        finally:
            while runtime.ref_count > 0:
                runtime.release()

    def test_parallel_cyclic_runtime_del_does_not_release_the_runtime(self):
        """Ref-count pin: catches every cleanup route, not just close()."""
        shared = LocalRuntime()
        pcr = ParallelCyclicRuntime(runtime=shared)
        before = shared.ref_count
        assert before >= 2, "expected the shared runtime to be acquired"

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                type(pcr).__del__(pcr)

            assert shared.ref_count == before, (
                f"ref_count moved {before} -> {shared.ref_count}. "
                "ParallelCyclicRuntime.__del__ must not release the runtime: "
                "release() is LocalRuntime.close(), which logs and takes "
                "_loop_lock (issue #2107)."
            )
        finally:
            pcr.close()
            while shared.ref_count > 0:
                shared.release()


class TestResourceWarningContract:
    """Dropping the cleanup must not drop the leak signal. Two poles each."""

    def test_unclosed_sqlite_storage_warns_and_names_the_class(self, tmp_path):
        store = SQLiteStorage(str(tmp_path / "w.db"))
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                type(store).__del__(store)

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource, (
                "SQLiteStorage.__del__ must emit ResourceWarning -- it is the "
                "only remaining leak signal now that close() is gone."
            )
            assert any("SQLiteStorage" in str(w.message) for w in resource), (
                "The warning must name the class so the operator can find the "
                f"leak; got {[str(w.message) for w in resource]}"
            )
        finally:
            store.close()

    def test_closed_sqlite_storage_does_not_warn(self, tmp_path):
        """The other pole: the warning is a leak signal, not noise on every drop."""
        store = SQLiteStorage(str(tmp_path / "w2.db"))
        store.close()
        store.conn = None  # close() shuts the handle; drop the attr it checks

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            type(store).__del__(store)

        resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
        assert not resource, (
            "A properly closed SQLiteStorage must not warn on finalization; "
            f"got {[str(w.message) for w in resource]}"
        )

    def test_unclosed_dlq_warns_and_names_the_class(self, tmp_path):
        dlq = PersistentDLQ(db_path=str(tmp_path / "w3.db"))
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                type(dlq).__del__(dlq)

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource and any(
                "PersistentDLQ" in str(w.message) for w in resource
            ), (
                "PersistentDLQ.__del__ must emit a ResourceWarning naming the "
                f"class; got {[str(w.message) for w in caught]}"
            )
        finally:
            dlq.close()

    def test_unclosed_event_store_warns_and_names_the_class(self, tmp_path):
        store = SqliteEventStoreBackend(str(tmp_path / "w4.db"))
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                type(store).__del__(store)

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert resource and any(
                "SqliteEventStoreBackend" in str(w.message) for w in resource
            ), (
                "SqliteEventStoreBackend.__del__ must emit a ResourceWarning "
                f"naming the class; got {[str(w.message) for w in caught]}"
            )
        finally:
            store._conn.close()
            store._conn = None


class TestAsyncLocalRuntimeWarnsOnce:
    """The dropped ``super().__del__()`` chain. NON-DISCRIMINATING -- a forward
    guard, not evidence. See the module docstring.

    Pre-fix the subclass forced ``close()``, which drove ``_ref_count`` to 0, so
    the chained parent finalizer found nothing to warn about and the count was
    also exactly 1. MEASURED green both pre- and post-fix. With the cleanup
    removed that accident disappears: chaining two warn-only finalizers with the
    same ``_ref_count > 0`` predicate would double-warn for one leaked object,
    which is what this now pins going forward.
    """

    def test_async_local_runtime_warns_exactly_once(self):
        runtime = AsyncLocalRuntime()
        try:
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                type(runtime).__del__(runtime)

            resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
            assert len(resource) == 1, (
                f"Expected exactly one ResourceWarning for one leaked "
                f"AsyncLocalRuntime, got {len(resource)}: "
                f"{[str(w.message) for w in resource]}. Both this finalizer and "
                "LocalRuntime.__del__ are now warn-only with the same "
                "_ref_count > 0 predicate, so AsyncLocalRuntime.__del__ must "
                "NOT call super().__del__() (issue #2107)."
            )
            assert "AsyncLocalRuntime" in str(resource[0].message)
            assert "async with" in str(resource[0].message), (
                "The async runtime's warning must name 'async with' as the "
                f"remedy; got {resource[0].message}"
            )
        finally:
            while runtime.ref_count > 0:
                runtime.release()


class TestRedisNodeHasADeterministicClosePath:
    """A warning may only name a remedy that exists.

    ``RedisNode`` had NO ``close()`` -- its finalizer was the only place the
    client was ever released. Telling the operator to "call close()" without
    adding one would have been a false instruction, so ``close()`` ships with
    the fix.
    """

    def test_redis_node_close_releases_the_client(self):
        node = RedisNode(operation="get")

        class _FakeClient:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        fake = _FakeClient()
        node._client = fake

        node.close()

        assert fake.closed, "RedisNode.close() must close the underlying client"
        assert node._client is None, (
            "RedisNode.close() must drop its client reference so the finalizer "
            "does not then warn about an already-released node"
        )

        node.close()  # idempotent: must not raise

    def test_redis_node_del_does_not_close_the_client(self):
        node = RedisNode(operation="get")

        class _FakeClient:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        fake = _FakeClient()
        node._client = fake

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            type(node).__del__(node)

        assert not fake.closed, (
            "RedisNode.__del__ must not close the client: the redis-py pool "
            "takes its own lock and disconnects sockets, which is unsafe from "
            "an arbitrary GC thread (issue #2107)."
        )
        resource = [w for w in caught if issubclass(w.category, ResourceWarning)]
        assert resource and any("RedisNode" in str(w.message) for w in resource), (
            f"expected a ResourceWarning naming RedisNode; got "
            f"{[str(w.message) for w in caught]}"
        )


class TestWarnAndReturnDoesNotLeakTheHandle:
    """NON-DISCRIMINATING guard -- see the module docstring.

    Pins the reasoning that made warn-and-return safe: we are not choosing
    "leak vs deadlock". Once the Python object is unreachable, sqlite3's own
    C-level deallocator closes the database handle. This passes pre-fix too
    (pre-fix also closed it, just dangerously); it is kept because the tempting
    wrong answer to a leak worry -- parking live objects in a module-level
    registry -- would make it fail.
    """

    @staticmethod
    def _fds_open_on(path: str) -> int:
        """Count this process's file descriptors pointing at ``path``.

        Matches on (st_dev, st_ino) rather than on a name, so it is unaffected
        by symlinked temp dirs. ``sqlite3.Connection`` does not support weak
        references, and ``psutil.open_files()`` was MEASURED to report 0 even
        while a connection is open on this platform -- an instrument that
        cannot produce the positive result is not evidence of the negative one,
        so neither is used. Every caller below asserts the non-zero control
        first, which is what makes a subsequent 0 meaningful.
        """
        fddir = "/proc/self/fd" if os.path.isdir("/proc/self/fd") else "/dev/fd"
        st = os.stat(path)
        count = 0
        for entry in os.listdir(fddir):
            try:
                fd_stat = os.fstat(int(entry))
            except (OSError, ValueError):
                continue  # fd closed underneath us, or a non-numeric entry
            if fd_stat.st_ino == st.st_ino and fd_stat.st_dev == st.st_dev:
                count += 1
        return count

    @pytest.mark.skipif(
        not (os.path.isdir("/proc/self/fd") or os.path.isdir("/dev/fd")),
        reason="no fd directory to enumerate on this platform",
    )
    def test_dropping_an_unclosed_store_still_releases_the_sqlite_handle(
        self, tmp_path
    ):
        db_path = str(tmp_path / "leak.db")
        store = SQLiteStorage(db_path)

        # POSITIVE CONTROL: the counter must be able to SEE the descriptor.
        # Without this, the zero asserted below would be indistinguishable from
        # a broken instrument (instrument-discipline MUST-3).
        open_while_live = self._fds_open_on(db_path)
        assert open_while_live >= 1, (
            f"fd counter saw {open_while_live} descriptors on {db_path} while "
            "the connection is demonstrably open -- the instrument is broken, "
            "so its result below would carry no information."
        )

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            del store
            gc.collect()

        remaining = self._fds_open_on(db_path)
        assert remaining == 0, (
            f"{remaining} descriptor(s) still open on {db_path} after the "
            "owning SQLiteStorage was collected. warn-and-return relies on the "
            "sqlite3.Connection becoming unreachable so its C-level "
            "deallocator closes the handle -- if something holds a strong "
            "reference, this IS a real fd leak and the finalizer change would "
            "have traded a deadlock for exhaustion."
        )


class TestNoFinalizerInTheTreeReintroducesTheClass:
    """The root-cause guard: the bug class cannot come back silently.

    Fixing eight call sites fixes eight call sites. This walks every ``__del__``
    under ``src/kailash`` and fails on the SHAPE, so a ninth site added later --
    including via a cleanup route the issue's own ``close()``-only sweep would
    have missed, such as ``release()`` or ``shutdown()`` -- fails here.
    """

    # Names whose invocation from __del__ is the defect. Deliberately broader
    # than the issue's `close`-only predicate, which would have passed a
    # finalizer calling release()/shutdown()/disconnect() on the same paths.
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

    @staticmethod
    def _src_root() -> Path:
        root = Path(__file__).resolve().parents[2] / "src" / "kailash"
        assert root.is_dir(), f"expected {root} to exist"
        return root

    @staticmethod
    def _is_string_join(node: ast.Call) -> bool:
        """``"".join(...)`` is a string op, not resource cleanup."""
        func = node.func
        return (
            isinstance(func, ast.Attribute)
            and func.attr == "join"
            and isinstance(func.value, ast.Constant)
            and isinstance(func.value.value, str)
        )

    def test_no_del_under_src_kailash_calls_cleanup_or_swallows(self):
        root = self._src_root()
        py_files = sorted(root.rglob("*.py"))
        assert len(py_files) > 100, (
            f"only found {len(py_files)} python files under {root} -- the "
            "walker is broken, so an empty finding would be a false negative"
        )

        cleanup_offenders: list[str] = []
        swallow_offenders: list[str] = []
        finalizers_seen = 0

        for path in py_files:
            if "__pycache__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if (
                    not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    or node.name != "__del__"
                ):
                    continue
                finalizers_seen += 1
                rel = path.relative_to(root.parent.parent)

                for inner in ast.walk(node):
                    if (
                        isinstance(inner, ast.Call)
                        and isinstance(inner.func, ast.Attribute)
                        and inner.func.attr in self.BANNED_CALLS
                        and not self._is_string_join(inner)
                    ):
                        cleanup_offenders.append(
                            f"{rel}:{inner.lineno} calls .{inner.func.attr}()"
                        )
                    if isinstance(inner, ast.ExceptHandler):
                        body = inner.body
                        if len(body) == 1 and isinstance(body[0], ast.Pass):
                            kind = ast.unparse(inner.type) if inner.type else "<bare>"
                            swallow_offenders.append(
                                f"{rel}:{inner.lineno} except {kind}: pass"
                            )

        # Guard the guard: if this ever sees no finalizers, its green means
        # nothing. src/kailash has had 12 for the life of this issue.
        assert finalizers_seen >= 10, (
            f"walked only {finalizers_seen} __del__ definitions under {root}; "
            "expected >= 10. The sweep is not finding the finalizers, so a "
            "clean result here would be a false negative."
        )

        assert not cleanup_offenders, (
            "__del__ must perform NO cleanup -- it fires at an arbitrary "
            "bytecode boundary on an arbitrary thread and can re-enter a "
            "non-reentrant logging or threading lock, deadlocking the process. "
            "Emit ResourceWarning (kailash.utils.finalizer.warn_unclosed) and "
            "return; real cleanup belongs to close()/cleanup(). Offending "
            "sites:\n  " + "\n  ".join(cleanup_offenders)
        )
        assert not swallow_offenders, (
            "__del__ must not swallow exceptions silently "
            "(zero-tolerance.md Rule 3). It also does not need to: CPython "
            "already prints anything escaping a finalizer as 'Exception "
            "ignored in:' and continues, so NOT catching is both safe and "
            "loud. Offending sites:\n  " + "\n  ".join(swallow_offenders)
        )
