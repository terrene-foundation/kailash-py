# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test: ProtectedDataFlow.close() must drain the persistent
event loops of every ProtectedDataFlowRuntime it handed out (issue #1045).

``ProtectedDataFlowRuntime.__init__`` calls ``mark_externally_managed()``
(Shard A's deprecation fix). ``mark_externally_managed()``
(``kailash.runtime.local.LocalRuntime``) does two things:

1. sets ``_externally_managed = True`` (suppresses the CM DeprecationWarning
   — guarded by the sibling test
   ``test_issue_1045_protection_runtime_cm_deprecation.py``), AND
2. SKIPS ``atexit.register(self._cleanup_event_loop)`` in
   ``_get_persistent_loop`` (``local.py`` ~L1474-1482) — the opt-out
   deliberately transfers cleanup responsibility to the owning framework.

Before the fix, ``DataFlowProtectionMixin.create_protected_runtime()``
returned a FRESH, untracked runtime per call, and ``ProtectedDataFlow``
only inherited ``DataFlow.close()`` — which drains
``_sync_runtime_singleton`` / ``_loop_runtime_cache`` / ``_runtime_override``
but NEVER the protected runtimes. Net: each protected runtime's persistent
asyncio event loop was no longer atexit-cleaned AND nothing else closed it
→ a per-protected-runtime event-loop leak. That is the exact
``ResourceWarning`` class issue #1045 is chartered to close.

The fix tracks every runtime returned by ``create_protected_runtime()`` on
the owning ``DataFlowProtectionMixin`` and drains them (``runtime.close()``)
in cooperative-MRO ``close()`` / ``close_async()`` overrides — the same
owner-tracks-then-drains invariant every sibling
``mark_externally_managed()`` call site already honors (``engine.py:883`` ->
``self._sync_runtime_singleton`` drained in ``DataFlow.close()``;
``auto_migration_system.py`` -> ``self._explicit_runtime`` drained in
``close()``).

These tests exercise the REAL protection ``execute()`` path against a real
(SQLite) DataFlow instance, capture the persistent loop the runtime
allocated, and assert ``ProtectedDataFlow.close()`` / ``close_async()``
actually closed it (``loop.is_closed()`` + ``_persistent_loop is None``).
The behavioral loop-closed assertion is the structural proof; it holds
under ``-W error::ResourceWarning``.

Scope boundary: a separate, pre-existing ``aiosqlite.core.Connection ...
was deleted before being closed`` ResourceWarning is emitted by the
``ProtectedDataFlow`` + ``sqlite:///:memory:`` + ``runtime.execute()`` path
(visible on the EXISTING ``test_issue_1045_protection_runtime_cm_
deprecation.py`` too — it predates this shard). That is a DISTINCT bug
class (SQLite connection teardown in ``DataFlow.close()``'s ``:memory:`` /
async-SQL-node-cache path), NOT the protected-runtime event-loop leak this
shard closes. These tests therefore assert the event-loop drain
behaviorally and do not force GC of the aiosqlite connection into the test
body (which would surface the unrelated pre-existing leak). The aiosqlite
:memory: teardown leak is tracked as issue #1051 (distinct bug class,
DataFlow.close() core lifecycle, out of this shard's budget).

See issue #1045, issue #1051 (deferred aiosqlite :memory: teardown),
rules/dataflow-pool.md Rule 5 (no orphan runtimes),
rules/zero-tolerance.md Rule 1 (warnings are errors).
"""

from __future__ import annotations

import pytest

_wf = pytest.importorskip("kailash.workflow.builder")
WorkflowBuilder = _wf.WorkflowBuilder

from dataflow.core.protected_engine import ProtectedDataFlow
from dataflow.core.protection_middleware import ProtectedDataFlowRuntime


def _drive_persistent_loop(runtime: ProtectedDataFlowRuntime) -> None:
    """Run a trivial workflow so the runtime allocates its persistent loop.

    The execution OUTCOME is irrelevant (the :memory: table may not exist
    — protection is left permissive so no ProtectionViolation short-
    circuits, and LocalRuntime.execute() allocates the persistent loop
    before workflow execution either way). What matters is that
    ``runtime._persistent_loop`` becomes a live, non-closed loop.
    """
    workflow = WorkflowBuilder()
    workflow.add_node(
        "Issue1045CloseModelCreateNode",
        "create_it",
        {"name": "regression", "value": 1045},
    )
    try:
        runtime.execute(workflow.build())
    except Exception:
        # Outcome irrelevant — see docstring.
        pass


@pytest.mark.regression
class TestIssue1045ProtectedRuntimeClose:
    """ProtectedDataFlow.close()/close_async() drain protected runtimes."""

    def test_close_drains_protected_runtime_persistent_loop(self):
        """Behavioral: a used protected runtime's persistent event loop is
        closed by ProtectedDataFlow.close().

        This is the leak issue #1045's residual targets — without the fix
        the captured loop stays OPEN forever after the owning DataFlow is
        closed, because mark_externally_managed() skipped atexit and nothing
        else closes it.
        """
        db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )

        @db.model
        class Issue1045CloseModel:
            id: int
            name: str
            value: int

        runtime = db.create_protected_runtime()
        assert isinstance(runtime, ProtectedDataFlowRuntime)

        _drive_persistent_loop(runtime)

        # The runtime must have allocated a persistent loop (the thing that
        # leaks). If this is None the test is not exercising the leak.
        loop = runtime._persistent_loop
        assert loop is not None, (
            "ProtectedDataFlowRuntime did not allocate a persistent event "
            "loop; the leak surface is not being exercised."
        )
        assert not loop.is_closed(), "loop unexpectedly closed before db.close()"

        db.close()

        # The fix: ProtectedDataFlow.close() drains tracked runtimes.
        assert loop.is_closed(), (
            "ProtectedDataFlow.close() did NOT close the protected runtime's "
            "persistent event loop (issue #1045 regression). "
            "create_protected_runtime() registration or the close() drain "
            "was likely dropped."
        )
        assert runtime._persistent_loop is None, (
            "_cleanup_event_loop did not run for the protected runtime; "
            "_persistent_loop should be None after owner-driven close()."
        )

    def test_close_drains_multiple_protected_runtimes(self):
        """Every runtime from create_protected_runtime() is drained, not
        just the most recent one.

        create_protected_runtime() returns a FRESH runtime per call; the
        owner tracks the LIST. A fix that only closes the latest runtime
        still leaks the earlier ones.
        """
        db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )

        @db.model
        class Issue1045CloseModel:
            id: int
            name: str
            value: int

        runtimes = [db.create_protected_runtime() for _ in range(3)]
        loops = []
        for rt in runtimes:
            _drive_persistent_loop(rt)
            assert rt._persistent_loop is not None
            loops.append(rt._persistent_loop)

        db.close()

        for idx, loop in enumerate(loops):
            assert loop.is_closed(), (
                f"protected runtime #{idx} persistent loop NOT closed by "
                f"ProtectedDataFlow.close() — only-latest-runtime drain "
                f"(issue #1045 regression)."
            )

    async def test_close_async_drains_protected_runtimes(self):
        """Async-context teardown path: close_async() drains protected
        runtimes and is reachable on the cooperative-MRO chain.

        FastAPI lifespan / pytest-asyncio fixtures call close_async(), not
        close(). The cooperative-MRO override MUST exist on BOTH paths or
        async deployments never drain the protected runtimes at all.

        Note on scope: a *sync* ``LocalRuntime.execute()`` invoked while an
        outer event loop is already running (this test runs under
        pytest-asyncio) does NOT allocate ``runtime._persistent_loop`` — it
        detects the running outer loop and takes the no-persistent-loop
        path (``local.py`` outer-loop branch). The persistent-loop leak
        therefore only manifests in the SYNC-context path, fully asserted
        by ``test_close_drains_protected_runtime_persistent_loop`` /
        ``test_close_drains_multiple_protected_runtimes``. What this async
        test guards is the OTHER half of the contract: that
        ``close_async()`` exists on the mixin, runs the drain, clears the
        tracking list, and delegates to ``DataFlow.close_async()`` without
        raising — i.e. the async deployment path is wired, not just sync.
        """
        db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )

        @db.model
        class Issue1045CloseModel:
            id: int
            name: str
            value: int

        runtime = db.create_protected_runtime()
        assert isinstance(runtime, ProtectedDataFlowRuntime)
        # Owner registered it (the precondition for the drain).
        assert runtime in db._protected_runtimes

        await db.close_async()

        # The drain ran on the async path: the tracking list is emptied
        # (the structural proof close_async() called _drain_protected_
        # runtimes, NOT merely that DataFlow.close_async() ran). If the
        # mixin's close_async() override were missing, MRO would resolve
        # straight to DataFlow.close_async() and the list would still hold
        # the runtime.
        assert db._protected_runtimes == [], (
            "ProtectedDataFlow.close_async() did NOT drain the protected "
            "runtime tracking list (issue #1045 regression — the async "
            "deployment path bypasses the drain)."
        )
        # Idempotent second close_async() must not raise.
        await db.close_async()

    def test_protected_runtimes_tracked_on_owner(self):
        """Structural invariant: create_protected_runtime() registers the
        runtime on the owner.

        If a future refactor drops the ``self._protected_runtimes.append``
        in create_protected_runtime() (or the list init in __init__), the
        drain in close() silently misses every runtime and the leak
        re-opens with NO behavioral test failure on the cleanup path that
        no longer runs. This invariant fails loudly at that point.
        """
        db = ProtectedDataFlow(
            database_url="sqlite:///:memory:", enable_protection=True
        )
        try:
            assert hasattr(db, "_protected_runtimes"), (
                "DataFlowProtectionMixin.__init__ no longer initializes "
                "_protected_runtimes — the close() drain has nothing to "
                "iterate (issue #1045 regression)."
            )
            r1 = db.create_protected_runtime()
            r2 = db.create_protected_runtime()
            tracked = db._protected_runtimes
            assert r1 in tracked and r2 in tracked, (
                "create_protected_runtime() no longer registers the runtime "
                "on the owner; ProtectedDataFlow.close() cannot drain an "
                "untracked runtime (issue #1045 regression)."
            )
        finally:
            db.close()
