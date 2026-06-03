# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression test for issue #1248.

``LocalRuntime``'s sync-bridge teardown (``_execute_sync.run_in_thread``) and
``_cleanup_event_loop``, plus ``AsyncLocalRuntime.cleanup``, called
``AsyncSQLDatabaseNode.clear_shared_pools(graceful=True)`` UNCONDITIONALLY —
disposing every pool in the process-wide registry, including connection pools
created on, and still owned by, a *different, live* event loop. The owning
loop then hit ``RuntimeWarning: ... attached to a different loop`` and had to
re-initialize the pool (churn), with intermittent query failures under load.

The fix scopes disposal to the disposing loop via the new
``clear_shared_pools(loop_id=...)`` filter (pool keys begin with
``f"{loop_id}|"`` per ``_generate_pool_key``). Tier-1 pins the filter; Tier-2
reproduces the cross-loop scenario against real Postgres.
"""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from urllib.parse import urlparse

import pytest

from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode

PG_DSN = os.environ.get(
    "TEST_POSTGRES_DSN",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def _pg_reachable(dsn: str) -> bool:
    parsed = urlparse(dsn)
    host, port = parsed.hostname or "localhost", parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


# ---------------------------------------------------------------------------
# Tier 1 — deterministic: clear_shared_pools(loop_id=...) scopes by loop.
# ---------------------------------------------------------------------------


class _StubAdapter:
    """Protocol-satisfying deterministic adapter (NOT a mock).

    Exposes the single ``disconnect()`` coroutine ``clear_shared_pools``
    invokes, recording whether it was disposed.
    """

    def __init__(self) -> None:
        self.disconnected = False

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1248_clear_shared_pools_scopes_to_loop_id():
    """A loop-scoped clear disposes ONLY that loop's pools, leaving others."""
    loop_a, loop_b = 991248001, 991248002  # synthetic, collision-free loop ids
    key_a = f"{loop_a}|postgresql|h:5432:db:u|10|20"
    key_b = f"{loop_b}|postgresql|h:5432:db:u|10|20"
    adapter_a, adapter_b = _StubAdapter(), _StubAdapter()

    AsyncSQLDatabaseNode._shared_pools[key_a] = (adapter_a, 1)
    AsyncSQLDatabaseNode._shared_pools[key_b] = (adapter_b, 1)
    try:
        result = await AsyncSQLDatabaseNode.clear_shared_pools(
            graceful=True, loop_id=loop_a
        )

        # Only loop_a's pool was considered + disposed.
        assert result["total_pools"] == 1
        assert result["pools_cleared"] == 1
        assert adapter_a.disconnected is True
        assert adapter_b.disconnected is False
        # loop_a removed; loop_b's live pool untouched.
        assert key_a not in AsyncSQLDatabaseNode._shared_pools
        assert key_b in AsyncSQLDatabaseNode._shared_pools
    finally:
        AsyncSQLDatabaseNode._shared_pools.pop(key_a, None)
        AsyncSQLDatabaseNode._shared_pools.pop(key_b, None)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1248_unscoped_clear_still_disposes_all():
    """No loop_id (default) preserves the original dispose-everything behavior."""
    key_a = "991248101|postgresql|h:5432:db:u|10|20"
    key_b = "991248102|postgresql|h:5432:db:u|10|20"
    adapter_a, adapter_b = _StubAdapter(), _StubAdapter()
    AsyncSQLDatabaseNode._shared_pools[key_a] = (adapter_a, 1)
    AsyncSQLDatabaseNode._shared_pools[key_b] = (adapter_b, 1)
    try:
        await AsyncSQLDatabaseNode.clear_shared_pools(graceful=True)
        assert adapter_a.disconnected is True
        assert adapter_b.disconnected is True
        assert key_a not in AsyncSQLDatabaseNode._shared_pools
        assert key_b not in AsyncSQLDatabaseNode._shared_pools
    finally:
        AsyncSQLDatabaseNode._shared_pools.pop(key_a, None)
        AsyncSQLDatabaseNode._shared_pools.pop(key_b, None)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_1248_scoped_clear_preserves_no_loop_pools_and_registry():
    """A scoped clear must leave `no_loop` pools AND the process registry intact.

    Pins the two halves of the fix the loop-key filter alone doesn't cover:
    (a) sync-context `no_loop|...` pools are not owned by any event loop, so a
    loop-scoped teardown MUST skip them (sweeping them would be the same bug
    class #1248 fixes); the unscoped path still disposes them.
    (b) a scoped clear MUST NOT blanket-clear `_PROCESS_POOL_REGISTRY` (that
    would corrupt cap accounting for other live loops' pools); the unscoped
    clear does clear it.
    """
    from kailash.nodes.data import async_sql as _async_sql

    no_loop_key = "no_loop|postgresql|h:5432:db:u|10|20"
    scoped_key = "991248301|postgresql|h:5432:db:u|10|20"
    no_loop_adapter, scoped_adapter = _StubAdapter(), _StubAdapter()
    # Hold a strong ref so the WeakValueDictionary entry survives until we drop it.
    registry_sentinel = _StubAdapter()
    registry_token = "test-1248-registry-sentinel"

    AsyncSQLDatabaseNode._shared_pools[no_loop_key] = (no_loop_adapter, 1)
    AsyncSQLDatabaseNode._shared_pools[scoped_key] = (scoped_adapter, 1)
    _async_sql._PROCESS_POOL_REGISTRY[registry_token] = registry_sentinel
    try:
        # Scoped clear of the real-loop key: no_loop pool + registry survive.
        await AsyncSQLDatabaseNode.clear_shared_pools(graceful=True, loop_id=991248301)
        assert scoped_adapter.disconnected is True
        assert no_loop_adapter.disconnected is False
        assert no_loop_key in AsyncSQLDatabaseNode._shared_pools
        assert registry_token in _async_sql._PROCESS_POOL_REGISTRY

        # Unscoped clear: no_loop pool disposed AND registry cleared.
        await AsyncSQLDatabaseNode.clear_shared_pools(graceful=True)
        assert no_loop_adapter.disconnected is True
        assert no_loop_key not in AsyncSQLDatabaseNode._shared_pools
        assert registry_token not in _async_sql._PROCESS_POOL_REGISTRY
    finally:
        AsyncSQLDatabaseNode._shared_pools.pop(no_loop_key, None)
        AsyncSQLDatabaseNode._shared_pools.pop(scoped_key, None)
        _async_sql._PROCESS_POOL_REGISTRY.pop(registry_token, None)


