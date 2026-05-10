# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration test for the MissingRunIdError wiring end-to-end.

Issue #876 C-2b — exercises the full chain:

WorkflowHistoryStore.record_event(run_id=None)
  └── raises MissingRunIdError
        └── NodeCompletionHookRegistry.dispatch_async catches it typed-first
              ├── emits WARN "history_store.record_event.dropped" with hashed ids
              └── increments kailash_history_store_record_event_dropped_total

Per ``rules/facade-manager-detection.md`` MUST Rule 2 the wiring test
file naming is ``test_<lowercase_manager_name>_wiring.py``-shaped so
the absence of the file is grep-able.  We exercise the in-memory
SQLiteHistoryStore so the test stays in Tier 2 without docker;
identical wiring fires against the Postgres surface in production.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.history_store import SQLiteHistoryStore
from kailash.runtime.durable import NodeCompletionEvent, NodeCompletionHookRegistry
from kailash.runtime.metrics import get_metrics_bridge
from kailash.sdk_exceptions import MissingRunIdError


@pytest.fixture
async def history_store():
    """Yield a fresh SQLiteHistoryStore against an in-memory SQLite DB."""
    conn = ConnectionManager("sqlite:///:memory:")
    await conn.initialize()
    store = SQLiteHistoryStore(conn)
    await store.initialize()
    yield store
    await store.close()
    await conn.close()


@pytest.mark.asyncio
async def test_history_store_record_event_raises_typed_error_via_registry(
    history_store: SQLiteHistoryStore,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """End-to-end: register the store's ``record_event`` against a real
    hook registry; dispatching an event with ``run_id=None`` triggers
    the typed-error chain.

    Asserts:
    - the registry observes the typed error (not re-raised)
    - WARN log line ``history_store.record_event.dropped`` is emitted
      with hashed identifiers
    - metric counter increments
    - no SQL rows persisted (the typed gate fires BEFORE the transaction
      opens; we read back via ``list_runs`` to confirm zero rows)
    """
    caplog.set_level(logging.WARNING)
    bridge = get_metrics_bridge()
    counter_name = "kailash_history_store_record_event_dropped_total"
    before = bridge.cumulative_count(counter_name)

    registry = NodeCompletionHookRegistry()
    registry.register(history_store.record_event)

    now = datetime.now(timezone.utc)
    event = NodeCompletionEvent(
        run_id=None,
        workflow_id="wf-end-to-end",
        workflow_fingerprint="fp",
        node_id="node-end-to-end",
        node_type="PythonCodeNode",
        outputs={},
        started_at=now,
        ended_at=now,
        duration_ms=1,
        tenant_id="tenant-1",
    )

    # MUST NOT raise — typed handler observes and continues.
    await registry.dispatch_async(event)

    # Counter incremented.
    after = bridge.cumulative_count(counter_name)
    assert after == before + 1

    # WARN log line emitted with the right shape.
    dropped_records = [
        r
        for r in caplog.records
        if r.getMessage() == "history_store.record_event.dropped"
    ]
    assert len(dropped_records) == 1

    # No rows persisted — the typed gate fires before the transaction.
    rows = await history_store.list_runs(filter={"tenant_id": "tenant-1"})
    assert rows == []


@pytest.mark.asyncio
async def test_history_store_direct_call_raises_typed_error(
    history_store: SQLiteHistoryStore,
) -> None:
    """Direct call (not via the registry) MUST also raise the typed
    error — the typed-error contract is the store's public API, not
    an artifact of the registry path.
    """
    now = datetime.now(timezone.utc)
    event = NodeCompletionEvent(
        run_id=None,
        workflow_id="wf-direct",
        workflow_fingerprint="fp",
        node_id="node-direct",
        node_type="PythonCodeNode",
        outputs={},
        started_at=now,
        ended_at=now,
        duration_ms=1,
        tenant_id="tenant-direct",
    )
    with pytest.raises(MissingRunIdError) as exc_info:
        await history_store.record_event(event)
    assert exc_info.value.node_id == "node-direct"
    assert exc_info.value.workflow_id == "wf-direct"


@pytest.mark.asyncio
async def test_history_store_record_event_valid_path_does_not_increment_dropped_counter(
    history_store: SQLiteHistoryStore,
) -> None:
    """A normal record_event call MUST NOT touch the dropped counter —
    the counter is reserved for the typed-error signal.
    """
    bridge = get_metrics_bridge()
    counter_name = "kailash_history_store_record_event_dropped_total"
    before = bridge.cumulative_count(counter_name)

    now = datetime.now(timezone.utc)
    event = NodeCompletionEvent(
        run_id="run-happy-path",
        workflow_id="wf-happy",
        workflow_fingerprint="fp",
        node_id="node-happy",
        node_type="PythonCodeNode",
        outputs={"result": "ok"},
        started_at=now,
        ended_at=now,
        duration_ms=1,
        tenant_id="tenant-happy",
    )
    await history_store.record_event(event)

    after = bridge.cumulative_count(counter_name)
    assert after == before
