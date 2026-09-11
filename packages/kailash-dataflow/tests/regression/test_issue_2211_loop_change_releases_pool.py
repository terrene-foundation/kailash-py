"""Issue #2211 — a node displaced by an event-loop change must be released.

``DataFlow._get_or_create_async_sql_node`` caches one ``AsyncSQLDatabaseNode``
per ``database_type`` and rebuilds it when the event loop changes. It used to
overwrite the cache entry without closing the outgoing node, which still owned
a live connection pool. The displaced node is no longer in the cache, so
``DataFlow.close()`` can never reach it either: every loop change leaked one
more pool for the life of the process.

Measured against the unfixed tree, three ``asyncio.run()`` calls on one
DataFlow instance: two displaced nodes, zero teardown calls,
``AsyncSQLDatabaseNode.pool_count()`` == 3. Twelve calls: ``pool_count()``
== 12, against a configured cap of 5.

Assertions count POOLS. Both poles are covered:
  * release — a node displaced from a CLOSED loop is released immediately;
  * no over-close — a node displaced while its loop is STILL ALIVE is NOT
    force-closed (that would abort connections under a concurrent caller, the
    regression kailash 2.65.0 fixed) and is instead drained by close_async().

SQLite-backed: no Docker, no network. The eviction path is database-agnostic.
"""

import asyncio

import pytest

from dataflow import DataFlow
from kailash.nodes.data.async_sql import (
    _POOL_DEFAULTS,
    AsyncSQLDatabaseNode,
    set_pool_defaults,
)

pytestmark = [pytest.mark.regression, pytest.mark.unit]


@pytest.fixture
def restore_pool_defaults():
    saved = dict(_POOL_DEFAULTS)
    yield
    set_pool_defaults(**{k: v for k, v in saved.items()})


def _make_db(tmp_path, name: str):
    db = DataFlow(f"sqlite:///{tmp_path / (name + '.db')}", auto_migrate=True)

    @db.model
    class Issue2211Widget:
        id: str
        name: str

    return db


def test_loop_change_releases_the_displaced_node_pool(tmp_path, restore_pool_defaults):
    """Churning loops on ONE DataFlow instance must not accumulate pools.

    Synchronous on purpose: each ``asyncio.run()`` creates a loop, uses it and
    CLOSES it, which is the loop-change the eviction branch sees in
    pytest-asyncio and in any sync caller driving async work.
    """
    set_pool_defaults(max_pool_count_per_process=5, idle_timeout=300)
    baseline = AsyncSQLDatabaseNode.pool_count()

    db = _make_db(tmp_path, "loop_churn")
    seen_nodes = []
    counts = []

    async def _one(i: int) -> None:
        await db.express.create("Issue2211Widget", {"id": f"w{i}", "name": "x"})

    for i in range(8):
        asyncio.run(_one(i))
        entry = db._async_sql_node_cache.get("sqlite")
        assert entry is not None
        seen_nodes.append(entry[0])
        counts.append(AsyncSQLDatabaseNode.pool_count())

    # The premise: the loop really did change, so nodes really were displaced.
    distinct = {id(n) for n in seen_nodes}
    assert len(distinct) > 1, (
        "no node was displaced — this test's premise did not hold, so its "
        "green says nothing about #2211"
    )

    assert max(counts) <= baseline + 1, (
        f"pool_count() per iteration was {counts} (baseline {baseline}). Each "
        "displaced node kept its pool and its registry slot — one leak per "
        "event-loop change, which is #2211."
    )

    # Every displaced node released its adapter; only the live one holds a pool.
    live = db._async_sql_node_cache["sqlite"][0]
    for node in seen_nodes:
        if node is live:
            continue
        assert node._adapter is None, (
            f"displaced node {node.id} still holds an adapter — its pool and "
            "its sockets were never released"
        )
        assert node._connected is False

    db.close()
    assert AsyncSQLDatabaseNode.pool_count() == baseline


def test_cap_holds_across_many_loop_changes(tmp_path, restore_pool_defaults):
    """``max_pool_count_per_process`` is a bound, and loop churn must respect it.

    This is #2075's assertion driven by #2211's mechanism: before the fix the
    count rose monotonically with the number of loops, straight through the cap.
    """
    set_pool_defaults(max_pool_count_per_process=3, idle_timeout=300)
    baseline = AsyncSQLDatabaseNode.pool_count()

    db = _make_db(tmp_path, "cap_churn")

    async def _one(i: int) -> None:
        await db.express.create("Issue2211Widget", {"id": f"c{i}", "name": "x"})

    peak = baseline
    for i in range(12):
        asyncio.run(_one(i))
        peak = max(peak, AsyncSQLDatabaseNode.pool_count())

    assert peak <= baseline + 3, (
        f"peak pool_count()={peak} against a cap of 3 (baseline {baseline}) "
        "after 12 event-loop changes"
    )
    db.close()


