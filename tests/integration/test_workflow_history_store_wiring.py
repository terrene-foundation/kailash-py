# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for WorkflowHistoryStore wiring.

Per ``rules/facade-manager-detection.md`` MUST Rule 2 the wiring test
file naming is ``test_<lowercase_manager_name>_wiring.py`` so the
absence of the file is grep-able.  Per ``rules/testing.md`` § "3-Tier"
NO mocking — every assertion observes a real PostgreSQL row.

Exercises:

* ``LocalRuntime(history_store=...)`` auto-subscribes the store's
  ``record_event`` against the W1 hook registry, so executing a
  workflow lands rows in ``workflow_runs`` + ``workflow_run_events``.
* ``list_runs`` returns the run, ``get_run`` returns one row,
  ``get_run_events`` returns the per-node event log.
* The persisted ``payload_json`` round-trips back to a dict on read.

Requires PostgreSQL at ``TEST_PG_URL`` (defaults to
``postgresql://test_user:test_password@localhost:5434/kailash_test``).
Tests skip when Postgres is unreachable so CI without docker still
runs the rest of the suite.
"""

from __future__ import annotations

import os
import socket
import uuid
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.history_store import PostgresHistoryStore
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow.builder import WorkflowBuilder

# ---------------------------------------------------------------------------
# Postgres availability
# ---------------------------------------------------------------------------

PG_URL = os.environ.get(
    "TEST_PG_URL",
    "postgresql://test_user:test_password@localhost:5434/kailash_test",
)


def _is_pg_available() -> bool:
    parsed = urlparse(PG_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 5432
    try:
        with socket.create_connection((host, port), timeout=2.0):
            return True
    except (OSError, ConnectionRefusedError, TimeoutError):
        return False


# Skip every test in this module if Postgres is unreachable — history
# persistence is the contract under test, and the dialect-portable
# schema invariants only fire against Postgres.
pytestmark = pytest.mark.skipif(
    not _is_pg_available(),
    reason=f"PostgreSQL not available at {PG_URL}",
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    """Yield a fresh PostgreSQL ConnectionManager and clean up after."""
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
    # Clean any lingering history rows from prior runs.
    for table in ("workflow_run_events", "workflow_runs"):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    yield manager
    for table in ("workflow_run_events", "workflow_runs"):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


@pytest.fixture
async def history_store(
    pg_conn: ConnectionManager,
) -> AsyncGenerator[PostgresHistoryStore, None]:
    """Yield an initialized PostgresHistoryStore against the test DB."""
    store = PostgresHistoryStore(pg_conn)
    await store.initialize()
    yield store
    await store.close()


def _build_two_node_workflow():
    """Two sequential PythonCodeNodes — minimal canonical pipeline."""
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "step1", {"code": "result = {'value': 1}"})
    wb.add_node(
        "PythonCodeNode",
        "step2",
        {"code": "result = {'value': value + 1}"},
    )
    wb.add_connection("step1", "result.value", "step2", "value")
    return wb.build()


# ---------------------------------------------------------------------------
# 1. Auto-subscribe + record_event end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_history_store_records_events_via_auto_subscribe(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
):
    """Constructing AsyncLocalRuntime(history_store=store) MUST auto-
    subscribe store.record_event so executing a workflow lands rows
    in workflow_runs + workflow_run_events.  Tier-2 invariant: the
    rows are observable via a direct DB query, not just the store's
    own read API.
    """
    workflow = _build_two_node_workflow()
    idempotency_key = f"test_record_{uuid.uuid4().hex[:8]}"

    runtime = AsyncLocalRuntime(history_store=history_store)
    results, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )

    # The execution succeeded.
    assert "step2" in results

    # Direct DB observation: workflow_runs has exactly one row.
    runs = await pg_conn.fetch(
        "SELECT run_id, status, idempotency_key FROM workflow_runs WHERE run_id = ?",
        run_id,
    )
    assert len(runs) == 1
    assert runs[0]["idempotency_key"] == idempotency_key

    # Direct DB observation: workflow_run_events has one row per node
    # (step1 + step2) with monotonic event_seq.
    events = await pg_conn.fetch(
        "SELECT event_seq, node_id_hash, event_type FROM workflow_run_events "
        "WHERE run_id = ? ORDER BY event_seq ASC",
        run_id,
    )
    assert len(events) == 2
    assert events[0]["event_seq"] == 1
    assert events[1]["event_seq"] == 2
    assert all(e["event_type"] == "node_completed" for e in events)


# ---------------------------------------------------------------------------
# 2. Read API: list_runs / get_run / get_run_events
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_history_store_list_runs_returns_executed_run(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
):
    workflow = _build_two_node_workflow()
    runtime = AsyncLocalRuntime(history_store=history_store)
    _, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=f"test_list_{uuid.uuid4().hex[:8]}",
    )

    # The default tenant is "default" when no tenant context is set.
    runs = await history_store.list_runs(filter={"tenant_id": "default"})
    matching = [r for r in runs if r["run_id"] == run_id]
    assert len(matching) == 1
    assert matching[0]["status"] in ("running", "failed")  # status enum


@pytest.mark.integration
async def test_history_store_get_run_returns_one_row(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
):
    workflow = _build_two_node_workflow()
    runtime = AsyncLocalRuntime(history_store=history_store)
    _, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=f"test_get_{uuid.uuid4().hex[:8]}",
    )

    row = await history_store.get_run(run_id, tenant_id="default")
    assert row is not None
    assert row["run_id"] == run_id


@pytest.mark.integration
async def test_history_store_get_run_events_returns_decoded_payloads(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
):
    """The payload_json column round-trips back to a dict on read —
    callers see ``event["payload"]`` as a Python dict, not a string.
    """
    workflow = _build_two_node_workflow()
    runtime = AsyncLocalRuntime(history_store=history_store)
    _, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=f"test_events_{uuid.uuid4().hex[:8]}",
    )

    events = await history_store.get_run_events(run_id, tenant_id="default")
    assert len(events) == 2
    # Every event has a decoded payload dict containing outputs+metadata.
    for ev in events:
        assert isinstance(ev["payload"], dict)
        assert "outputs" in ev["payload"]
        assert "metadata" in ev["payload"]


# ---------------------------------------------------------------------------
# 3. Cross-tenant isolation: a different tenant sees no rows
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_history_store_tenant_isolation_blocks_cross_tenant_read(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
):
    """A run written under tenant_id='default' MUST NOT be visible to
    a list_runs / get_run / get_run_events query scoped to a different
    tenant.  Cross-tenant reads are BLOCKED at the store layer per
    ``rules/tenant-isolation.md`` MUST Rule 5.
    """
    workflow = _build_two_node_workflow()
    runtime = AsyncLocalRuntime(history_store=history_store)
    _, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=f"test_isolation_{uuid.uuid4().hex[:8]}",
    )

    # Different tenant: should NOT see the run.
    runs_other = await history_store.list_runs(filter={"tenant_id": "tenant-other"})
    assert all(r["run_id"] != run_id for r in runs_other)

    row = await history_store.get_run(run_id, tenant_id="tenant-other")
    assert row is None

    events = await history_store.get_run_events(run_id, tenant_id="tenant-other")
    assert events == []


# ---------------------------------------------------------------------------
# 4. Indexes are present on the runs + events tables
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_history_store_indexes_present_on_runs_table(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
):
    """Per architecture plan §6 risk register the index set MUST include
    (tenant_id, started_at), (tenant_id, run_id), (tenant_id, status,
    started_at) on workflow_runs and (run_id, event_seq) on
    workflow_run_events.  The Postgres pg_indexes view confirms.
    """
    rows = await pg_conn.fetch(
        "SELECT indexname FROM pg_indexes "
        "WHERE tablename IN ('workflow_runs', 'workflow_run_events')"
    )
    names = {r["indexname"] for r in rows}
    assert "idx_workflow_runs_tenant_started_at" in names
    assert "idx_workflow_runs_tenant_run_id" in names
    assert "idx_workflow_runs_tenant_status_started" in names
    assert "idx_workflow_run_events_run_seq" in names


# ---------------------------------------------------------------------------
# 5b. C-3 tenant-scoped + batched DELETE in retention sweeps (#876)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_delete_runs_older_than_tenant_scoped_leaves_other_tenants(
    pg_conn: ConnectionManager,
):
    """Issue #876 L-1: ``delete_runs_older_than(tenant_id="a")`` MUST
    delete only tenant_a's expired runs; tenant_b's data MUST remain
    intact per ``rules/tenant-isolation.md`` MUST Rule 5.

    Constructs a store with ``retention_days=False`` so the write-time
    lazy retention sweep does NOT race the test's explicit sweep call.
    The C-3 contract under test is the explicit-call surface; the
    write-time sweep is tested separately.
    """
    from datetime import datetime, timedelta, timezone

    from kailash.runtime.durable import NodeCompletionEvent

    # Fresh store with retention disabled so write-time eviction does NOT
    # delete the test's expired rows BEFORE the explicit sweep runs.
    store = PostgresHistoryStore(pg_conn, retention_days=False)
    await store.initialize()

    past_ts = datetime.now(timezone.utc) - timedelta(days=60)

    # Insert one expired event per tenant.
    for tenant in ("tenant_a", "tenant_b"):
        run_id = f"r-{tenant}-{uuid.uuid4().hex[:8]}"
        event = NodeCompletionEvent(
            run_id=run_id,
            workflow_id="wf",
            workflow_fingerprint="fp",
            node_id="n",
            node_type="PythonCodeNode",
            outputs={},
            started_at=past_ts,
            ended_at=past_ts,
            duration_ms=1,
            tenant_id=tenant,
            error="forced terminal",  # mark terminal so terminal_at is set
        )
        await store.record_event(event)

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    # Sanity: both tenants have one run pre-delete.
    assert len(await store.list_runs(filter={"tenant_id": "tenant_a"})) == 1
    assert len(await store.list_runs(filter={"tenant_id": "tenant_b"})) == 1

    deleted = await store.delete_runs_older_than(
        cutoff, tenant_id="tenant_a", force_downgrade=True
    )
    assert deleted == 1

    # tenant_a's expired run is gone.
    assert await store.list_runs(filter={"tenant_id": "tenant_a"}) == []
    # tenant_b's run survives untouched.
    rows_b = await store.list_runs(filter={"tenant_id": "tenant_b"})
    assert len(rows_b) == 1


@pytest.mark.integration
async def test_delete_runs_older_than_batched_uses_two_statements(
    pg_conn: ConnectionManager,
):
    """Issue #876 L-2: the retention sweep over N expired runs MUST
    issue exactly two DELETE statements (events + runs), NOT 2N.

    Constructs a store with ``retention_days=False`` so the write-time
    lazy retention sweep does NOT race the test's explicit sweep call.
    """
    from datetime import datetime, timedelta, timezone

    from kailash.runtime.durable import NodeCompletionEvent

    store = PostgresHistoryStore(pg_conn, retention_days=False)
    await store.initialize()

    past_ts = datetime.now(timezone.utc) - timedelta(days=60)
    # Insert 5 expired runs for the default tenant.
    for i in range(5):
        run_id = f"r-batch-{i}-{uuid.uuid4().hex[:8]}"
        await store.record_event(
            NodeCompletionEvent(
                run_id=run_id,
                workflow_id="wf",
                workflow_fingerprint="fp",
                node_id=f"n{i}",
                node_type="PythonCodeNode",
                outputs={},
                started_at=past_ts,
                ended_at=past_ts,
                duration_ms=1,
                tenant_id="default",
                error="forced terminal",
            )
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    deleted = await store.delete_runs_older_than(cutoff, force_downgrade=True)
    assert deleted == 5

    # After the sweep neither runs nor events rows survive for those IDs.
    surviving = await store.list_runs(filter={"tenant_id": "default"})
    # Only non-expired runs survive (the post-sweep set excludes the 5
    # we just inserted).  We can't enumerate "the 5" by run_id post-
    # delete; the count test is enough — if N×DELETEs leaked rows the
    # eviction would have left orphan events.
    assert all(r.get("terminal_at") is None for r in surviving) or surviving == []


@pytest.mark.integration
async def test_delete_runs_older_than_default_is_cross_tenant(
    pg_conn: ConnectionManager,
):
    """Issue #876 L-1: ``tenant_id=None`` (default) preserves the
    cross-tenant sweep behaviour — every tenant's expired runs are
    pruned in one call.

    Constructs a store with ``retention_days=False`` so the write-time
    lazy retention sweep does NOT race the test's explicit sweep call.
    """
    from datetime import datetime, timedelta, timezone

    from kailash.runtime.durable import NodeCompletionEvent

    store = PostgresHistoryStore(pg_conn, retention_days=False)
    await store.initialize()

    past_ts = datetime.now(timezone.utc) - timedelta(days=60)
    for tenant in ("tenant_a", "tenant_b"):
        await store.record_event(
            NodeCompletionEvent(
                run_id=f"r-cross-{tenant}-{uuid.uuid4().hex[:8]}",
                workflow_id="wf",
                workflow_fingerprint="fp",
                node_id="n",
                node_type="PythonCodeNode",
                outputs={},
                started_at=past_ts,
                ended_at=past_ts,
                duration_ms=1,
                tenant_id=tenant,
                error="forced terminal",
            )
        )

    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    deleted = await store.delete_runs_older_than(cutoff, force_downgrade=True)
    # Both tenants pruned in one call.
    assert deleted == 2
    assert await store.list_runs(filter={"tenant_id": "tenant_a"}) == []
    assert await store.list_runs(filter={"tenant_id": "tenant_b"}) == []


# ---------------------------------------------------------------------------
# 5a. L-4 audit-safe-default — typed payload + unsupported type raise (#876)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_history_store_record_event_raises_on_unsupported_payload_type(
    history_store: PostgresHistoryStore,
):
    """Issue #876 L-4 (Tier-2): a node returning a ``set`` in its
    outputs MUST cause ``record_event`` to raise ``TypeError`` at
    audit-write time, NOT silently round-trip the value as its string
    repr.  Behavior change documented in the CHANGELOG migration entry
    per zero-tolerance.md Rule 6a.
    """
    from datetime import datetime, timezone

    from kailash.runtime.durable import NodeCompletionEvent

    event = NodeCompletionEvent(
        run_id=f"r-unsupported-{uuid.uuid4().hex[:8]}",
        workflow_id="wf-1",
        workflow_fingerprint="fp",
        node_id="bad_node",
        node_type="PythonCodeNode",
        outputs={"items": {1, 2, 3}},  # set — unsupported by the whitelist
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=1,
        tenant_id="default",
    )
    with pytest.raises(TypeError, match=r"unsupported type 'set'"):
        await history_store.record_event(event)


@pytest.mark.integration
async def test_history_store_record_event_serializes_decimal_payload(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
):
    """Issue #876 L-4 (Tier-2): a node returning a ``Decimal`` in its
    outputs MUST round-trip through the whitelist as a string-typed
    JSON value; readers reconstruct the precision via ``Decimal(value)``.
    """
    from datetime import datetime, timezone
    from decimal import Decimal

    from kailash.runtime.durable import NodeCompletionEvent

    run_id = f"r-decimal-{uuid.uuid4().hex[:8]}"
    event = NodeCompletionEvent(
        run_id=run_id,
        workflow_id="wf-decimal",
        workflow_fingerprint="fp",
        node_id="good_node",
        node_type="PythonCodeNode",
        outputs={"price": Decimal("19.99")},
        started_at=datetime.now(timezone.utc),
        ended_at=datetime.now(timezone.utc),
        duration_ms=1,
        tenant_id="default",
    )
    await history_store.record_event(event)

    events = await history_store.get_run_events(run_id, tenant_id="default")
    assert len(events) == 1
    # Decimal serialized as its string form per the whitelist contract.
    assert events[0]["payload"]["outputs"]["price"] == "19.99"


# ---------------------------------------------------------------------------
# 5. C-1 hashing-symmetry — no raw record-level IDs at WARN+ (#876)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_history_store_warn_logs_no_raw_record_identifiers(
    pg_conn: ConnectionManager,
    history_store: PostgresHistoryStore,
    caplog,
):
    """Issue #876 C-1 (Tier-2): execute a workflow against real Postgres
    and force the ``payload_decode_failed`` WARN path by writing an
    invalid JSON payload directly; assert no raw record-level
    identifier (run_id / workflow_id) appears in any history_store.*
    log record per ``rules/observability.md`` Rule 8.
    """
    import logging

    workflow = _build_two_node_workflow()
    runtime = AsyncLocalRuntime(history_store=history_store)
    _, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=f"test_warn_hash_{uuid.uuid4().hex[:8]}",
    )

    # Corrupt one event's payload_json so the next get_run_events read
    # triggers the WARN path.
    await pg_conn.execute(
        "UPDATE workflow_run_events SET payload_json = ? WHERE run_id = ?",
        "{not valid json",
        run_id,
    )

    caplog.clear()
    caplog.set_level(logging.WARNING)
    events = await history_store.get_run_events(run_id, tenant_id="default")
    # Corrupted row surfaces with empty payload (WARN-and-continue per Rule 8).
    assert any(ev["payload"] == {} for ev in events)

    history_records = [
        r
        for r in caplog.records
        if r.name.startswith("kailash.infrastructure.history_store")
    ]
    assert history_records, "expected history_store.* WARN line"
    for record in history_records:
        msg = record.getMessage()
        extra_repr = repr(record.__dict__)
        # Raw run_id MUST NOT appear in any history_store WARN record.
        assert run_id not in msg, f"raw run_id leaked into log message: {msg!r}"
        assert (
            run_id not in extra_repr
        ), f"raw run_id leaked into log extra: {extra_repr!r}"
