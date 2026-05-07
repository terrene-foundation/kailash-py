# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for the W6 SQLTaskQueueDispatcher
classification-policy kwarg.

Pre-W6 the dispatcher had no classification-policy surface — every
``task.kwargs`` and ``task.workflow_blob`` rode to the queue payload
row in plaintext, regardless of any classification policy in effect on
the producing runtime.  The W6 fix adds an opt-in
``classification_policy=`` constructor kwarg that routes both the
kwargs dict and the parsed workflow_blob's per-node config dicts
through the same ``redact_event_for_persistence`` helper used by the
runtime's checkpoint write-path and on_node_complete subscriber
surface.

These Tier-2 tests pin both halves of the contract end-to-end through
the real :class:`SQLTaskQueueDispatcher` against a real PostgreSQL
``kailash_task_queue`` table.  Per ``rules/testing.md`` § Tier 2 — NO
mocking; per ``rules/orphan-detection.md`` MUST Rule 2 — exercises
through the framework facade and asserts an externally-observable
effect (raw bytes absent from the persisted ``payload`` column).

Companion to ``tests/e2e/test_redaction_dispatcher_payload.py`` (W5
tier-3 RED tests, separate PR).  These integration tests live with the
W6 implementation so the SDK PR can ship with its own regression
coverage.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable.
"""

from __future__ import annotations

import json
import os
import socket
import uuid
from typing import AsyncGenerator
from urllib.parse import urlparse

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.task_queue import SQLTaskQueueDispatcher
from kailash.runtime.dispatcher import Task

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
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_task_queue")
    except Exception:
        # Cleanup best-effort — table may not exist on first run.
        pass
    yield manager
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_task_queue")
    except Exception:
        pass
    await manager.close()


# ---------------------------------------------------------------------------
# Stub policies — duck-typed per kailash.runtime.durable._get_classification_tag
# ---------------------------------------------------------------------------


class _CustomerHashKwargPolicy:
    """HASH_PK the configured kwarg field name; node_id ignored.

    The dispatcher passes node_id="" for kwargs (kwargs are not scoped
    to any one workflow node), so the policy keys solely on field_name.
    """

    def __init__(self, field_name: str) -> None:
        self._field = field_name

    def get_classification(self, _node_id: str, field_name: str):
        if field_name == self._field:
            return "HASH_PK"
        return None


class _NodeConfigRedactPolicy:
    """REDACT a specific (node_id, field_name) pair inside a workflow
    blob's per-node config dict."""

    def __init__(self, node_id: str, field_name: str) -> None:
        self._node = node_id
        self._field = field_name

    def get_classification(self, node_id: str, field_name: str):
        if node_id == self._node and field_name == self._field:
            return "REDACT"
        return None


