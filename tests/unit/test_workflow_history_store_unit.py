# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash.infrastructure.history_store``.

Per ``rules/testing.md`` § "3-Tier" Tier 1 may use deterministic
adapters for the ConnectionManager surface — the tests here validate
constructor invariants (table-name validation, retention bounds),
the auto-subscribe wiring on LocalRuntime, the read-redaction
write-time invariant, and the destructive-confirmation gate on
``delete_runs_older_than``.

Tier 2 + Tier 3 tests against real Postgres land in
``tests/integration/test_workflow_history_store_wiring.py`` and
``tests/e2e/test_redaction_history_store.py``.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import pytest

from kailash.infrastructure.history_store import (
    DowngradeRefusedError,
    PostgresHistoryStore,
    SQLiteHistoryStore,
    WorkflowHistoryStore,
)
from kailash.runtime.durable import NodeCompletionEvent

# ---------------------------------------------------------------------------
# Deterministic ConnectionManager adapter (Protocol-satisfying, NOT a mock)
# ---------------------------------------------------------------------------
#
# Per ``rules/testing.md`` § "Protocol Adapters" a class that satisfies
# the ConnectionManager surface at runtime with deterministic output is
# NOT a mock — it is a behaviour-preserving adapter.  These tests use
# the adapter ONLY to verify constructor / dispatch / redaction logic;
# the dialect-portable schema + atomic-transaction guarantees are
# exercised in Tier 2 against real Postgres.


class _DeterministicDialect:
    """Minimal QueryDialect surface used by the unit-level tests."""

    def quote_identifier(self, name: str) -> str:
        return f'"{name}"'

    def text_column(self, indexed: bool = False) -> str:
        return "TEXT"

    def blob_type(self) -> str:
        return "BLOB"

    def auto_id_column(self) -> str:
        return "id INTEGER PRIMARY KEY"

    def json_column_type(self) -> str:
        return "TEXT"

    def translate_query(self, q: str) -> str:
        return q


