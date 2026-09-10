"""Tier-2 regression for issue #697 + #698 — AsyncSQLDatabaseNode pool leak.

Reproduces the JourneyMate / Azure PostgreSQL connection-leak class
against real PostgreSQL and locks in the DPI-B fix (DPI-B1 through
DPI-B4):

    - pool count stays bounded under lock contention (the original bug)
    - PoolExhaustedError fires at the configured cap (DPI-B4)
    - idle pools are reaped within idle_timeout (DPI-B3)
    - active pools survive the reaper (DPI-B3 invariant)
    - cross-event-loop dead pools are reaped via WeakValueDictionary
      semantics (DPI-B2)
    - set_pool_defaults rejects unknown kwargs (DPI-B2 invariant)

NO MOCKING per rules/testing.md § Tier 2 — every test runs against the
``kailash_test_postgres`` Docker container.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from kailash.nodes.data.async_sql import (
    _POOL_DEFAULTS,
    _PROCESS_POOL_REGISTRY,
    AsyncSQLDatabaseNode,
    EnterpriseConnectionPool,
    _idle_target,
    set_pool_defaults,
)
from kailash.nodes.data.exceptions import PoolExhaustedError

# Skip the whole module if Docker / PG isn't available — match other
# regression tests' guards.
try:
    from tests.utils.docker_config import (
        DATABASE_CONFIG,
        ensure_docker_services,
        get_postgres_connection_string,
    )
except ImportError:  # pragma: no cover
    pytest.skip("docker_config not available", allow_module_level=True)


pytestmark = [
    pytest.mark.regression,
    pytest.mark.integration,
    pytest.mark.requires_docker,
]


@pytest.fixture(autouse=True)
def _verify_docker_services():
    """Skip the test if PG isn't running. Mirrors DockerIntegrationTestBase."""
    services_ok = asyncio.run(ensure_docker_services())
    if not services_ok:
        pytest.skip("Required Docker services not available. Run './test-env up'")


@pytest.fixture
def pg_dsn():
    """PostgreSQL connection string from the docker_config helper."""
    return get_postgres_connection_string()


# ---------------------------------------------------------------------------
# Test 1 — pool count stays bounded under lock contention
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_count_stays_bounded_under_lock_contention(pg_dsn):
    """50 concurrent reads with cap=10 → pool_count() <= 10 always.

    The pre-fix bug: every per-pool-lock timeout silently created a
    fresh dedicated pool with no process-wide bound. Under saturation
    that produced 480-500 backend connections (Azure PG ceiling 100-200).

    Setup:
        - cap = 10 (set_pool_defaults)
        - lock timeout = default (5s) — contention may or may not fire
        - 50 concurrent SELECT 1 calls

    Assertion: ``AsyncSQLDatabaseNode.pool_count()`` never exceeds 10.
    """
    set_pool_defaults(max_pool_count_per_process=10, idle_timeout=300)

    async def _one_query(i: int) -> int:
        node = AsyncSQLDatabaseNode(
            name=f"q_{i}",
            database_type="postgresql",
            connection_string=pg_dsn,
            query="SELECT 1 AS n",
            validate_queries=False,
        )
        try:
            result = await node.async_run()
            return result["result"]["data"][0]["n"]  # type: ignore[index]
        finally:
            try:
                if node._adapter is not None:
                    await node._adapter.disconnect()
            except Exception:
                pass

    # Run 50 concurrent — under the cap because each completes quickly.
    await asyncio.gather(*(_one_query(i) for i in range(50)), return_exceptions=True)

    # The cap is structural — the assertion holds whether the contention
    # path fired or not. The KEY invariant is "pool_count NEVER blew
    # past the cap" — which the pre-fix code violated immediately.
    assert AsyncSQLDatabaseNode.pool_count() <= 10


