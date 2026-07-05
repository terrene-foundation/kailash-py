# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression test for issue #1572 — bridge-loop pool leak.

DataFlow's sync->async bridge (``dataflow.core.async_utils`` — the
``async_safe_run`` / ``_run_in_thread_pool`` path) runs coroutines on a
*transient* event loop it creates, runs, and closes. When a coroutine on that
loop creates an aiomysql / asyncpg pool (an adapter reachability probe, or
``EnterpriseConnectionPool`` min-size connections), the pool's transports are
bound to the transient loop. Once the loop closes, those transports belong to
a dead loop and can never be drained — surfacing at GC time as
``RuntimeError: Event loop is closed`` + ``ResourceWarning: Unclosed
connection`` from the aiomysql / asyncpg finalizers, long after
``db.close_async()`` has (correctly) done everything it can.

The fix (``kailash.utils.loop_pool_registry`` + the bridge ``finally`` drain)
closes those pools while the transient loop is still alive.

Test strategy — two layers:

* **PRIMARY (deterministic).** Drive ``async_safe_run`` from WITHIN a running
  loop (forcing the thread-pool bridge branch), open a REAL adapter pool inside
  the driven coroutine (so it is created ON the transient bridge loop), and
  assert the pool was drained (``adapter._pool is None``) after
  ``async_safe_run`` returns. WITHOUT the fix the drain never runs and the pool
  object survives — a clean, timing-independent pass/fail. This is the path the
  root-cause diagnosis (issue #1572) identifies.
* **SECONDARY (symptom-path GC capture).** A full express CRUD + ``close_async``
  cycle, then a forced GC with warning + unraisable capture, asserting neither
  the ResourceWarning nor the "Event loop is closed" RuntimeError surfaces.

Per ``rules/testing.md`` § 3-Tier: NO MOCKING — real containers only:
* PostgreSQL — ``postgresql://test_user:test_password@localhost:5434/kailash_test``
* MySQL — ``mysql://kailash_test:test_password@localhost:3307/kailash_test``
  (container ``kailash_sdk_test_mysql``; MYSQL_USER=kailash_test, grant host '%').

TRAP (do NOT "fix" by adding a pytest flag): running with
``-W error::PytestUnraisableExceptionWarning`` turns the GC-time warning into a
mid-teardown error that cascades into a spurious "Record id=N not found". The
GC layer asserts on CAPTURED warnings/unraisables directly and MUST NOT be run
under that flag.
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import os
import sys
import warnings

import pytest

from dataflow import DataFlow

# The sync->async bridge under test.
from dataflow.core.async_utils import async_safe_run

# Core adapters whose connect() registers a bridge-loop pool drain (#1572).
from kailash.nodes.data.async_sql import (
    DatabaseConfig,
    DatabaseType,
    MySQLAdapter,
    PostgreSQLAdapter,
)

POSTGRES_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)
MYSQL_URL = os.getenv(
    "TEST_MYSQL_URL",
    # Container ``kailash_sdk_test_mysql`` provisions MYSQL_USER=kailash_test
    # (grant host '%'), NOT test_user; aiomysql uses these host/port/creds.
    "mysql://kailash_test:test_password@localhost:3307/kailash_test",
)


# ---------------------------------------------------------------------------
# PRIMARY — deterministic bridge-drain assertion
# ---------------------------------------------------------------------------


