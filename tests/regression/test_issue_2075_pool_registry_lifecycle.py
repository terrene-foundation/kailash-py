"""Issue #2075 — ``pool_count()`` must count POOLS, not adapter objects.

``_PROCESS_POOL_REGISTRY`` is a ``WeakValueDictionary``, so before the fix the
only thing that freed a slot was garbage collection of the adapter OBJECT.
That made ``AsyncSQLDatabaseNode.pool_count()`` — the instrument
``max_pool_count_per_process`` is enforced with — report pools that had
already been closed, for as long as anything still referenced their adapter.
#2075 observed ``pool_count() == 9`` against a configured cap of 5 after ten
DataFlow instances had each been closed.

Every assertion here counts POOLS. "No exception was raised" cannot tell a
closed pool from a leaked one, so it is never the assertion.

Both poles are asserted:
  * release  — a closed pool frees its slot even while its adapter is alive;
  * no over-close — a pool that is still live keeps its slot and keeps
    serving queries. Without that second pole a fix that simply emptied the
    registry would pass, and that is the #2218 / kailash 2.65.0 regression
    (reaping a pool out from under its caller) wearing a different hat.

SQLite-backed: no Docker, no network, runs in every environment. The registry
under test is database-agnostic.
"""

import asyncio
import gc

import pytest

from kailash.nodes.data.async_sql import (
    _POOL_DEFAULTS,
    AsyncSQLDatabaseNode,
    set_pool_defaults,
)

pytestmark = [pytest.mark.regression, pytest.mark.unit]


@pytest.fixture
def restore_pool_defaults():
    """Restore the process-wide pool defaults this module mutates."""
    saved = dict(_POOL_DEFAULTS)
    yield
    set_pool_defaults(**{k: v for k, v in saved.items()})


def _sqlite_node(tmp_path, name: str) -> AsyncSQLDatabaseNode:
    """A node with its OWN pool key, so each one occupies its own slot."""
    return AsyncSQLDatabaseNode(
        node_id=f"issue2075_{name}",
        connection_string=f"sqlite:///{tmp_path / (name + '.db')}",
        database_type="sqlite",
    )


@pytest.mark.asyncio
async def test_closed_pool_frees_its_registry_slot(tmp_path):
    """A pool that has been closed stops counting — while its adapter lives.

    The strong ``adapter`` reference held across ``cleanup()`` is the whole
    test. Drop it and the WeakValueDictionary clears the slot on its own, and
    the assertion passes against the BROKEN code too.
    """
    before = AsyncSQLDatabaseNode.pool_count()

    node = _sqlite_node(tmp_path, "closed_frees_slot")
    await node.async_run(query="SELECT 1", result_format="dict")

    adapter = node._adapter  # STRONG reference — held for the rest of the test
    assert adapter is not None
    assert AsyncSQLDatabaseNode.pool_count() == before + 1

    await node.cleanup()

    # The pool really is closed...
    assert getattr(adapter, "_pool", None) is None
    assert getattr(adapter, "_connection", None) is None
    # ...so it must not still be counted, even though `adapter` is alive.
    assert AsyncSQLDatabaseNode.pool_count() == before, (
        f"closed pool still counted: pool_count()="
        f"{AsyncSQLDatabaseNode.pool_count()}, expected {before}. The adapter "
        "object is deliberately still referenced here; a registry keyed on "
        "object lifetime rather than pool lifetime is exactly #2075."
    )
    assert adapter is not None  # keep the reference alive to the very end


@pytest.mark.asyncio
async def test_cap_is_not_consumed_by_already_closed_pools(
    tmp_path, restore_pool_defaults
):
    """Open/close N pools with N > cap: the cap is never breached.

    This is #2075's assertion in its general form. Every adapter is retained
    in ``kept`` so nothing can be attributed to garbage collection timing.
    """
    set_pool_defaults(max_pool_count_per_process=3, idle_timeout=300)
    before = AsyncSQLDatabaseNode.pool_count()

    kept = []
    peak = before
    for i in range(8):
        node = _sqlite_node(tmp_path, f"cap_{i}")
        await node.async_run(query="SELECT 1", result_format="dict")
        kept.append(node._adapter)
        peak = max(peak, AsyncSQLDatabaseNode.pool_count())
        await node.cleanup()

    assert len(kept) == 8 and all(a is not None for a in kept)
    assert AsyncSQLDatabaseNode.pool_count() == before, (
        f"pool_count()={AsyncSQLDatabaseNode.pool_count()} after closing all 8 "
        f"pools (expected {before}); 8 closed pools are holding registry slots"
    )
    assert peak <= before + 3, (
        f"peak pool_count()={peak} exceeded the configured cap of 3 "
        f"(baseline {before}) — the bound in max_pool_count_per_process is a "
        "bound, not a hint (#2075)"
    )


