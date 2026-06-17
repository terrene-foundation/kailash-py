"""Regression: WorkflowConnectionPool diagnostic methods report HONEST metrics.

Defect (pre-fix): the pool's public diagnostic methods returned hardcoded
fabricated values alongside real ones:

  * ``get_pool_statistics()`` returned ``avg_query_time_ms = 50.0`` (a constant
    ``# TODO: Track actual query time``) and ``queue_depth = 0``
    (``# TODO: Track actual queue depth``).
  * ``_get_pool_status()`` returned ``avg_latency_ms = 0.0``
    (``# TODO: Track actual latency``) and a hardcoded
    ``capabilities = ["read", "write"]`` (``# TODO: Add actual capability
    detection``).

These fabricated constants were presented to callers (and the query router,
which uses ``avg_latency_ms`` for routing) as if they were measured signals.

Fix:

  * Query-execution time is now instrumented: ``ConnectionPoolMetrics`` tracks a
    bounded rolling window of real query times via ``record_query_time()``,
    called from the real ``_execute_query`` path. ``get_pool_statistics`` reports
    the real average; with no activity it reports ``0.0`` honestly (and a
    ``query_time_samples`` count distinguishes "no data" from "fast queries").
  * ``queue_depth`` reads the real pending-waiter count from the
    ``available_connections`` queue.
  * ``avg_latency_ms`` is derived from each connection's real execution stats,
    and OMITTED when the connection has run no queries (rather than emitting a
    fabricated ``0.0``).
  * The fabricated ``capabilities`` constant is OMITTED entirely (the query
    router supplies its own default).

All assertions below are BEHAVIORAL: they construct/drive a real pool and a
real ``ConnectionPoolMetrics`` through real activity, then assert the returned
values reflect that activity and are NOT the old fabricated constants.
"""

import pytest

from kailash.core.actors.connection_actor import QueryResult
from kailash.nodes.data.workflow_connection_pool import (
    ConnectionPoolMetrics,
    WorkflowConnectionPool,
)

# Old fabricated constants the fix removed — no returned metric may equal these
# AFTER real activity has occurred.
_FABRICATED_QUERY_TIME_MS = 50.0
_FABRICATED_LATENCY_MS = 0.0


def _make_pool(**overrides) -> WorkflowConnectionPool:
    """Construct a real pool instance (no live DB needed for diagnostics)."""
    cfg = dict(
        name="regression_pool",
        database_type="postgresql",
        host="localhost",
        database="testdb",
        user="u",
        password="p",
        min_connections=1,
        max_connections=4,
    )
    cfg.update(overrides)
    return WorkflowConnectionPool(**cfg)


class _FakeStats:
    """Minimal stand-in for ConnectionStats with real execution accounting."""

    def __init__(self):
        self.queries_executed = 0
        self.total_execution_time = 0.0
        self.health_score = 90.0
        self.last_used_at = None


class _FakeActor:
    def __init__(self, conn_id):
        self.id = conn_id
        self.stats = _FakeStats()


class _FakeConnection:
    """A ConnectionActor-shaped fake whose execute() returns a real QueryResult.

    It mirrors the real wrapper: ``.id``, ``.health_score``, ``.actor.stats``,
    and an awaitable ``execute()`` that returns a ``QueryResult`` carrying a
    real (caller-supplied) execution_time.
    """

    def __init__(self, conn_id, execution_time):
        self.id = conn_id
        self.actor = _FakeActor(conn_id)
        self._execution_time = execution_time

    @property
    def health_score(self):
        return self.actor.stats.health_score

    async def execute(self, query=None, params=None, fetch_mode="all"):
        # Record real execution accounting onto the connection's own stats,
        # exactly as the real actor does, so per-connection latency is honest.
        self.actor.stats.queries_executed += 1
        self.actor.stats.total_execution_time += self._execution_time
        return QueryResult(
            success=True, data=[], error=None, execution_time=self._execution_time
        )


# ---------------------------------------------------------------------------
# (a) avg_query_time_ms reflects real timing (or the key/value is honest 0.0)
# ---------------------------------------------------------------------------


@pytest.mark.regression
def test_metrics_record_query_time_drives_real_avg():
    """ConnectionPoolMetrics computes a REAL avg/p99 from recorded query times."""
    metrics = ConnectionPoolMetrics("unit")

    # No activity yet -> honest zero, zero samples (NOT a fabricated constant).
    stats = metrics.get_stats()
    assert stats["performance"]["avg_query_time_ms"] == 0.0
    assert stats["performance"]["query_samples"] == 0

    # Record three real query times (seconds): 0.010, 0.020, 0.030 -> avg 0.020s.
    for seconds in (0.010, 0.020, 0.030):
        metrics.record_query_time(seconds)

    stats = metrics.get_stats()
    perf = stats["performance"]
    assert perf["query_samples"] == 3
    # avg = 20ms exactly; must reflect the real samples, never the old 50.0.
    assert perf["avg_query_time_ms"] == pytest.approx(20.0, abs=1e-6)
    assert perf["avg_query_time_ms"] != _FABRICATED_QUERY_TIME_MS
    assert perf["p99_query_time_ms"] == pytest.approx(30.0, abs=1e-6)