class _RecordingConn:
    """Records SQL + params so tests can assert query shape.

    Implements the ConnectionManager surface used by WorkflowHistoryStore
    (execute / fetch / fetchone / transaction / create_index / dialect).
    The transaction context manager yields ``self`` so multi-statement
    paths exercise the same recording.
    """

    def __init__(self, fetchone_results: Optional[List[Any]] = None) -> None:
        self.dialect = _DeterministicDialect()
        self.executes: List[tuple] = []
        self.created_indexes: List[tuple] = []
        self._fetchone_queue: List[Any] = list(fetchone_results or [])
        self._fetch_results: Dict[str, List[Dict[str, Any]]] = {}

    async def execute(self, query: str, *args: Any) -> Any:
        self.executes.append((query, args))
        return None

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        # Simple match by substring of query.
        for needle, rows in self._fetch_results.items():
            if needle in query:
                return rows
        return []

    async def fetchone(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        if self._fetchone_queue:
            return self._fetchone_queue.pop(0)
        return None

    async def create_index(self, name: str, table: str, columns: str) -> None:
        self.created_indexes.append((name, table, columns))

    class _TxProxy:
        def __init__(self, parent: "_RecordingConn") -> None:
            self._parent = parent

        async def execute(self, query: str, *args: Any) -> Any:
            return await self._parent.execute(query, *args)

        async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
            return await self._parent.fetch(query, *args)

        async def fetchone(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
            return await self._parent.fetchone(query, *args)

    def transaction(self):
        parent = self

        class _Cm:
            async def __aenter__(self_inner):
                return parent._TxProxy(parent)

            async def __aexit__(self_inner, exc_type, exc, tb):
                return False

        return _Cm()


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------


def test_constructor_rejects_invalid_runs_table() -> None:
    conn = _RecordingConn()
    with pytest.raises(ValueError, match=r"runs_table"):
        SQLiteHistoryStore(conn, runs_table="bad-name; DROP TABLE x")


def test_constructor_rejects_invalid_events_table() -> None:
    conn = _RecordingConn()
    with pytest.raises(ValueError, match=r"events_table"):
        SQLiteHistoryStore(conn, events_table="0starts_with_digit")


def test_constructor_accepts_valid_table_names() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(
        conn,
        runs_table="my_runs",
        events_table="my_events",
    )
    assert store._runs_table == "my_runs"
    assert store._events_table == "my_events"


def test_constructor_rejects_bool_true_retention_days() -> None:
    """retention_days=True is the silent-coerce-to-1 trap (zero-tolerance Rule 3c)."""
    conn = _RecordingConn()
    with pytest.raises(ValueError, match=r"retention_days=True"):
        SQLiteHistoryStore(conn, retention_days=True)


def test_constructor_accepts_false_retention_days() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn, retention_days=False)
    assert store._retention_days is None


def test_constructor_rejects_negative_retention_days() -> None:
    conn = _RecordingConn()
    with pytest.raises(ValueError, match=r"retention_days"):
        SQLiteHistoryStore(conn, retention_days=-7)


def test_constructor_rejects_zero_retention_days() -> None:
    conn = _RecordingConn()
    with pytest.raises(ValueError, match=r"retention_days"):
        SQLiteHistoryStore(conn, retention_days=0)


def test_constructor_rejects_negative_per_tenant_cap() -> None:
    conn = _RecordingConn()
    with pytest.raises(ValueError, match=r"per_tenant_cap"):
        SQLiteHistoryStore(conn, per_tenant_cap=-1)


# ---------------------------------------------------------------------------
# Read API: cross-tenant reads are BLOCKED
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_requires_tenant_id() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    with pytest.raises(ValueError, match=r"tenant_id"):
        await store.list_runs(filter={"status": "failed"})


@pytest.mark.asyncio
async def test_list_runs_rejects_unsupported_filter_keys() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    with pytest.raises(ValueError, match=r"unsupported filter keys"):
        await store.list_runs(filter={"tenant_id": "t1", "bogus_key": "x"})


@pytest.mark.asyncio
async def test_get_run_requires_tenant_id() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    with pytest.raises(ValueError, match=r"tenant_id"):
        await store.get_run("run-1", tenant_id=None)
    with pytest.raises(ValueError, match=r"tenant_id"):
        await store.get_run("run-1", tenant_id="")


@pytest.mark.asyncio
async def test_get_run_events_requires_tenant_id() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    with pytest.raises(ValueError, match=r"tenant_id"):
        await store.get_run_events("run-1", tenant_id=None)


@pytest.mark.asyncio
async def test_list_failed_requires_tenant_id() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    with pytest.raises(ValueError, match=r"tenant_id"):
        await store.list_failed(tenant_id=None)


@pytest.mark.asyncio
async def test_get_run_events_returns_empty_on_tenant_mismatch() -> None:
    """Tenant-scope check: when the run row does not match the tenant,
    the events query MUST return empty even if events exist for the run.
    """
    conn = _RecordingConn(fetchone_results=[None])  # run lookup returns None
    store = SQLiteHistoryStore(conn)
    rows = await store.get_run_events("run-1", tenant_id="t-other")
    assert rows == []


# ---------------------------------------------------------------------------
# delete_runs_older_than: destructive confirmation gate
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_runs_older_than_refuses_without_force() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    with pytest.raises(DowngradeRefusedError):
        await store.delete_runs_older_than(cutoff)


@pytest.mark.asyncio
async def test_delete_runs_older_than_runs_with_force() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    cutoff = datetime.now(timezone.utc) - timedelta(days=1)
    deleted = await store.delete_runs_older_than(cutoff, force_downgrade=True)
    assert deleted == 0  # no rows in the deterministic adapter


@pytest.mark.asyncio
async def test_delete_runs_older_than_rejects_bad_timestamp_type() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    with pytest.raises(TypeError, match=r"timestamp"):
        await store.delete_runs_older_than(12345, force_downgrade=True)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# record_event: read-redaction at write-time invariant
# ---------------------------------------------------------------------------


class _StubPolicy:
    """Classification policy that REDACTs everything for the test node."""

    def get_classification(self, node_id: str, field_name: str) -> Optional[str]:
        if node_id == "secret_node":
            return "REDACT"
        return None


@pytest.mark.asyncio
async def test_record_event_routes_through_redaction_helper() -> None:
    """The persisted payload MUST contain the [REDACTED] sentinel for
    classified fields — not the raw value.  This pins the cross-cutting
    invariant 4: read-redaction at write time.
    """
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn, classification_policy=_StubPolicy())
    store._initialized = True

    event = NodeCompletionEvent(
        run_id="run-redact-1",
        workflow_id="wf-1",
        workflow_fingerprint="fp-abc",
        node_id="secret_node",
        node_type="PythonCodeNode",
        outputs={"ssn": "123-45-6789", "name": "Alice"},
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=10,
        tenant_id="t1",
    )

    await store.record_event(event)

    # The first INSERT into workflow_run_events captures payload_json
    # at args[4].  Find that statement and decode the JSON.
    inserts = [
        (q, args)
        for (q, args) in conn.executes
        if "workflow_run_events" in q and q.strip().startswith("INSERT")
    ]
    assert (
        inserts
    ), f"expected an INSERT into workflow_run_events; got {conn.executes!r}"
    _, args = inserts[0]
    payload_json = args[4]
    payload = json.loads(payload_json)
    # Both fields are classified → both replaced with the [REDACTED]
    # sentinel.  The raw "123-45-6789" / "Alice" MUST NOT appear in
    # the persisted bytes.
    assert payload["outputs"]["ssn"] == "[REDACTED]"
    assert payload["outputs"]["name"] == "[REDACTED]"
    assert "123-45-6789" not in payload_json
    assert "Alice" not in payload_json