@pytest.mark.asyncio
async def test_displaced_node_on_a_LIVE_loop_is_parked_not_force_closed(
    tmp_path, restore_pool_defaults
):
    """POLE 2: a pool whose loop is still alive keeps serving queries.

    Without this, a "fix" that force-closed every displaced node would pass
    every other test in this file and re-introduce the bug kailash 2.65.0
    fixed: a pool torn down underneath the caller that was using it.
    """
    set_pool_defaults(max_pool_count_per_process=5, idle_timeout=300)
    db = _make_db(tmp_path, "live_loop")

    await db.express.create("Issue2211Widget", {"id": "live1", "name": "x"})
    node = db._async_sql_node_cache["sqlite"][0]
    adapter = node._adapter
    assert adapter is not None
    assert node._pool_loop is asyncio.get_running_loop()

    count_before = AsyncSQLDatabaseNode.pool_count()

    # Displace it while its loop is the one we are running on.
    db._release_displaced_async_sql_node(node)

    assert (
        node in db._displaced_async_sql_nodes
    ), "a node displaced on a LIVE loop was not parked for close()"
    assert node._adapter is adapter, (
        "a node displaced on a LIVE loop had its adapter torn off — this is "
        "the kailash 2.65.0 'pool closed under its caller' regression"
    )
    assert AsyncSQLDatabaseNode.pool_count() == count_before

    # And it still works: the pool was not closed under us.
    result = await node.async_run(query="SELECT 4 AS v", result_format="dict")
    assert result["result"]["data"][0]["v"] == 4

    # close_async() is what finally drains the park.
    await db.close_async()
    assert db._displaced_async_sql_nodes == []
    assert node._adapter is None


def test_the_park_is_swept_once_a_parked_nodes_loop_dies(
    tmp_path, restore_pool_defaults
):
    """The live-loop park must not become a leak of its own.

    Deferring a live-loop node to ``close()`` is correct, but a server that
    creates one event loop per request would park one node per request and
    hold every one of them until the DataFlow instance closed — trading a pool
    leak for a node leak. Each eviction therefore re-checks the park and
    releases whatever has since become releasable.
    """
    set_pool_defaults(max_pool_count_per_process=5, idle_timeout=300)
    db = _make_db(tmp_path, "park_sweep")
    parked = {}

    async def _park_on_a_live_loop():
        await db.express.create("Issue2211Widget", {"id": "p1", "name": "x"})
        node = db._async_sql_node_cache["sqlite"][0]
        db._release_displaced_async_sql_node(node)
        # Refused while this loop is alive — that is the premise being set up.
        assert node in db._displaced_async_sql_nodes
        assert node._adapter is not None
        parked["node"] = node

    asyncio.run(_park_on_a_live_loop())  # loop dies here
    node = parked["node"]
    assert node._pool_loop.is_closed()
    assert db._displaced_async_sql_nodes == [node]

    # Any later eviction sweeps the park.
    db._release_displaced_async_sql_node(None)

    assert db._displaced_async_sql_nodes == [], (
        "a parked node whose loop has since closed was not released — the "
        "park grows one entry per loop for the life of the DataFlow instance"
    )
    assert node._adapter is None
    db.close()


@pytest.mark.asyncio
async def test_clear_async_sql_node_cache_releases_instead_of_dropping(
    tmp_path, restore_pool_defaults
):
    """The explicit cache-clear API is the same eviction, and must also release.

    ``clear_async_sql_node_cache()`` dropped the last reference to nodes that
    still owned live pools — the same never-closed-on-eviction shape as the
    loop-change branch, reached by an API users are told to call in tests.
    """
    set_pool_defaults(max_pool_count_per_process=5, idle_timeout=300)
    db = _make_db(tmp_path, "explicit_clear")

    await db.express.create("Issue2211Widget", {"id": "e1", "name": "x"})
    node = db._async_sql_node_cache["sqlite"][0]
    assert node._adapter is not None

    db.clear_async_sql_node_cache()

    assert db._async_sql_node_cache == {}
    # Loop is alive, so the node is parked rather than force-closed (POLE 2)...
    assert node in db._displaced_async_sql_nodes
    assert node._adapter is not None
    # ...and close_async() releases it (POLE 1).
    await db.close_async()
    assert node._adapter is None
    assert db._displaced_async_sql_nodes == []