@pytest.mark.asyncio
async def test_live_pool_keeps_its_slot_and_keeps_serving(tmp_path):
    """POLE 2: closing one pool must not deregister or disturb another.

    A fix that cleared the registry wholesale, or that force-closed every
    adapter it could reach, would satisfy the two tests above and re-introduce
    the bug kailash 2.65.0 fixed — a pool closed underneath the caller that
    was using it. This asserts the live pool both still COUNTS and still
    WORKS after its neighbour is torn down.
    """
    before = AsyncSQLDatabaseNode.pool_count()

    live = _sqlite_node(tmp_path, "live")
    doomed = _sqlite_node(tmp_path, "doomed")
    await live.async_run(query="SELECT 1", result_format="dict")
    await doomed.async_run(query="SELECT 1", result_format="dict")
    assert AsyncSQLDatabaseNode.pool_count() == before + 2

    await doomed.cleanup()

    assert AsyncSQLDatabaseNode.pool_count() == before + 1, (
        "closing one pool deregistered more than one — a registry sweep that "
        "frees slots it does not own is as wrong as one that frees none"
    )
    assert live._adapter is not None, "live node lost its adapter"
    result = await live.async_run(query="SELECT 2 AS v", result_format="dict")
    assert (
        result["result"]["data"][0]["v"] == 2
    ), "the live pool stopped serving queries after an unrelated pool closed"

    await live.cleanup()
    assert AsyncSQLDatabaseNode.pool_count() == before


@pytest.mark.asyncio
async def test_dispose_sync_refuses_while_the_pool_loop_is_live(tmp_path):
    """POLE 2 at the primitive: ``dispose_sync()`` will not abort a live pool.

    ``dispose_sync()`` is the force-release used when a pool's event loop is
    already closed. Called while that loop is still running it MUST decline —
    otherwise the #2211 eviction fix becomes a way to abort connections under
    a concurrent caller.
    """
    node = _sqlite_node(tmp_path, "refuse")
    await node.async_run(query="SELECT 1", result_format="dict")
    adapter = node._adapter
    count = AsyncSQLDatabaseNode.pool_count()

    # We are inside the very loop the pool was attached on.
    assert node._pool_loop is asyncio.get_running_loop()
    assert node.dispose_sync() is False, "dispose_sync() disposed a LIVE pool"

    assert node._adapter is adapter, "dispose_sync() detached a live adapter"
    assert AsyncSQLDatabaseNode.pool_count() == count
    result = await node.async_run(query="SELECT 3 AS v", result_format="dict")
    assert result["result"]["data"][0]["v"] == 3

    await node.cleanup()


def test_dispose_sync_releases_a_pool_whose_loop_is_closed(tmp_path):
    """POLE 1 at the primitive: a dead-loop pool IS released, and stops counting.

    Deliberately synchronous: the loop that owned the pool must be closed
    before ``dispose_sync()`` is called, which is the situation the loop-change
    eviction in DataFlow finds itself in.

    The load-bearing assertion is ``pool_count()``, not the return value. A
    file-backed SQLite adapter holds no driver handle between queries, so
    nothing is terminated here — and the registry slot must be freed anyway.
    """
    before = AsyncSQLDatabaseNode.pool_count()
    node = _sqlite_node(tmp_path, "dead_loop")

    async def _attach():
        await node.async_run(query="SELECT 1", result_format="dict")

    asyncio.run(_attach())  # loop is created, used, and CLOSED

    adapter = node._adapter
    assert adapter is not None
    assert node._pool_loop is not None and node._pool_loop.is_closed()
    assert AsyncSQLDatabaseNode.pool_count() == before + 1

    assert node.dispose_sync() is True, "dispose_sync() refused a DEAD-loop pool"

    assert node._adapter is None
    assert node._connected is False
    assert AsyncSQLDatabaseNode.pool_count() == before, (
        f"pool_count()={AsyncSQLDatabaseNode.pool_count()} after disposing a "
        f"dead-loop pool (expected {before})"
    )
    assert adapter is not None  # the slot was freed without relying on GC
    gc.collect()
