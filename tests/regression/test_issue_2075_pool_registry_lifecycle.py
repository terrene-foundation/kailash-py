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
    dispose_pool_sync,
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


def test_driver_terminate_is_actually_called_on_a_dead_loop_pool():
    """The ``terminate()`` branch — the whole PostgreSQL/MySQL fix — executes.

    Every other test here is SQLite-backed, and a file-backed SQLite adapter
    holds NO driver handle between queries, so none of them can reach
    ``_terminate_driver_handle_sync``'s ``terminate()`` call: they would all
    pass identically if that function were ``return False``. asyncpg and
    aiomysql both expose a synchronous ``terminate()``, and before #2211 a GC'd
    PostgreSQL/MySQL node released nothing at all — this is the instrument for
    that claim, with a stub standing in for the driver pool so no server is
    needed.
    """
    calls = []

    class _FakeDriverPool:
        """Minimal asyncpg/aiomysql shape: a synchronous ``terminate()``."""

        def terminate(self):
            calls.append("terminate")

    class _FakeAdapter:
        def __init__(self):
            self._pool = _FakeDriverPool()
            self._enterprise_pool = None
            self._connection = None

    adapter = _FakeAdapter()
    # No _POOL_LOOP_ATTR stamp -> unregistered owner -> the guard lets it past,
    # which is the documented contract for a bare/unregistered owner.
    assert dispose_pool_sync(adapter, label="fake pg pool") is True

    assert calls == ["terminate"], (
        f"driver terminate() was not called (calls={calls}); the "
        "PostgreSQL/MySQL half of the #2211 fix never runs"
    )
    assert adapter._pool is None, "the terminated handle was not claimed/cleared"


def test_a_driver_whose_terminate_raises_is_reported_not_swallowed(caplog):
    """A failed force-close is logged at WARNING, never silently absorbed.

    There is no recovery past this point — the loop that owned the handle is
    gone — so the only correct disposition is to surface it. zero-tolerance
    Rule 3: teardown may continue, but not silently.
    """

    class _ExplodingPool:
        def terminate(self):
            raise RuntimeError("Event loop is closed")

    class _FakeAdapter:
        def __init__(self):
            self._pool = _ExplodingPool()
            self._enterprise_pool = None
            self._connection = None

    with caplog.at_level("WARNING", logger="kailash.nodes.data.async_sql"):
        dispose_pool_sync(_FakeAdapter(), label="exploding pool")

    assert any(
        "pool_sync_terminate_failed" in r.getMessage() for r in caplog.records
    ), f"terminate() failure was not logged; records={[r.getMessage() for r in caplog.records]}"


@pytest.mark.asyncio
async def test_slot_is_freed_when_disposal_STARTS_not_when_it_SUCCEEDS(tmp_path):
    """Known trade-off, pinned: the count is "released", not "socket closed".

    ``_disposal_barrier`` frees the slot on ENTRY, before the driver close is
    awaited, so a close that times out leaves the slot freed while the pool may
    still be open. That is deliberate — a slot held for a five-second close is
    a slot the cap wrongly denies to a caller that needs one now — but it
    inverts #2075's failure direction from over-count to under-count, and an
    undocumented, untested trade-off is indistinguishable from an oversight.

    The boundary measured here is precise, and is NOT "any failed close frees
    the slot": disposal must actually REACH the barrier. A disconnect that
    raises before claiming its pool handle leaves the slot in place, which is
    the safe direction — the second half of this test pins that too.
    """
    # Half 1: the close STARTS (barrier entered) and then times out.
    node = _sqlite_node(tmp_path, "slow_close")
    await node.async_run(query="SELECT 1", result_format="dict")
    adapter = node._adapter
    before = AsyncSQLDatabaseNode.pool_count()
    assert before >= 1

    async def _never_finishes():
        await asyncio.sleep(3600)

    # Hang the DRIVER close, not disconnect() itself, so the adapter still
    # claims its handle and enters the disposal barrier.
    enterprise = getattr(adapter, "_enterprise_pool", None)
    assert enterprise is not None, "expected a Production* adapter here"
    enterprise.close = _never_finishes  # type: ignore[method-assign]

    await node.cleanup()  # bounded at 1.0s internally, then gives up

    assert AsyncSQLDatabaseNode.pool_count() == before - 1, (
        "slot was NOT freed on a close that started and then timed out — if "
        "this flips, the entry-time release in _disposal_barrier changed and "
        "the docstring trade-off needs rewriting, not the test"
    )

    # Half 2: the close never starts — the slot MUST stay (fail-safe direction).
    other = _sqlite_node(tmp_path, "never_starts")
    await other.async_run(query="SELECT 1", result_format="dict")
    other_adapter = other._adapter
    count = AsyncSQLDatabaseNode.pool_count()

    async def _raises_immediately():
        raise RuntimeError("driver refused before claiming the handle")

    other_adapter.disconnect = _raises_immediately  # type: ignore[method-assign]
    await other.cleanup()

    assert AsyncSQLDatabaseNode.pool_count() == count, (
        "a disconnect that never reached the disposal barrier freed the slot "
        "anyway — that is the under-count direction with no release behind it"
    )


