# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 regression test for issue #1575 — transient-loop pool leak (sibling of #1572).

#1572 fixed the sync->async *bridge* (``dataflow.core.async_utils``) so a pool
created on a transient bridge loop is drained before the loop closes. #1575 is
the SIBLING gap: transient / owned loops OUTSIDE the bridge that also create
adapter pools and leak them the same way.

The load-bearing anchor is ``DataFlowEngine._inspect_database_schema_real``
(reached from the sync ``discover_schema``). It opens a real asyncpg /
aiosqlite adapter, walks the catalog, and closes the adapter — but pre-fix the
close was OUTSIDE any ``try/finally``, so a mid-discovery exception jumped over
it and leaked the connection pool on a (possibly transient) loop that then
closed -> ``RuntimeError: Event loop is closed`` + ``ResourceWarning: Unclosed
connection`` at GC.

The fix wraps the adapter close in ``try/finally`` (both the PostgreSQL and the
SQLite branch) AND routes the transient ``asyncio.run`` / ``new_event_loop``
sites (``discover_schema``, ``validate_schema``, ``current_schema`` fallback,
and the model-registry workflow bridge) through ``async_safe_run``, which
stamps the transient loop with ``BRIDGE_LOOP_ATTR`` so any pool created on it
drains before close.

Test strategy:

