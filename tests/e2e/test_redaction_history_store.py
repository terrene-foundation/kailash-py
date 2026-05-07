# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-3 E2E: redaction at write-time invariant for the history store.

Per ``rules/orphan-detection.md`` MUST Rule 2a (crypto-pair round-trip
through facade) the cross-cutting invariant 4 (read-redaction at write
time) MUST be exercised through the runtime facade against a real
Postgres instance.  A classification-policy-tagged field in the event's
``outputs`` MUST be hashed via ``format_record_id_for_event`` (HASH_PK)
or replaced with the ``[REDACTED]`` sentinel BEFORE it lands in the
``payload_json`` column.

Concretely: the persisted bytes MUST NOT contain the raw classified
value, AND the ``classified_field_count`` column MUST reflect the
non-zero redaction.  Tier-2 unit tests cover the helper directly; this
Tier-3 test pins the end-to-end facade contract.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable.
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


pytestmark = pytest.mark.skipif(
    not _is_pg_available(),
    reason=f"PostgreSQL not available at {PG_URL}",
)


@pytest.fixture
async def pg_conn() -> AsyncGenerator[ConnectionManager, None]:
    manager = ConnectionManager(PG_URL)
    await manager.initialize()
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


class _SsnRedactPolicy:
    """Classification policy: REDACT the top-level ``result`` output of
    the 'leak_node'.

    Per :func:`~kailash.runtime.durable.redact_event_for_persistence`
    the policy is consulted for every TOP-LEVEL field of the event's
    ``outputs`` dict.  PythonCodeNode wraps user output under the
    ``result`` key, so redacting the SSN+email payload means redacting
    the entire ``result`` mapping at the top level.  The redaction helper
    replaces the whole value with the ``[REDACTED]`` sentinel — the
    nested SSN / email strings cannot leak through it.
    """

    def get_classification(self, node_id: str, field_name: str):
        if node_id == "leak_node" and field_name == "result":
            return "REDACT"
        return None


def _build_classified_workflow():
    """One-node workflow whose output emits two classified fields under
    the PythonCodeNode ``result`` wrapper."""
    wb = WorkflowBuilder()
    wb.add_node(
        "PythonCodeNode",
        "leak_node",
        {
            "code": (
                "result = {" "'ssn': '999-88-7777', " "'email': 'alice@example.com'" "}"
            )
        },
    )
    return wb.build()


@pytest.mark.e2e
async def test_redaction_at_write_time_in_history_store(
    pg_conn: ConnectionManager,
):
    """A classified field's raw value MUST NOT appear in the persisted
    payload_json bytes.  Per cross-cutting invariant 4: read-redaction
    at write time, NEVER re-redacted at read time.
    """
    history = PostgresHistoryStore(pg_conn, classification_policy=_SsnRedactPolicy())
    await history.initialize()

    workflow = _build_classified_workflow()
    runtime = AsyncLocalRuntime(history_store=history)
    _, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=f"test_redact_{uuid.uuid4().hex[:8]}",
    )

    # Direct DB observation: the persisted payload_json column MUST NOT
    # contain either of the raw classified values.  This is the
    # write-time-redaction invariant — if the bytes leak, the audit
    # log of every downstream consumer is poisoned.
    rows = await pg_conn.fetch(
        "SELECT payload_json, classified_field_count FROM workflow_run_events "
        "WHERE run_id = ?",
        run_id,
    )
    assert len(rows) == 1
    payload_bytes = rows[0]["payload_json"]
    assert (
        "999-88-7777" not in payload_bytes
    ), "Raw SSN leaked to payload_json — write-time redaction failed"
    assert (
        "alice@example.com" not in payload_bytes
    ), "Raw email leaked to payload_json — write-time redaction failed"
    # The top-level ``result`` field was classified → redacted →
    # contributes 1 to the classified-field count.  PythonCodeNode wraps
    # the user dict under ``result``, so the entire SSN+email payload
    # is replaced as one unit (any nested raw bytes inside that dict
    # disappear entirely from the persisted bytes).
    assert rows[0]["classified_field_count"] >= 1

    # Read-back through the facade: the [REDACTED] sentinel replaces the
    # whole ``result`` mapping — callers never see the raw SSN / email.
    events = await history.get_run_events(run_id, tenant_id="default")
    assert len(events) == 1
    outputs = events[0]["payload"]["outputs"]
    assert outputs.get("result") == "[REDACTED]"
