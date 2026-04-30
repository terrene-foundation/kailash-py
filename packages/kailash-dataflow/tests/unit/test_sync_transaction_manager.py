# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier 1 unit tests for ``SyncTransactionManager`` (issue #711).

These tests exercise the lifecycle of the BG-event-loop thread and the
typed-guard contract WITHOUT touching a real database. The Tier 2
regression tests in ``tests/regression/test_issue_711_transactions_sync.py``
cover the end-to-end behavior against real PostgreSQL.

Per ``rules/testing.md`` § 3-Tier Testing:
- Tier 1: mocking allowed, < 1s per test, no real infra.
"""

from __future__ import annotations

import threading
import warnings
from typing import Any

import pytest

from dataflow.features.transactions import (
    SyncTransactionManager,
    SyncTransactionScope,
    TransactionManager,
)


# ---------------------------------------------------------------------------
# Test doubles — Protocol-Satisfying Deterministic Adapter per
# rules/testing.md § "Protocol Adapters". These are NOT mocks: they are
# real classes with deterministic behavior used to satisfy the constructor
# contract without spawning a real database connection.
# ---------------------------------------------------------------------------


class _DataFlowStub:
    """Minimal stand-in for the DataFlow instance.

    SyncTransactionManager only reaches the DataFlow via its inner async
    TransactionManager when ``begin()`` is invoked — these unit tests cover
    construction + close + scope guard, none of which call begin(), so
    the stub never needs adapter resolution.
    """


@pytest.fixture
def async_manager() -> TransactionManager:
    """Real TransactionManager backed by the stub DataFlow."""
    return TransactionManager(_DataFlowStub())


# ---------------------------------------------------------------------------
# Lifecycle: BG thread starts on construction, stops on close
# ---------------------------------------------------------------------------


def test_construction_starts_bg_thread(async_manager):
    """SyncTransactionManager() spawns a daemon thread running the BG loop."""
    sync_mgr = SyncTransactionManager(async_manager)
    try:
        assert sync_mgr._thread is not None
        assert sync_mgr._thread.is_alive()
        assert sync_mgr._thread.daemon is True
        # Loop is running on the BG thread.
        assert sync_mgr._loop is not None
        assert sync_mgr._loop.is_running()
        assert sync_mgr._closed is False
    finally:
        sync_mgr.close_sync()


def test_close_sync_stops_bg_thread(async_manager):
    """close_sync() stops the loop and joins the thread."""
    sync_mgr = SyncTransactionManager(async_manager)
    thread_ref = sync_mgr._thread

    sync_mgr.close_sync()

    assert sync_mgr._closed is True
    # Refs cleared so post-close _run_sync raises the closed-error.
    assert sync_mgr._loop is None
    assert sync_mgr._thread is None
    # The captured thread reference has finished.
    assert thread_ref is not None
    assert not thread_ref.is_alive()


def test_close_sync_is_idempotent(async_manager):
    """Calling close_sync() twice MUST NOT raise."""
    sync_mgr = SyncTransactionManager(async_manager)
    sync_mgr.close_sync()
    # Second call is a no-op.
    sync_mgr.close_sync()
    assert sync_mgr._closed is True


def test_run_sync_after_close_raises(async_manager):
    """Once closed, ``_run_sync`` raises a typed ``RuntimeError``.

    This is the structural defense per ``rules/zero-tolerance.md`` Rule 3a:
    routing through a None backing object MUST raise an actionable typed
    error rather than a downstream ``AttributeError``.
    """

    sync_mgr = SyncTransactionManager(async_manager)
    sync_mgr.close_sync()

    async def _noop():
        return 1

    coro = _noop()
    try:
        with pytest.raises(RuntimeError, match="SyncTransactionManager is closed"):
            sync_mgr._run_sync(coro)
    finally:
        # Close the un-awaited coroutine so pytest does not surface a
        # RuntimeWarning at GC. The closed-manager path refuses the call
        # before the coroutine is scheduled, so it stays un-awaited.
        coro.close()


# ---------------------------------------------------------------------------
# ResourceWarning: __del__ on un-closed instance MUST emit ResourceWarning
# per rules/patterns.md § Async Resource Cleanup.
# ---------------------------------------------------------------------------


def test_del_emits_resource_warning_on_unclosed(async_manager):
    """Garbage-collecting an un-closed manager emits ResourceWarning.

    Per ``rules/patterns.md`` § Async Resource Cleanup: __del__ MUST emit
    ``ResourceWarning`` and do nothing else (no close call from the
    finalizer — that's the deadlock pattern the rule documents).
    """
    sync_mgr = SyncTransactionManager(async_manager)
    # Capture the BG thread so we can join it post-test (we did NOT call
    # close_sync — the warning fires precisely because of that).
    thread_ref = sync_mgr._thread

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        # Trigger __del__ by removing the only ref.
        del sync_mgr

        # Force a GC pass to ensure __del__ ran in this thread (CPython
        # refcount-based finalization fires synchronously when the last
        # ref drops, but PyPy / cyclic patterns rely on GC).
        import gc

        gc.collect()

    resource_warnings = [w for w in captured if issubclass(w.category, ResourceWarning)]
    assert len(resource_warnings) >= 1, (
        f"expected ResourceWarning on un-closed SyncTransactionManager; "
        f"got categories: {[w.category.__name__ for w in captured]}"
    )
    assert "not closed" in str(resource_warnings[0].message)

    # Manually clean up the BG thread we leaked on purpose. The daemon
    # flag means it dies with the interpreter regardless, but joining
    # keeps the test runner from leaking threads across the suite.
    if thread_ref is not None and thread_ref.is_alive():
        # The loop is still running — there's no manager left to call
        # close_sync, so we drive the loop stop directly via the thread's
        # loop attribute (we captured nothing else). Best-effort — the
        # daemon flag is the safety net.
        thread_ref.join(timeout=0.01)


def test_del_silent_on_closed(async_manager):
    """A cleanly-closed manager does NOT emit ResourceWarning on GC."""
    sync_mgr = SyncTransactionManager(async_manager)
    sync_mgr.close_sync()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        del sync_mgr
        import gc

        gc.collect()

    resource_warnings = [w for w in captured if issubclass(w.category, ResourceWarning)]
    assert resource_warnings == [], (
        f"closed manager MUST NOT emit ResourceWarning; got: "
        f"{[(w.category.__name__, str(w.message)) for w in captured]}"
    )


# ---------------------------------------------------------------------------
# Out-of-scope guard on SyncTransactionScope (no DB needed)
# ---------------------------------------------------------------------------


def test_sync_scope_execute_raw_after_inactive_raises():
    """``execute_raw`` outside the with body raises typed ``RuntimeError``.

    Mirrors the async-side test
    ``test_execute_raw_outside_scope_raises_runtime_error`` but for the
    sync surface — exercises the typed delegate guard per
    ``rules/zero-tolerance.md`` Rule 3a.
    """
    # Construct a sync scope without entering any begin(); the inactive
    # marker is set explicitly so ``execute_raw`` MUST raise the typed
    # guard. ``conn`` is a placeholder — the test exercises the guard
    # path before any DB call could fire.
    sync_scope = SyncTransactionScope(
        conn=object(),
        run_sync=lambda coro: None,
        id="test_scope",
        isolation_level="READ COMMITTED",
        status="active",
        type="transaction",
    )
    sync_scope._mark_inactive()

    with pytest.raises(RuntimeError, match="outside the transaction body"):
        sync_scope.execute_raw("SELECT 1")