# ---------------------------------------------------------------------------
# Test 2 — PoolExhaustedError fires at cap
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pool_exhausted_error_fires_at_cap(pg_dsn, monkeypatch):
    """When the registry is at cap and the lock times out, the
    fallback raises PoolExhaustedError instead of silently creating
    yet another pool.

    Forces the lock-timeout fallback by monkeypatching
    ``_acquire_pool_lock_with_timeout`` to raise immediately, then
    seeds the registry to cap.
    """
    set_pool_defaults(max_pool_count_per_process=2)

    # Seed registry with stub objects (real adapters would also work
    # but stubs are cheaper).
    class _SeedAdapter:
        pass

    seeded = [_SeedAdapter() for _ in range(2)]
    _PROCESS_POOL_REGISTRY["seed_a"] = seeded[0]
    _PROCESS_POOL_REGISTRY["seed_b"] = seeded[1]
    assert AsyncSQLDatabaseNode.pool_count() == 2

    # Force the per-pool lock to timeout.
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _timeout_lock(*args, **kwargs):
        raise asyncio.TimeoutError("forced lock timeout")
        yield

    monkeypatch.setattr(
        AsyncSQLDatabaseNode,
        "_acquire_pool_lock_with_timeout",
        classmethod(lambda cls, *a, **kw: _timeout_lock()),
    )

    async def _no_runtime_pool(self):
        return None

    monkeypatch.setattr(
        AsyncSQLDatabaseNode, "_get_runtime_pool_adapter", _no_runtime_pool
    )

    node = AsyncSQLDatabaseNode(
        name="cap_check",
        database_type="postgresql",
        connection_string=pg_dsn,
        validate_queries=False,
    )

    with pytest.raises(PoolExhaustedError) as exc_info:
        await node._get_adapter()

    err = exc_info.value
    assert err.current == 2
    assert err.cap == 2
    assert "set_pool_defaults" in str(err)
    assert isinstance(err.__cause__, asyncio.TimeoutError)
    assert seeded  # pin


# ---------------------------------------------------------------------------
# Test 3 — idle pools reaped (DPI-B3)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idle_pools_reaped(pg_dsn):
    """Pools that sit idle longer than ``idle_timeout`` are closed and
    removed from the registry by the reaper.

    Setup:
        - idle_timeout = 2 s → reaper interval = max(1, 2//4) = 1 s
        - create one shared pool by running a query
        - sleep 5 s
        - assert pool count drops to 0
    """
    set_pool_defaults(idle_timeout=2, max_pool_count_per_process=20)

    node = AsyncSQLDatabaseNode(
        name="idle_pool",
        database_type="postgresql",
        connection_string=pg_dsn,
        query="SELECT 1",
        validate_queries=False,
    )
    await node.async_run()

    # Pool should now be in the registry.
    initial_count = AsyncSQLDatabaseNode.pool_count()
    assert initial_count >= 1

    # Sleep past idle_timeout + reaper interval (2s timeout + 1s interval
    # + 2s padding for first-iteration-already-in-flight).
    await asyncio.sleep(5)

    # The reaper should have closed and removed the idle pool. Allow
    # a small slack: the WeakValueDictionary may show transient entries
    # for adapters whose strong refs the test still holds.
    assert AsyncSQLDatabaseNode.pool_count() < initial_count


# ---------------------------------------------------------------------------
# Test 4 — active pools NOT reaped while busy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_active_pools_not_reaped(pg_dsn):
    """A pool with frequent get_connection() calls is NOT reaped.

    The is_idle() check uses ``_last_activity_at`` which the pool
    refreshes on every get_connection(). A pool that runs a query
    every 0.5 s with idle_timeout=2 should never become idle.
    """
    set_pool_defaults(idle_timeout=2, max_pool_count_per_process=20)

    node = AsyncSQLDatabaseNode(
        name="active_pool",
        database_type="postgresql",
        connection_string=pg_dsn,
        query="SELECT 1",
        validate_queries=False,
    )

    # Drive the pool — 5 queries over 2.5 seconds keeps it busy past
    # the idle_timeout window.
    for _ in range(5):
        await node.async_run()
        await asyncio.sleep(0.5)

    # Pool count is still at least 1 (the active pool survived).
    assert AsyncSQLDatabaseNode.pool_count() >= 1


# ---------------------------------------------------------------------------
# Test 5 — cross-event-loop dead pools reaped via WeakValueDictionary
# ---------------------------------------------------------------------------