* **PRIMARY (deterministic, the exception path AC#4).** A protocol-satisfying
  adapter subclass (NOT a mock — it opens a REAL pool via
  ``super().create_connection_pool()`` against the real container, then raises a
  non-connection error mid-discovery) records whether ``close_connection_pool``
  ran. WITHOUT the ``finally`` the close never runs and the pool survives; WITH
  it the close runs on the exception path. Clean, timing-independent pass/fail.
* **SUCCESS path.** The same adapter without an injected failure still drains
  its pool on the happy path (guards against a refactor deleting the close).
* **SYMPTOM-path GC capture.** The sync ``discover_schema(use_real_inspection=True)``
  full cycle, then a forced GC, asserting neither the ResourceWarning nor the
  "Event loop is closed" RuntimeError surfaces.

Per ``rules/testing.md`` § 3-Tier: NO MOCKING — real containers only:
* PostgreSQL — ``postgresql://test_user:test_password@localhost:5434/kailash_test``

The adapter subclasses here are the ``rules/testing.md`` § "Protocol-Satisfying
Deterministic Adapters" carve-out: real adapters (real pool, real driver) with
one deterministic overridden method — NOT ``unittest.mock`` / ``MagicMock``.
"""

from __future__ import annotations

import asyncio
import contextlib
import gc
import os
import sys
import tempfile
import warnings

import pytest

from dataflow import DataFlow
from dataflow.adapters.postgresql import PostgreSQLAdapter
from dataflow.adapters.sqlite import SQLiteAdapter

POSTGRES_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


# ---------------------------------------------------------------------------
# Protocol-satisfying deterministic adapters (real pool + injected failure)
# ---------------------------------------------------------------------------


class _FailMidDiscoveryPGAdapter(PostgreSQLAdapter):
    """Real asyncpg adapter that opens a real pool, then fails mid-discovery.

    ``create_connection_pool`` opens a REAL asyncpg pool against the container;
    ``execute_query`` raises a non-connection ``RuntimeError`` on the first
    catalog query. ``close_connection_pool`` records each call so the test can
    assert the ``finally`` drained the pool on the exception path.
    """

    instances: list["_FailMidDiscoveryPGAdapter"] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0
        type(self).instances.append(self)

    async def execute_query(self, query, params=None):
        raise RuntimeError("injected mid-discovery failure (#1575 regression)")

    async def close_connection_pool(self):
        self.close_calls += 1
        await super().close_connection_pool()


class _CountingClosePGAdapter(PostgreSQLAdapter):
    """Real adapter that only counts close_connection_pool calls (success path)."""

    instances: list["_CountingClosePGAdapter"] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.close_calls = 0
        type(self).instances.append(self)

    async def close_connection_pool(self):
        self.close_calls += 1
        await super().close_connection_pool()


class _FailMidDiscoverySQLiteAdapter(SQLiteAdapter):
    """Real SQLite adapter that connects, then fails on the first catalog query."""

    instances: list["_FailMidDiscoverySQLiteAdapter"] = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disconnect_calls = 0
        type(self).instances.append(self)

    async def execute_query(self, query, params=None):
        raise RuntimeError("injected mid-discovery failure (#1575 regression)")

    async def disconnect(self):
        self.disconnect_calls += 1
        await super().disconnect()


def _make_pg_engine():
    try:
        return DataFlow(database_url=POSTGRES_URL)
    except Exception as exc:  # pragma: no cover — infra-down skip
        pytest.skip(
            f"database at {POSTGRES_URL!r} not reachable ({exc}); this Tier-2 "
            f"test requires the real container to be up"
        )


# ---------------------------------------------------------------------------
# PRIMARY — deterministic exception-path drain (AC#4)
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_pg_inspect_closes_pool_on_mid_discovery_exception(monkeypatch):
    """PG: a mid-discovery exception still drains the adapter pool (try/finally).

    WITHOUT the fix, ``close_connection_pool`` is skipped when ``execute_query``
    raises, so ``close_calls == 0`` and the real pool leaks -> this assertion
    fails. WITH the fix, the ``finally`` drains it on the exception path.
    """
    engine = _make_pg_engine()
    _FailMidDiscoveryPGAdapter.instances.clear()
    # Route the method's lazy ``from ..adapters.postgresql import PostgreSQLAdapter``
    # to the deterministic subclass (real pool + injected failure).
    monkeypatch.setattr(
        "dataflow.adapters.postgresql.PostgreSQLAdapter",
        _FailMidDiscoveryPGAdapter,
    )

    with pytest.raises(RuntimeError, match="injected mid-discovery failure"):
        await engine._inspect_postgresql_schema_real(POSTGRES_URL)

    assert _FailMidDiscoveryPGAdapter.instances, "adapter was never constructed"
    adapter = _FailMidDiscoveryPGAdapter.instances[-1]
    assert adapter.close_calls >= 1, (
        "PostgreSQL adapter pool was NOT closed on the mid-discovery exception "
        "path — the try/finally in _inspect_postgresql_schema_real is missing "
        "(issue #1575 regression)"
    )
    assert adapter.connection_pool is None, "pool object survived the drain"


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_sqlite_inspect_disconnects_on_mid_discovery_exception(monkeypatch):
    """SQLite: a mid-discovery exception still disconnects the adapter (try/finally)."""
    engine = DataFlow(database_url="sqlite:///:memory:")
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "regression_1575.db")
        sqlite_url = f"sqlite:///{db_path}"

        _FailMidDiscoverySQLiteAdapter.instances.clear()
        monkeypatch.setattr(
            "dataflow.adapters.sqlite.SQLiteAdapter",
            _FailMidDiscoverySQLiteAdapter,
        )

        with pytest.raises(RuntimeError, match="injected mid-discovery failure"):
            await engine._inspect_sqlite_schema_real(sqlite_url)

        assert _FailMidDiscoverySQLiteAdapter.instances, "adapter never constructed"
        adapter = _FailMidDiscoverySQLiteAdapter.instances[-1]
        assert adapter.disconnect_calls >= 1, (
            "SQLite adapter was NOT disconnected on the mid-discovery exception "
            "path — the try/finally in _inspect_sqlite_schema_real is missing "
            "(issue #1575 regression)"
        )


# ---------------------------------------------------------------------------
# SUCCESS path — the drain still runs on the happy path
# ---------------------------------------------------------------------------


@pytest.mark.regression
@pytest.mark.integration
@pytest.mark.asyncio
async def test_pg_inspect_closes_pool_on_success(monkeypatch):
    """PG: the success path drains the adapter pool exactly once."""
    engine = _make_pg_engine()
    _CountingClosePGAdapter.instances.clear()
    monkeypatch.setattr(
        "dataflow.adapters.postgresql.PostgreSQLAdapter",
        _CountingClosePGAdapter,
    )

    try:
        schema = await engine._inspect_postgresql_schema_real(POSTGRES_URL)
    except Exception as exc:  # pragma: no cover — infra-down skip
        pytest.skip(f"PG inspection failed against real container ({exc})")

    assert isinstance(schema, dict)
    assert _CountingClosePGAdapter.instances, "adapter was never constructed"
    adapter = _CountingClosePGAdapter.instances[-1]
    assert adapter.close_calls == 1, (
        f"expected exactly one pool close on the success path, got "
        f"{adapter.close_calls}"
    )
    assert adapter.connection_pool is None


# ---------------------------------------------------------------------------
# SYMPTOM-path GC capture over the sync discover_schema transient-loop path
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


@pytest.mark.regression
@pytest.mark.integration
def test_pg_discover_schema_no_gc_dead_loop_signal():
    """Sync discover_schema over the transient loop leaves no dead-loop GC signal.

    ``discover_schema(use_real_inspection=True)`` runs the inspection coroutine
    on a transient loop via ``async_safe_run`` (which stamps BRIDGE_LOOP_ATTR
    and drains registered pools before close). Combined with the inspector's
    own try/finally, a full sync discovery must leave no unclosed-connection /
    "Event loop is closed" signal at GC.
    """
    engine = _make_pg_engine()

    # Sync bridge path — this is the transient-loop site #1575 targets.
    schema = engine.discover_schema(use_real_inspection=True)
    assert isinstance(schema, dict)

    del engine

    with _capture_gc_teardown_signals() as (caught, unraisables):
        for _ in range(3):
            gc.collect()
        gc.collect()

    rw_hits = _resource_warning_hits(caught)
    loop_hits = _event_loop_closed_hits(unraisables)
    assert (
        rw_hits == []
    ), f"discover_schema leaked unclosed connections at GC: {rw_hits}"
    assert (
        loop_hits == []
    ), f"discover_schema produced 'Event loop is closed' at GC: {loop_hits}"