@pytest.mark.asyncio
async def test_runtime_borrowed_adapter_is_flagged_by_get_adapter(
    tmp_path, monkeypatch
):
    """``_pool_is_borrowed`` is SET by the runtime path, not just honoured.

    The sibling test proves ``dispose_sync()`` respects the flag, but would
    stay green if ``_get_adapter`` never set it — which is the whole defect.
    This drives the runtime-pool branch and asserts the stamp.
    """
    node = _sqlite_node(tmp_path, "runtime_borrowed")

    class _BorrowedAdapter:
        _pool = object()
        _enterprise_pool = None
        _connection = None

    borrowed = _BorrowedAdapter()

    async def _fake_runtime_adapter(self):
        return borrowed

    monkeypatch.setattr(
        AsyncSQLDatabaseNode, "_get_runtime_pool_adapter", _fake_runtime_adapter
    )

    adapter = await node._get_adapter()

    assert adapter is borrowed
    assert node._pool_is_borrowed is True, (
        "the runtime-coordinated branch of _get_adapter did not flag the "
        "adapter as borrowed; dispose_sync() would force-close the runtime's "
        "shared pool out from under its other holders"
    )
    assert node.dispose_sync() is False


@pytest.mark.asyncio
async def test_get_pool_metrics_does_not_kill_another_loops_live_pool(tmp_path):
    """POLE 2 at the module primitive: a read-only diagnostic stays read-only.

    ``get_pool_metrics()`` is a public classmethod that takes
    ``_get_pool_lock()``, whose cross-loop branch walks the CLASS-LEVEL
    ``_shared_pools`` dict — which legitimately holds adapters from several
    concurrently-live loops. The #2211 fix made that branch's previously-inert
    ``adapter._pool.close()`` into a real synchronous terminate, which turned
    a read-only diagnostic into a process-wide pool killer (caught in security
    review). ``dispose_pool_sync`` now refuses a live-loop owner on its own,
    so the guard cannot be forgotten by a future call site either.
    """
    node = _sqlite_node(tmp_path, "metrics_bystander")
    await node.async_run(query="SELECT 1", result_format="dict")
    adapter = node._adapter
    assert adapter is not None
    assert getattr(adapter, "_kailash_pool_loop", None) is asyncio.get_running_loop()
    count = AsyncSQLDatabaseNode.pool_count()

    # Force the cross-loop branch: make the cached lock claim a foreign loop id.
    AsyncSQLDatabaseNode._pool_lock = asyncio.Lock()
    AsyncSQLDatabaseNode._pool_lock_loop_id = -1

    await AsyncSQLDatabaseNode.get_pool_metrics()

    assert (
        AsyncSQLDatabaseNode.pool_count() == count
    ), "a read-only get_pool_metrics() call deregistered a live pool"
    result = await node.async_run(query="SELECT 5 AS v", result_format="dict")
    assert result["result"]["data"][0]["v"] == 5, (
        "get_pool_metrics() terminated a pool that was still serving queries — "
        "the kailash 2.65.0 regression, reached from a public diagnostic"
    )

    await node.cleanup()


def test_dispose_sync_refuses_a_BORROWED_pool_even_on_a_dead_loop(tmp_path):
    """POLE 2, the case a dead loop does not excuse: someone else's pool.

    On the runtime-coordinated path ``_create_adapter_with_runtime_pool``
    injects the runtime ConnectionPoolManager's pool as ``adapter._pool``.
    That pool is shared with other nodes and the runtime owns its lifetime, so
    a synchronous ``terminate()`` from this node — which ``__del__`` now
    reaches on every backend, not just SQLite — would abort a pool its other
    holders are still using. "Its loop is dead" is not a licence to close a
    pool this node does not own.
    """
    node = _sqlite_node(tmp_path, "borrowed")

    async def _attach():
        await node.async_run(query="SELECT 1", result_format="dict")

    asyncio.run(_attach())

    adapter = node._adapter
    assert adapter is not None
    assert node._pool_loop.is_closed()  # dead loop: the release WOULD proceed

    # Mark it borrowed, exactly as the runtime-pool branch of _get_adapter does.
    node._pool_is_borrowed = True

    assert node.dispose_sync() is False, "dispose_sync() force-closed a BORROWED pool"
    assert node._adapter is adapter, "a borrowed adapter was detached"

    # And it does release once the pool is this node's own again.
    node._pool_is_borrowed = False
    assert node.dispose_sync() is True
    assert node._adapter is None


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