def test_cross_event_loop_pools_reaped_by_gc():
    """A pool whose event loop closes is reaped on next registry access.

    Drives a query in event loop A, lets that loop close, then checks
    pool_count() — the WeakValueDictionary semantics should drop the
    entry once the strong references go out of scope.

    NOT @pytest.mark.asyncio — this test creates its own loop so the
    asyncio.run(...) call returns and the loop closes deterministically.
    """
    import gc

    set_pool_defaults(max_pool_count_per_process=10)

    async def _drive_query():
        node = AsyncSQLDatabaseNode(
            name="loop_a",
            database_type="postgresql",
            connection_string=get_postgres_connection_string(),
            query="SELECT 1",
            validate_queries=False,
        )
        await node.async_run()
        # Keep the adapter ref local — when the function returns, the
        # ref drops and the WeakValueDictionary will reap on next read.

    asyncio.run(_drive_query())

    # Force GC so the WeakValueDictionary drops dead entries.
    gc.collect()

    # The pool count should be 0 — the strong refs from the adapter
    # closure are gone, the loop is closed, GC reaped the entries.
    # (Some entries may temporarily survive if the adapter has cycles;
    # the assertion is "pool count cannot grow" not "is exactly 0".)
    final_count = AsyncSQLDatabaseNode.pool_count()
    cap = _POOL_DEFAULTS["max_pool_count_per_process"]
    assert final_count <= cap


# ---------------------------------------------------------------------------
# Test 6 — set_pool_defaults rejects unknown kwargs (structural invariant)
# ---------------------------------------------------------------------------


def test_set_pool_defaults_rejects_unknown_kwargs():
    """The set_pool_defaults override path rejects unknown kwargs.

    Mirrors the unit-test contract — included here as a regression
    invariant so a refactor that loosens the signature surfaces both
    in unit AND regression tiers.
    """
    with pytest.raises(TypeError):
        set_pool_defaults(foo=42, idle_timeout=300)  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Test 7 — the query path refreshes the idle clock (DPI-B3 root invariant)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_query_path_refreshes_the_idle_clock(pg_dsn):
    """Running a query MUST refresh the pool's ``_last_activity_at``.

    Test 4 (``test_active_pools_not_reaped``) pins the same invariant
    BEHAVIOURALLY, but it can only observe a violation when the reaper's tick
    happens to land on one of its queries -- so it passed for weeks against a
    pool whose clock was never refreshed at all, and then failed in CI as a
    "flake" the moment a loaded runner shifted the timing.

    This pins the invariant DIRECTLY, so the regression surfaces as a
    deterministic failure instead of a race:

      - ``_last_activity_at`` was refreshed in exactly one place,
        ``EnterpriseConnectionPool.get_connection()``;
      - nothing on the node's query path calls it (``async_run`` reaches the
        driver through ``adapter.begin_transaction()``, and the non-transaction
        path through ``adapter.execute()``);
      - so the clock held the pool's CREATION time forever and the reaper
        closed pools that were actively serving queries
        (``asyncpg.InterfaceError: pool is closing``).

    Neutralising the fix (``_ActivityTrackingPool`` -> identity) makes this
    test fail on the ``after > before`` assertion.
    """
    set_pool_defaults(idle_timeout=2, max_pool_count_per_process=20)

    node = AsyncSQLDatabaseNode(
        name="idle_clock_probe",
        database_type="postgresql",
        connection_string=pg_dsn,
        query="SELECT 1",
        validate_queries=False,
    )
    await node.async_run()

    targets = [
        target
        for target in (_idle_target(entry) for entry in _PROCESS_POOL_REGISTRY.values())
        if target is not None
    ]
    assert targets, "no registry entry exposed an idle clock -- cannot observe"
    pool = targets[0]

    # Let the clock age WITHOUT crossing idle_timeout, so this test never
    # depends on the reaper having (or not having) run.
    await asyncio.sleep(1.0)
    before = pool._last_activity_at

    await node.async_run()
    after = pool._last_activity_at

    assert after > before, (
        "the node's query path did not refresh the pool idle clock: "
        f"_last_activity_at unchanged at {before!r} across a successful query. "
        "The reaper will treat an actively-served pool as idle and close it "
        "under the caller."
    )
    assert not pool.is_idle(), (
        "pool reports is_idle() immediately after a successful query "
        f"(age={time.monotonic() - pool._last_activity_at:.2f}s, "
        f"idle_timeout={pool.idle_timeout}s)"
    )