# ---------------------------------------------------------------------------
# Tier 2 — real Postgres: a worker-thread LocalRuntime teardown must NOT
# dispose the pool owned by this (live) loop.
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.skipif(
    not _pg_reachable(PG_DSN),
    reason=f"Postgres not reachable at {urlparse(PG_DSN).hostname}:{urlparse(PG_DSN).port}",
)
async def test_issue_1248_worker_thread_localruntime_preserves_live_loop_pool():
    """A LocalRuntime run in a worker thread must not dispose THIS loop's pool.

    Reproduces the issue: loop A (this test) holds a live async-SQL pool; a
    LocalRuntime runs a trivial (no-DB) workflow in a worker thread, whose
    teardown previously disposed *every* pool — including loop A's. After the
    fix, the worker thread's teardown is scoped to its own ephemeral loop, so
    loop A's pool survives and stays usable.
    """
    from kailash.runtime.local import LocalRuntime
    from kailash.workflow.builder import WorkflowBuilder

    this_loop_id = id(asyncio.get_running_loop())
    node = AsyncSQLDatabaseNode(
        node_id="reader_1248",
        connection_string=PG_DSN,
        database_type="postgresql",
    )
    try:
        await node.async_run(query="SELECT 1")  # pool created, keyed to this loop

        def our_pool_keys() -> list[str]:
            return [
                k
                for k in AsyncSQLDatabaseNode._shared_pools
                if k.startswith(f"{this_loop_id}|")
            ]

        before = our_pool_keys()
        assert before, "expected this loop to own a pool after the first query"

        # Worker thread: ephemeral loop + LocalRuntime teardown calls
        # clear_shared_pools. The no-DB workflow creates no pool on the
        # ephemeral loop, so a correct (scoped) teardown disposes nothing.
        errors: list[BaseException] = []

        def run_localruntime_in_thread() -> None:
            try:
                wf = WorkflowBuilder()
                wf.add_node("PythonCodeNode", "noop", {"code": "result = 1"})
                # ``with`` exercises BOTH teardown paths in the worker thread:
                # ``run_in_thread`` (sync bridge during execute) and
                # ``_cleanup_event_loop`` (at __exit__) — both previously
                # disposed every loop's pools.
                with LocalRuntime() as runtime:
                    runtime.execute(wf.build())
            except BaseException as exc:  # pragma: no cover - surfaced via assert
                errors.append(exc)

        thread = threading.Thread(target=run_localruntime_in_thread)
        thread.start()
        thread.join(timeout=30)
        assert not thread.is_alive(), "worker-thread LocalRuntime hung"
        assert not errors, f"worker thread raised: {errors!r}"

        # The load-bearing assertion: our live loop's pool SURVIVED.
        after = our_pool_keys()
        assert after == before, (
            "worker-thread LocalRuntime teardown disposed THIS loop's pool "
            f"(#1248): before={before} after={after}"
        )

        # And it is still usable on this loop without re-init / cross-loop error.
        result = await node.async_run(query="SELECT 1")
        assert result is not None
    finally:
        await AsyncSQLDatabaseNode.clear_shared_pools(
            graceful=True, loop_id=this_loop_id
        )
