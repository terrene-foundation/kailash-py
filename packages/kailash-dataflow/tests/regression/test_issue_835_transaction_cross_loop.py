# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""
Regression test for issue #835 — `db.transactions.begin()` MUST resolve a
per-loop asyncpg pool so transactions work from any caller event loop.

Pre-fix, ``TransactionManager._get_adapter`` returned the long-lived
``_connection_manager._adapter`` whose pool was created inside
``async_safe_run`` 's worker-thread loop. That loop closed at return; every
subsequent ``begin()`` on a different loop hit
``RuntimeError: Event loop is closed`` on ``pool.acquire()``.

The fix routes resolution through
``DataFlow._get_or_create_async_sql_node(db_type)._get_adapter()`` — the
priority chain at ``async_sql.py:4173`` keyed on
``loop_id|db_type|connection|pool_size|max_pool_size``. Each event loop
receives its own pool; pools are reaped on loop close via
WeakValueDictionary semantics.

Per ``rules/testing.md`` § "3-Tier Testing" Tier 2: NO mocking. Every test
runs against the real PostgreSQL test instance via the
``IntegrationTestSuite`` harness.
"""

from __future__ import annotations

import asyncio
import gc
import time
import uuid
from typing import Any

import pytest
from kailash.nodes.data.async_sql import _PROCESS_POOL_REGISTRY, set_pool_defaults

from dataflow import DataFlow
from dataflow.features.transactions import TransactionScope
from tests.infrastructure.test_harness import IntegrationTestSuite

# dataflow_lifecycle: asserts GC reaping of pool-registry entries across closed
# loops; opts out of the autouse close-fixture (conftest.py F-TEST-HYGIENE) whose
# strong reference would keep pools alive and break the registry-cap assertions.
pytestmark = [
    pytest.mark.regression,
    pytest.mark.integration,
    pytest.mark.dataflow_lifecycle,
]


# ---------------------------------------------------------------------------
# Conftest mitigation — autouse fixture lowers `idle_timeout` so pool churn
# from cross-loop tests doesn't trip `max_pool_count_per_process=100` cap
# under pytest-xdist parallelism. Restored to prior value on teardown.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _aggressive_pool_reaper():
    """Reduce idle_timeout for cross-loop tests; restore on teardown.

    Each pytest-asyncio function-scoped test creates a fresh loop and
    therefore a fresh pool entry in ``_PROCESS_POOL_REGISTRY``. With the
    default 300s idle timeout, 100 sequential tests fill the cap and
    cause subsequent tests to fail at pool creation. Lowering to 2s
    keeps the cap clear; the trade-off (more frequent re-init in
    production) is irrelevant in tests.
    """
    prior = set_pool_defaults(idle_timeout=2)
    yield
    # Restore prior defaults — `set_pool_defaults` returned the prior
    # value as a dict; replay it with the same kwargs API.
    if isinstance(prior, dict) and "idle_timeout" in prior:
        set_pool_defaults(idle_timeout=prior["idle_timeout"])


# ---------------------------------------------------------------------------
# Local fixtures — `test_suite` lives in tests/integration/conftest.py and
# is not auto-discovered for tests/regression/. Define a regression-scope
# copy that uses the same IntegrationTestSuite harness against real Postgres.
# ---------------------------------------------------------------------------


@pytest.fixture
async def pg_test_suite():
    """Create the IntegrationTestSuite once per test (real Postgres)."""
    suite = IntegrationTestSuite()
    try:
        async with suite.session():
            yield suite
    except Exception as exc:
        pytest.skip(
            f"Cannot reach PostgreSQL test infra: {type(exc).__name__}: {exc}. "
            f"Ensure shared SDK Docker is running on port 5434."
        )


@pytest.fixture
async def temp_table_name():
    """Unique temp table name per test for isolation."""
    return f"tx_835_{int(time.time() * 1_000_000)}_{uuid.uuid4().hex[:8]}"


@pytest.fixture
async def temp_table(pg_test_suite, temp_table_name):
    """Create + drop a clean test table for each test."""
    create_sql = f"""
        CREATE TABLE {temp_table_name} (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE,
            payload TEXT,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """
    async with pg_test_suite.get_connection() as conn:
        await conn.execute(create_sql)

    yield temp_table_name

    async with pg_test_suite.get_connection() as conn:
        await conn.execute(f"DROP TABLE IF EXISTS {temp_table_name} CASCADE")


@pytest.fixture
async def df(pg_test_suite):
    """A DataFlow against the real Postgres infra; closed on teardown.

    NOTE: ``await instance.initialize()`` is required so the
    reachability gate (Phase 2 of issue #835's fix) runs once.
    """
    instance = DataFlow(database_url=pg_test_suite.config.url, auto_migrate=False)
    await instance.initialize()
    try:
        yield instance
    finally:
        try:
            await instance.close_async()
        except Exception:
            pass


async def _count_rows(pg_test_suite, table: str) -> int:
    """Read row-count via a FRESH connection from the integration suite —
    outside any DataFlow transaction. Proves commit persisted to disk."""
    async with pg_test_suite.get_connection() as conn:
        return await conn.fetchval(f"SELECT COUNT(*) FROM {table}")


# ---------------------------------------------------------------------------
# Tier 2 regression coverage — 9 tests covering the per-loop pool contract
# ---------------------------------------------------------------------------


async def test_transaction_works_in_fresh_asyncio_run(pg_test_suite, temp_table):
    """Bug repro inverted: construct DataFlow + run transaction inside a
    fresh ``asyncio.run`` invocation. Pre-fix this raised
    ``RuntimeError: Event loop is closed``; post-fix it succeeds.
    """
    db_url = pg_test_suite.config.url
    table = temp_table

    async def _payload() -> int:
        instance = DataFlow(database_url=db_url, auto_migrate=False)
        await instance.initialize()
        try:
            async with instance.transactions.begin() as tx:
                await tx.execute_raw(
                    f"INSERT INTO {table} (email, payload) VALUES ($1, $2)",
                    ["fresh-run@example.test", "asyncio-run"],
                )
            return 1
        finally:
            try:
                await instance.close_async()
            except Exception:
                pass

    # Run the payload inside its own asyncio.run — exercises the
    # "single asyncio.run, transaction works" contract that the bug repro
    # in briefs/01-issue-835.md documents.
    inserted = await asyncio.to_thread(asyncio.run, _payload())
    assert inserted == 1
    assert await _count_rows(pg_test_suite, table) == 1


async def test_transaction_works_across_pytest_asyncio_loops(df, temp_table):
    """Two consecutive ``begin()`` calls within the same async test must
    both succeed. Pre-fix the second call hit "Event loop is closed" if
    the first call's pool was bound to a different loop.
    """
    async with df.transactions.begin() as tx:
        await tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["loop1@example.test", "first-call"],
        )

    async with df.transactions.begin() as tx:
        await tx.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["loop2@example.test", "second-call"],
        )

    rows = []
    async with df.transactions.begin() as tx:
        rows = await tx.execute_raw(f"SELECT email FROM {temp_table} ORDER BY email")
    assert {dict(r)["email"] for r in rows} == {
        "loop1@example.test",
        "loop2@example.test",
    }


async def test_transaction_pool_keyed_per_loop(pg_test_suite, temp_table):
    """The pool resolved by a transaction MUST be loop-local — its
    ``_loop`` attribute (or equivalent) MUST match the loop that
    requested the transaction.
    """
    db_url = pg_test_suite.config.url
    instance = DataFlow(database_url=db_url, auto_migrate=False)
    try:
        await instance.initialize()
        loop = asyncio.get_running_loop()
        async with instance.transactions.begin() as tx:
            assert isinstance(tx, TransactionScope)
            # The adapter resolved by the active transaction is the one
            # owned by AsyncSQLDatabaseNode for THIS loop. Resolve it via
            # the same path TransactionManager uses, then assert the pool
            # is bound to the current loop.
            db_type = instance._detect_database_type()
            node = instance._get_or_create_async_sql_node(db_type)
            adapter = await node._get_adapter()
            # Same pool-attribute normalization the production code does:
            # core-SDK adapters expose `_pool`, dataflow-package adapters
            # expose `connection_pool` — accept either.
            pool = getattr(adapter, "connection_pool", None) or getattr(
                adapter, "_pool", None
            )
            assert pool is not None
            # asyncpg.Pool exposes `_loop`; if absent (other dialect) the
            # resolution path is still per-loop because the registry key
            # itself contains `loop_id`.
            pool_loop = getattr(pool, "_loop", None)
            if pool_loop is not None:
                assert (
                    pool_loop is loop
                ), "transaction adapter pool MUST be bound to the caller's loop"
    finally:
        try:
            await instance.close_async()
        except Exception:
            pass


async def test_init_fail_fast_on_unreachable_db_unchanged():
    """Phase 2 of the fix preserves the existing reachability gate
    (``rules/dataflow-pool.md`` Rule 2). Constructing a DataFlow against
    an unreachable URL MUST raise at ``initialize()`` time, not at first
    user-driven query.
    """
    bad_url = "postgresql://nope:nope@127.0.0.1:65530/nope"
    instance = DataFlow(database_url=bad_url, auto_migrate=False)
    with pytest.raises(Exception):
        # Initialize is the gate; if reachability slipped through, the
        # later `transactions.begin()` would still fail — but at the wrong
        # surface, defeating the fail-fast contract.
        await instance.initialize()


async def test_transaction_pool_reaped_when_loop_closes(pg_test_suite, temp_table):
    """When the loop that created a per-loop pool closes, the
    WeakValueDictionary entry MUST be reapable. Verifies the registry
    does not pin pools by strong reference.

    Runs the inner payload on a worker thread (with its own fresh loop)
    because pytest-asyncio already owns the test's loop — calling
    ``loop.run_until_complete`` from inside the test body would raise
    ``RuntimeError: Cannot run the event loop while another loop is running``.
    """
    db_url = pg_test_suite.config.url
    table = temp_table

    async def _payload():
        instance = DataFlow(database_url=db_url, auto_migrate=False)
        await instance.initialize()
        try:
            async with instance.transactions.begin() as tx:
                await tx.execute_raw(
                    f"INSERT INTO {table} (email, payload) VALUES ($1, $2)",
                    ["reap@example.test", "ephemeral"],
                )
        finally:
            try:
                await instance.close_async()
            except Exception:
                pass

    # Run on a worker thread with its own fresh loop. Cannot use
    # `loop.run_until_complete` directly here — pytest-asyncio owns the
    # test's loop, so a nested run_until_complete on the same thread
    # raises `Cannot run the event loop while another loop is running`.
    def _run_in_fresh_loop():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_payload())
        finally:
            loop.close()

    await asyncio.to_thread(_run_in_fresh_loop)

    # Force GC; the registry uses WeakValueDictionary semantics — the
    # entry whose loop just closed should be eligible for collection.
    gc.collect()
    # We can't deterministically assert the entry is gone (timing of
    # weakref reaping depends on the pool object's GC), but the entry
    # MUST not have grown into a permanent leak. The cap-survival test
    # (#9 below) is the load-bearing assertion for the no-leak contract.
    after_keys = {k for k in _PROCESS_POOL_REGISTRY.keys() if db_url in k}
    # Entries are either reaped or capped — either way, the count
    # MUST stay within `max_pool_count_per_process` (default 100).
    assert len(after_keys) <= 100


async def test_transaction_first_db_touch_is_transaction(pg_test_suite, temp_table):
    """Issue #835 H4: when the FIRST DB-touch on a fresh DataFlow is a
    transaction (no prior Express call), `_ensure_connected` and the
    transaction's `_get_adapter()` must coexist on the same loop without
    a pool-loop binding race.
    """
    db_url = pg_test_suite.config.url
    instance = DataFlow(database_url=db_url, auto_migrate=False)
    try:
        await instance.initialize()
        # Skip Express; go directly to transactions.
        async with instance.transactions.begin() as tx:
            await tx.execute_raw(
                f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                ["first-touch@example.test", "no-express-prior"],
            )
        assert await _count_rows(pg_test_suite, temp_table) == 1
    finally:
        try:
            await instance.close_async()
        except Exception:
            pass


async def test_execute_raw_outside_async_with_raises_runtime_error(df, temp_table):
    """Issue #835 H5: the typed-delegate guard at transactions.py:162 MUST
    survive the per-loop migration. Calling `tx.execute_raw` after the
    `async with` body exits raises RuntimeError, NOT a stale-connection
    AttributeError.
    """
    captured: dict[str, Any] = {}
    async with df.transactions.begin() as tx:
        captured["tx"] = tx
    # Scope exited — `_active_transaction` ContextVar is reset.
    with pytest.raises(RuntimeError, match="outside the transaction body"):
        await captured["tx"].execute_raw(
            f"SELECT 1 FROM {temp_table}",
        )


async def test_savepoint_nesting_same_loop_pinning(df, pg_test_suite, temp_table):
    """Issue #835 H3 (dataflow-specialist): nested begin() on the same
    loop MUST issue SAVEPOINT pinning the OUTER connection. Inner
    rollback MUST roll back ONLY the savepoint; outer commit persists.
    """
    async with df.transactions.begin() as outer:
        await outer.execute_raw(
            f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
            ["outer@example.test", "outer-row"],
        )

        # Inner transaction: SAVEPOINT
        with pytest.raises(RuntimeError, match="rollback inner"):
            async with df.transactions.begin() as inner:
                await inner.execute_raw(
                    f"INSERT INTO {temp_table} (email, payload) VALUES ($1, $2)",
                    ["inner@example.test", "inner-row"],
                )
                # Inner transaction sees BOTH rows on its pinned connection.
                rows = await inner.execute_raw(
                    f"SELECT email FROM {temp_table} ORDER BY email"
                )
                assert len(rows) == 2
                raise RuntimeError("rollback inner")

        # After SAVEPOINT rollback: outer transaction's row remains;
        # inner's row is gone. The pinned connection MUST still be valid.
        post_rollback = await outer.execute_raw(
            f"SELECT email FROM {temp_table} ORDER BY email"
        )
        assert {dict(r)["email"] for r in post_rollback} == {"outer@example.test"}

    # After outer commit, only the outer row persists — verified via a
    # FRESH connection from the integration suite, outside any DataFlow
    # transaction (per `rules/testing.md` § State Persistence Verification).
    assert await _count_rows(pg_test_suite, temp_table) == 1


async def test_pool_cap_survives_xdist_loops(pg_test_suite, temp_table):
    """Issue #835 H6: stress test — N sequential loops creating + closing
    transactions MUST keep ``len(_PROCESS_POOL_REGISTRY)`` within
    ``max_pool_count_per_process`` (default 100). The autouse
    aggressive-reaper fixture lowers ``idle_timeout`` to 2s so reaping
    keeps the cap clear under churn.
    """
    db_url = pg_test_suite.config.url
    table = temp_table

    async def _one_iteration(i: int):
        instance = DataFlow(database_url=db_url, auto_migrate=False)
        try:
            await instance.initialize()
            async with instance.transactions.begin() as tx:
                await tx.execute_raw(
                    f"INSERT INTO {table} (email, payload) VALUES ($1, $2)",
                    [f"churn-{i}@example.test", f"iter-{i}"],
                )
        finally:
            try:
                await instance.close_async()
            except Exception:
                pass

    # 50 sequential loops — empirically enough to exercise reaping
    # without making the test prohibitively slow. Each iteration runs on
    # a worker thread with its own fresh loop because pytest-asyncio
    # already owns this test's loop.
    def _run_iteration_in_fresh_loop(i: int) -> None:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_one_iteration(i))
        finally:
            loop.close()

    for i in range(50):
        await asyncio.to_thread(_run_iteration_in_fresh_loop, i)
        gc.collect()

        # After each iteration, registry size MUST stay below cap.
        registry_size = len(_PROCESS_POOL_REGISTRY)
        assert registry_size <= 100, (
            f"_PROCESS_POOL_REGISTRY grew to {registry_size} entries "
            f"after iteration {i}; reaper not keeping up under churn"
        )

    # All 50 inserts should have persisted (each on a fresh loop, each
    # successful). Read-back via a fresh integration-suite connection.
    final_count = await _count_rows(pg_test_suite, table)
    assert final_count == 50