# ---------------------------------------------------------------------------
# Back-compat: no policy → kwargs flow through verbatim
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_dispatcher_no_policy_passes_kwargs_through(
    pg_conn: ConnectionManager,
):
    """When classification_policy=None (default), kwargs land in the
    queue payload verbatim — back-compat baseline.  Existing callers
    that constructed SQLTaskQueueDispatcher(conn) before W6 MUST NOT
    see a behavior change.
    """
    dispatcher = SQLTaskQueueDispatcher(pg_conn)  # default: no policy
    await dispatcher.initialize()

    plaintext = "plain-no-classification-tag"
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    workflow_blob = json.dumps({"nodes": {}, "connections": []}).encode("utf-8")
    task = Task(
        task_id=task_id,
        schedule_id=f"sched-{uuid.uuid4().hex[:8]}",
        workflow_blob=workflow_blob,
        planned_fire_time="2026-05-07T00:00:00+00:00",
        kwargs={"public_field": plaintext},
    )

    await dispatcher.enqueue(task)

    rows = await pg_conn.fetch(
        "SELECT payload FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1, "task did not land in queue"
    assert plaintext in rows[0]["payload"], (
        "Default-policy dispatcher should pass unclassified kwargs through "
        "verbatim — back-compat broken."
    )


# ---------------------------------------------------------------------------
# Kwargs redaction — HASH_PK
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_dispatcher_hashes_classified_kwarg(
    pg_conn: ConnectionManager,
):
    """A classified kwarg field MUST be hashed before the row lands in
    kailash_task_queue.payload.  Pins the kwargs-redaction half of the
    W6 dispatcher contract.
    """
    raw_pk = "secret-customer-pk-A1B2C3"
    dispatcher = SQLTaskQueueDispatcher(
        pg_conn,
        classification_policy=_CustomerHashKwargPolicy("customer_id"),
    )
    await dispatcher.initialize()

    task_id = f"task-{uuid.uuid4().hex[:8]}"
    workflow_blob = json.dumps({"nodes": {}, "connections": []}).encode("utf-8")
    task = Task(
        task_id=task_id,
        schedule_id=f"sched-{uuid.uuid4().hex[:8]}",
        workflow_blob=workflow_blob,
        planned_fire_time="2026-05-07T00:00:00+00:00",
        kwargs={"customer_id": raw_pk, "public_field": "plain-value"},
    )

    await dispatcher.enqueue(task)

    rows = await pg_conn.fetch(
        "SELECT payload FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert raw_pk not in payload, (
        "Raw classified customer_id leaked to queue payload — "
        "dispatcher kwargs redaction did not run."
    )
    # Unclassified field still flows through.
    assert "plain-value" in payload, (
        "Unclassified field should still flow through — only "
        "classified fields are redacted."
    )

    # The hash sentinel ("pk:") for HASH_PK is present in the payload.
    assert "pk:" in payload, (
        "HASH_PK sentinel missing from queue payload — kwarg redaction "
        "ran but did not produce the expected sentinel shape."
    )


# ---------------------------------------------------------------------------
# Workflow_blob redaction — node config REDACT
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_dispatcher_redacts_classified_node_config(
    pg_conn: ConnectionManager,
):
    """A classified field inside a workflow node's config dict MUST be
    redacted before the workflow_blob is serialised into the queue
    payload.  Pins the workflow_blob-redaction half of the W6
    dispatcher contract.

    A common authoring mistake: a hardcoded credential, account ID, or
    SSN in a PythonCodeNode's ``code`` parameter.  The redaction path
    catches that authoring mistake before the value lands in the
    durable queue table.
    """
    raw_pk = "secret-account-XYZ-789-CONFIDENTIAL"
    dispatcher = SQLTaskQueueDispatcher(
        pg_conn,
        classification_policy=_NodeConfigRedactPolicy(
            node_id="leak_node", field_name="code"
        ),
    )
    await dispatcher.initialize()

    workflow_dict = {
        "nodes": {
            "leak_node": {
                "node_id": "leak_node",
                "node_type": "PythonCodeNode",
                "config": {"code": f"result = {{'pk': '{raw_pk}'}}"},
            }
        },
        "connections": [],
    }
    workflow_blob = json.dumps(workflow_dict).encode("utf-8")

    task_id = f"task-{uuid.uuid4().hex[:8]}"
    task = Task(
        task_id=task_id,
        schedule_id=f"sched-{uuid.uuid4().hex[:8]}",
        workflow_blob=workflow_blob,
        planned_fire_time="2026-05-07T00:00:00+00:00",
        kwargs={},
    )

    await dispatcher.enqueue(task)

    rows = await pg_conn.fetch(
        "SELECT payload FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert raw_pk not in payload, (
        "Raw classified account ID leaked to workflow_blob in queue "
        "payload — dispatcher did not redact node config at enqueue time."
    )
    # The sentinel for REDACT is present in the embedded workflow blob.
    assert "[REDACTED]" in payload, (
        "REDACT sentinel missing from queue payload — node-config "
        "redaction ran but did not produce the expected sentinel shape."
    )


# ---------------------------------------------------------------------------
# Workflow_blob — only classified fields are touched; unclassified survive
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_dispatcher_workflow_blob_preserves_unclassified_fields(
    pg_conn: ConnectionManager,
):
    """Workflow blob redaction MUST be surgical — only the classified
    (node, field) pair is touched.  Other top-level workflow fields
    (workflow_id, name, connections, metadata) and other node configs
    flow through unchanged.

    This is the inverse of test_dispatcher_redacts_classified_node_config:
    proves the helper does NOT over-redact.
    """
    public_code = "result = {'public_pk': 'public-value-OK-to-leak'}"
    dispatcher = SQLTaskQueueDispatcher(
        pg_conn,
        # Policy targets ONLY (target_node, code); leaves other_node alone.
        classification_policy=_NodeConfigRedactPolicy(
            node_id="target_node", field_name="code"
        ),
    )
    await dispatcher.initialize()

    workflow_dict = {
        "workflow_id": "preserved-id-001",
        "name": "preserved-name",
        "nodes": {
            "target_node": {
                "node_id": "target_node",
                "node_type": "PythonCodeNode",
                "config": {"code": "result = {'leaked_value': 'XYZ-789'}"},
            },
            "other_node": {
                "node_id": "other_node",
                "node_type": "PythonCodeNode",
                "config": {"code": public_code},
            },
        },
        "connections": [],
    }
    workflow_blob = json.dumps(workflow_dict).encode("utf-8")

    task_id = f"task-{uuid.uuid4().hex[:8]}"
    task = Task(
        task_id=task_id,
        schedule_id=f"sched-{uuid.uuid4().hex[:8]}",
        workflow_blob=workflow_blob,
        planned_fire_time="2026-05-07T00:00:00+00:00",
        kwargs={},
    )

    await dispatcher.enqueue(task)

    rows = await pg_conn.fetch(
        "SELECT payload FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1
    payload = rows[0]["payload"]
    # Targeted redaction succeeded.
    assert "XYZ-789" not in payload, (
        "target_node's classified code was not redacted; payload still "
        "contains the raw leaked value."
    )
    # Non-targeted node and top-level fields survived verbatim.
    assert "public-value-OK-to-leak" in payload, (
        "other_node's unclassified code was over-redacted — the helper "
        "is touching fields outside the policy's scope."
    )
    assert "preserved-id-001" in payload, (
        "workflow_id was redacted — only node configs should be in "
        "the redaction scope."
    )
    assert "preserved-name" in payload, (
        "workflow name was redacted — only node configs should be in "
        "the redaction scope."
    )


# ---------------------------------------------------------------------------
# Idempotency contract preserved across redaction
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_dispatcher_idempotent_enqueue_under_redaction(
    pg_conn: ConnectionManager,
):
    """The dispatcher's idempotency contract (duplicate enqueue with
    the same task_id is a silent no-op) MUST survive the W6 redaction
    addition.  Pins back-compat for the dispatcher's PRIMARY KEY
    semantics — a regression here would silently deduplicate
    legitimately distinct tasks.
    """
    dispatcher = SQLTaskQueueDispatcher(
        pg_conn,
        classification_policy=_CustomerHashKwargPolicy("customer_id"),
    )
    await dispatcher.initialize()

    task_id = f"task-{uuid.uuid4().hex[:8]}"
    workflow_blob = json.dumps({"nodes": {}, "connections": []}).encode("utf-8")
    task = Task(
        task_id=task_id,
        schedule_id=f"sched-{uuid.uuid4().hex[:8]}",
        workflow_blob=workflow_blob,
        planned_fire_time="2026-05-07T00:00:00+00:00",
        kwargs={"customer_id": "secret-A"},
    )

    # Two enqueues with identical task_id — the second is a silent no-op.
    await dispatcher.enqueue(task)
    await dispatcher.enqueue(task)  # duplicate — must NOT raise

    rows = await pg_conn.fetch(
        "SELECT task_id FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1, (
        "Duplicate enqueue should be a silent no-op — found "
        f"{len(rows)} rows instead of 1."
    )