@pytest.mark.regression
def test_record_query_time_window_is_bounded():
    """The query-time window is bounded (mirrors acquisition_wait_times: 1000)."""
    metrics = ConnectionPoolMetrics("unit")
    for _ in range(1500):
        metrics.record_query_time(0.001)
    assert len(metrics.query_execution_times) == 1000


@pytest.mark.regression
async def test_get_pool_statistics_query_time_is_real_after_activity():
    """get_pool_statistics avg_query_time_ms reflects REAL executed query time."""
    pool = _make_pool()

    # Before any query: honest 0.0 (NOT the fabricated 50.0 constant), 0 samples.
    stats_before = await pool.get_pool_statistics()
    assert stats_before["avg_query_time_ms"] == 0.0
    assert stats_before["avg_query_time_ms"] != _FABRICATED_QUERY_TIME_MS
    assert stats_before["query_time_samples"] == 0

    # Drive the REAL _execute_query path (which calls record_query_time) with a
    # connection whose query takes a known 25ms.
    conn = _FakeConnection("conn_real", execution_time=0.025)
    pool.all_connections[conn.id] = conn
    pool.active_connections[conn.id] = conn

    result = await pool._execute_query({"connection_id": conn.id, "query": "SELECT 1"})
    assert result["success"] is True

    stats_after = await pool.get_pool_statistics()
    # The framework actually called record_query_time on the real path.
    assert stats_after["query_time_samples"] == 1
    assert stats_after["avg_query_time_ms"] == pytest.approx(25.0, abs=1e-6)
    # Crucially: NOT the old fabricated constant after real activity.
    assert stats_after["avg_query_time_ms"] != _FABRICATED_QUERY_TIME_MS


# ---------------------------------------------------------------------------
# (b) No returned metric equals the old fabricated constants after real activity
# ---------------------------------------------------------------------------


@pytest.mark.regression
async def test_no_fabricated_constants_after_real_activity():
    """After real query activity, diagnostics carry honest values only."""
    pool = _make_pool()

    conn = _FakeConnection("conn_a", execution_time=0.040)  # 40ms, != 50ms, != 0
    pool.all_connections[conn.id] = conn
    pool.active_connections[conn.id] = conn
    await pool._execute_query({"connection_id": conn.id, "query": "SELECT 1"})

    # get_pool_statistics: query time is the real 40ms, never the fabricated 50.0
    stats = await pool.get_pool_statistics()
    assert stats["avg_query_time_ms"] == pytest.approx(40.0, abs=1e-6)
    assert stats["avg_query_time_ms"] != _FABRICATED_QUERY_TIME_MS

    # _get_pool_status: avg_latency_ms is the real 40ms, never the fabricated 0.0
    status = await pool._get_pool_status()
    conn_info = status["connections"][conn.id]
    assert "avg_latency_ms" in conn_info
    assert conn_info["avg_latency_ms"] == pytest.approx(40.0, abs=1e-6)
    assert conn_info["avg_latency_ms"] != _FABRICATED_LATENCY_MS


@pytest.mark.regression
async def test_get_pool_status_omits_latency_with_no_queries_no_fabricated_zero():
    """A connection with no queries OMITS avg_latency_ms (no fabricated 0.0)."""
    pool = _make_pool()

    conn = _FakeConnection("conn_idle", execution_time=0.0)  # never executed
    pool.all_connections[conn.id] = conn

    status = await pool._get_pool_status()
    conn_info = status["connections"][conn.id]
    # Honest omission: the consumer (query router) applies its own default
    # rather than reading a fabricated 0.0 latency that would skew routing.
    assert "avg_latency_ms" not in conn_info


@pytest.mark.regression
async def test_get_pool_status_omits_fabricated_capabilities_constant():
    """The fabricated ['read','write'] capabilities constant is gone."""
    pool = _make_pool()

    conn = _FakeConnection("conn_c", execution_time=0.005)
    pool.all_connections[conn.id] = conn

    status = await pool._get_pool_status()
    conn_info = status["connections"][conn.id]
    # No fabricated capability list — the router defaults when absent.
    assert "capabilities" not in conn_info


# ---------------------------------------------------------------------------
# (c) queue_depth reflects real waiter state
# ---------------------------------------------------------------------------


@pytest.mark.regression
async def test_queue_depth_reflects_real_pending_waiters():
    """queue_depth counts REAL consumers blocked waiting for a connection."""
    import asyncio

    pool = _make_pool()

    # No waiters initially -> real zero (not a TODO placeholder).
    stats = await pool.get_pool_statistics()
    assert stats["queue_depth"] == 0

    # Park two real coroutines blocked in available_connections.get().
    getter_tasks = [
        asyncio.ensure_future(pool.available_connections.get()) for _ in range(2)
    ]
    # Yield so the getters actually register as pending waiters on the queue.
    await asyncio.sleep(0)

    stats_waiting = await pool.get_pool_statistics()
    assert stats_waiting["queue_depth"] == 2

    # Releasing connections wakes the waiters; depth returns to real zero.
    await pool.available_connections.put(object())
    await pool.available_connections.put(object())
    await asyncio.gather(*getter_tasks)
    await asyncio.sleep(0)

    stats_done = await pool.get_pool_statistics()
    assert stats_done["queue_depth"] == 0