def _open_pool_on_bridge(adapter):
    """Coroutine factory: open the adapter's pool, then return.

    Run via ``async_safe_run`` from a running-loop context, this executes on
    the transient bridge loop. ``adapter.connect()`` creates the real pool
    (asyncpg min_size=1 / aiomysql minsize>=1 open connections eagerly) ON that
    bridge loop and registers ``adapter.disconnect`` for drain-before-close.
    """

    async def _coro():
        await adapter.connect()
        assert adapter._pool is not None  # pool really opened on the bridge loop
        return "opened"

    return _coro()


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_bridge_drain_disconnects_pool():
    """PG: a pool opened on the transient bridge loop is drained before close.

    Fails without the fix — the bridge never calls disconnect, so
    ``adapter._pool`` survives as a live pool bound to a now-dead loop.
    """
    assert (
        asyncio.get_running_loop().is_running()
    )  # async_safe_run -> thread-pool bridge
    adapter = PostgreSQLAdapter(
        DatabaseConfig(type=DatabaseType.POSTGRESQL, connection_string=POSTGRES_URL)
    )
    try:
        result = async_safe_run(_open_pool_on_bridge(adapter))
    except Exception as exc:  # pragma: no cover — infra-down skip
        pytest.skip(
            f"database at {POSTGRES_URL!r} not reachable ({exc}); this Tier-2 "
            f"test requires the real container to be up"
        )
    assert result == "opened"
    # The bridge drained the pool while its loop was still alive:
    assert adapter._pool is None, (
        "PostgreSQL pool created on the transient bridge loop was NOT drained "
        "before the loop closed (issue #1572 regression)"
    )


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mysql_bridge_drain_disconnects_pool():
    """MySQL: a pool opened on the transient bridge loop is drained before close."""
    assert (
        asyncio.get_running_loop().is_running()
    )  # async_safe_run -> thread-pool bridge
    adapter = MySQLAdapter(
        DatabaseConfig(type=DatabaseType.MYSQL, connection_string=MYSQL_URL)
    )
    try:
        result = async_safe_run(_open_pool_on_bridge(adapter))
    except Exception as exc:  # pragma: no cover — infra-down skip
        pytest.skip(
            f"database at {MYSQL_URL!r} not reachable ({exc}); this Tier-2 "
            f"test requires the real container to be up"
        )
    assert result == "opened"
    assert adapter._pool is None, (
        "MySQL pool created on the transient bridge loop was NOT drained before "
        "the loop closed (issue #1572 regression)"
    )


# ---------------------------------------------------------------------------
# SECONDARY — symptom-path GC capture over a full express lifecycle
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def _capture_gc_teardown_signals():
    """Capture ResourceWarnings AND unraisable exceptions during a GC sweep."""
    unraisables = []
    old_hook = sys.unraisablehook

    def _record_unraisable(unraisable):
        unraisables.append(unraisable)

    sys.unraisablehook = _record_unraisable
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            yield caught, unraisables
    finally:
        sys.unraisablehook = old_hook


def _resource_warning_hits(caught):
    return [
        str(w.message)
        for w in caught
        if issubclass(w.category, ResourceWarning) and "nclosed conn" in str(w.message)
    ]


def _event_loop_closed_hits(unraisables):
    hits = []
    for u in unraisables:
        exc = getattr(u, "exc_value", None)
        if isinstance(exc, RuntimeError) and "Event loop is closed" in str(exc):
            hits.append(str(exc))
    return hits


async def _express_lifecycle_gc_capture(database_url: str):
    """Full express CRUD + close_async, then GC-capture teardown signals."""
    try:
        db = DataFlow(database_url=database_url, auto_migrate=True)
    except Exception as exc:  # pragma: no cover — infra-down skip
        pytest.skip(
            f"database at {database_url!r} not reachable ({exc}); this Tier-2 "
            f"test requires the real container to be up"
        )

    @db.model
    class _Widget1572Sec:
        id: int
        name: str
        value: int

    await db.create_tables_async()
    created = await db.express.create(
        "_Widget1572Sec", {"id": 1, "name": "alice", "value": 1}
    )
    assert created is not None and created.get("id") == 1
    await db.express.update("_Widget1572Sec", 1, {"value": 2})
    await db.express.delete("_Widget1572Sec", 1)
    await db.close_async()

    del db
    del _Widget1572Sec

    with _capture_gc_teardown_signals() as (caught, unraisables):
        for _ in range(3):
            gc.collect()
            await asyncio.sleep(0)
        gc.collect()

    return _resource_warning_hits(caught), _event_loop_closed_hits(unraisables)


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_express_lifecycle_no_gc_warnings():
    """PG: full CRUD + close_async leaves no unclosed-connection / dead-loop signal."""
    rw_hits, loop_hits = await _express_lifecycle_gc_capture(POSTGRES_URL)
    assert rw_hits == [], f"PostgreSQL leaked unclosed connections at GC: {rw_hits}"
    assert (
        loop_hits == []
    ), f"PostgreSQL produced 'Event loop is closed' at GC: {loop_hits}"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_mysql_express_lifecycle_no_gc_warnings():
    """MySQL: full CRUD + close_async leaves no unclosed-connection / dead-loop signal."""
    rw_hits, loop_hits = await _express_lifecycle_gc_capture(MYSQL_URL)
    assert rw_hits == [], f"MySQL leaked unclosed connections at GC: {rw_hits}"
    assert loop_hits == [], f"MySQL produced 'Event loop is closed' at GC: {loop_hits}"
