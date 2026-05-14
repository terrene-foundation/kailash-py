# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression test for issue #1002 — sync ``DataFlow.close()`` MUST close cached
``AsyncSQLDatabaseNode`` instances.

Per ``workspaces/issue-1002-aiosqlite-fixture-cleanup/journal/0004-DISCOVERY-...md``:
``DataFlow.close_async()`` at ``engine.py:10116-10127`` closes every cached
``AsyncSQLDatabaseNode``; the sync ``DataFlow.close()`` at ``engine.py:9948`` did
NOT — when a test wrapped DataFlow in ``with DataFlow(...) as db:`` AND the sync
code path (e.g. ``refresh_derived_sync``) cached an ``AsyncSQLDatabaseNode``, the
node leaked and its ``__del__`` finalizer fired later, emitting
``PytestUnraisableExceptionWarning``.

This regression test directly exercises the cache-cleanup contract: prime the
cache with a stub node that records its close() call, run sync ``close()``,
assert (a) ``close()`` was awaited on the stub, AND (b) the cache is cleared.
Tier 1 — no real database required; the contract is "sync close() iterates
the cache and closes each entry," not the semantics of any specific adapter.

Tier 2 sibling coverage already exists via ``packages/kailash-dataflow/tests/integration/``
suites that exercise the full sync-vs-async close lifecycle under real adapters.
"""

from __future__ import annotations

import pytest

from dataflow import DataFlow

pytestmark = [pytest.mark.regression]


class _RecordingNode:
    """Protocol-satisfying stub that records its async close() invocation.

    Per ``rules/testing.md`` § "3-Tier Testing", a deterministic
    Protocol-Satisfying adapter is NOT a mock — it exposes the same
    ``close()`` shape ``AsyncSQLDatabaseNode`` exposes and records the
    invocation for structural verification.
    """

    def __init__(self) -> None:
        self.close_called = False

    async def close(self) -> None:
        self.close_called = True


def test_sync_close_closes_cached_async_sql_node_and_clears_cache() -> None:
    """Sync close() MUST close cached AsyncSQLDatabaseNode AND clear the cache.

    Mirrors close_async() lines 10116-10127. Without this, sync-context
    teardown (``with DataFlow(...) as db:``) leaks cached nodes whose
    ``__del__`` later emits ``PytestUnraisableExceptionWarning``.
    """
    db = DataFlow(":memory:", auto_migrate=False)
    try:
        # Prime the cache via the same shape the engine's own caching path uses.
        # _async_sql_node_cache is keyed by db_type, value is (node, event_loop_id).
        node_a = _RecordingNode()
        node_b = _RecordingNode()
        db._async_sql_node_cache["sqlite"] = (node_a, 0)
        db._async_sql_node_cache["postgresql"] = (node_b, 0)

        assert not node_a.close_called
        assert not node_b.close_called
        assert len(db._async_sql_node_cache) == 2

        # Exercise the sync close path. This is what `with DataFlow(...) as db:`
        # __exit__ invokes; the fix iterates _async_sql_node_cache and bridges
        # each node.close() through async_safe_run.
        db.close()

        # Structural assertions: both nodes had close() awaited, and the cache
        # was cleared so a second close() is a no-op (idempotency preserved).
        assert (
            node_a.close_called
        ), "sync close() did not close cached AsyncSQLDatabaseNode (sqlite entry)"
        assert (
            node_b.close_called
        ), "sync close() did not close cached AsyncSQLDatabaseNode (postgresql entry)"
        assert (
            len(db._async_sql_node_cache) == 0
        ), "sync close() did not clear _async_sql_node_cache"
    finally:
        # If the test above raised before close() ran, ensure we don't leak.
        if not db._closed:
            db.close()


def test_sync_close_with_context_manager_closes_cached_async_sql_node() -> None:
    """`with DataFlow(...) as db:` __exit__ MUST close cached AsyncSQLDatabaseNode.

    This is the user-facing path that journal/0004 identified as the leak
    site: synchronous ``with`` block + ``refresh_derived_sync`` triggers
    caching, then ``__exit__`` calls sync close().
    """
    node = _RecordingNode()
    with DataFlow(":memory:", auto_migrate=False) as db:
        db._async_sql_node_cache["sqlite"] = (node, 0)
        assert len(db._async_sql_node_cache) == 1
    # __exit__ called sync close() which MUST have closed the cached node.
    assert node.close_called
    assert len(db._async_sql_node_cache) == 0


def test_sync_close_tolerates_node_close_failure_and_still_clears_cache() -> None:
    """Per the fix's exception handling (logger.debug on failure), one bad
    node MUST NOT block cleanup of the others, AND the cache MUST still clear.
    """

    class _FailingNode:
        async def close(self) -> None:
            raise RuntimeError("simulated adapter close failure")

    good = _RecordingNode()
    bad = _FailingNode()
    db = DataFlow(":memory:", auto_migrate=False)
    try:
        db._async_sql_node_cache["postgresql"] = (bad, 0)
        db._async_sql_node_cache["sqlite"] = (good, 0)

        # MUST NOT raise — failures are logged at DEBUG per the engine fix.
        db.close()

        assert good.close_called, "sibling cleanup blocked by failing node"
        assert (
            len(db._async_sql_node_cache) == 0
        ), "cache not cleared after partial failure"
    finally:
        if not db._closed:
            db.close()