@pytest.mark.asyncio
async def test_record_event_skips_when_run_id_is_none() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    store._initialized = True
    event = NodeCompletionEvent(
        run_id=None,
        workflow_id="wf-1",
        workflow_fingerprint="fp",
        node_id="n1",
        node_type="PythonCodeNode",
        outputs={},
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=1,
        tenant_id="t1",
    )
    # Does not raise; emits a WARN log line and returns.
    await store.record_event(event)
    assert conn.executes == []


@pytest.mark.asyncio
async def test_record_event_raises_when_not_initialized() -> None:
    conn = _RecordingConn()
    store = SQLiteHistoryStore(conn)
    # Do NOT call initialize().
    event = NodeCompletionEvent(
        run_id="run-1",
        workflow_id="wf",
        workflow_fingerprint="fp",
        node_id="n",
        node_type="PythonCodeNode",
        outputs={},
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=1,
    )
    with pytest.raises(RuntimeError, match=r"initialize"):
        await store.record_event(event)


# ---------------------------------------------------------------------------
# LocalRuntime auto-subscribe wiring
# ---------------------------------------------------------------------------


def test_local_runtime_auto_subscribes_history_store() -> None:
    """LocalRuntime(history_store=<store>) MUST register the store's
    record_event with the W1 hook registry at construction time.
    """
    from kailash.runtime.local import LocalRuntime

    class _RecordingStore:
        def __init__(self) -> None:
            self.calls: List[NodeCompletionEvent] = []

        async def record_event(self, event: NodeCompletionEvent) -> None:
            self.calls.append(event)

    store = _RecordingStore()
    runtime = LocalRuntime(history_store=store)
    assert runtime._hook_registry.subscriber_count == 1


def test_local_runtime_no_history_store_means_no_subscriber() -> None:
    from kailash.runtime.local import LocalRuntime

    runtime = LocalRuntime()
    assert runtime._hook_registry.subscriber_count == 0


def test_local_runtime_rejects_history_store_without_record_event() -> None:
    from kailash.runtime.local import LocalRuntime

    class _BadStore:
        pass  # no record_event

    with pytest.raises(TypeError, match=r"record_event"):
        LocalRuntime(history_store=_BadStore())


def test_async_local_runtime_inherits_history_store_subscribe() -> None:
    """AsyncLocalRuntime(history_store=...) MUST inherit the same wiring
    via super().__init__(**kwargs) — no separate registration needed.
    """
    from kailash.runtime.async_local import AsyncLocalRuntime

    class _RecordingStore:
        async def record_event(self, event: NodeCompletionEvent) -> None:
            pass

    store = _RecordingStore()
    runtime = AsyncLocalRuntime(history_store=store)
    assert runtime._hook_registry.subscriber_count == 1


# ---------------------------------------------------------------------------
# ABC contract
# ---------------------------------------------------------------------------


def test_workflow_history_store_is_abstract() -> None:
    """WorkflowHistoryStore is an ABC; cannot be instantiated directly."""
    conn = _RecordingConn()
    with pytest.raises(TypeError):
        WorkflowHistoryStore(conn)  # type: ignore[abstract]


def test_postgres_and_sqlite_subclass_workflow_history_store() -> None:
    assert issubclass(PostgresHistoryStore, WorkflowHistoryStore)
    assert issubclass(SQLiteHistoryStore, WorkflowHistoryStore)
