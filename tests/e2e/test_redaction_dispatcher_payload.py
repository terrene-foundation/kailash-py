# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-3 E2E: redaction at enqueue-time invariant for the SQL task queue
dispatcher.

Per the W5 acceptance criterion in
``workspaces/runtime-integration-trio/todos/active/W5-*``: a classified
PK present in a dispatched ``workflow_blob`` (or in the per-task kwargs
that ride alongside) MUST be hashed before the row lands in the SQL
queue table.

The queue table is durable storage shared between the producer
(``WorkflowScheduler.dispatch``) and any worker pool that polls it. A
raw classified PK in the queue payload means every worker, every
operator with SELECT privilege on the table, and every backup of the
table sees the raw value — exactly the audit-leak failure mode the
classification policy exists to prevent.

This is the symmetric Tier-3 pin of the existing redaction test for the
W2 history store: BOTH durable persistence surfaces in the trio
(checkpoint blob, queue payload) MUST honor the same policy via the
same redaction helper. A surface-by-surface gap is a Rule-2 (orphan
detection) violation — the documented contract advertises a feature
the code performs on only some paths.

Requires PostgreSQL at ``TEST_PG_URL``; skips when unreachable.

Note: this test pins the SPEC contract per the W5 acceptance. If the
current ``SQLTaskQueueDispatcher`` does NOT yet thread a classification
policy through to the enqueue path, the test fails loudly — which is
the correct signal for a follow-up SDK fix per
``rules/zero-tolerance.md`` Rule 4. Do NOT amend the test to match the
implementation; amend the implementation to honor the spec.
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
from kailash.infrastructure.task_queue import SQLTaskQueue, SQLTaskQueueDispatcher
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
    for table in ("kailash_task_queue",):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    yield manager
    for table in ("kailash_task_queue",):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


@pytest.mark.e2e
async def test_dispatcher_payload_does_not_leak_unclassified_kwargs(
    pg_conn: ConnectionManager,
):
    """Baseline behavioral pin: kwargs that carry NO classification tag
    flow through to the queue payload verbatim.

    This is the no-redaction baseline. The next test pins the redaction
    contract for kwargs that DO carry a classification tag. Together
    they make the contract grep-able: which fields land raw, which
    land hashed.
    """
    queue = SQLTaskQueue(pg_conn)
    await queue.initialize()
    dispatcher = SQLTaskQueueDispatcher(pg_conn)
    await dispatcher.initialize()

    schedule_id = f"sched-{uuid.uuid4().hex[:8]}"
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    workflow_blob = json.dumps({"nodes": {}, "connections": []}).encode("utf-8")
    task = Task(
        task_id=task_id,
        schedule_id=schedule_id,
        workflow_blob=workflow_blob,
        planned_fire_time="2026-05-07T00:00:00+00:00",
        kwargs={"plain_field": "plain-value-no-classification"},
    )

    await dispatcher.enqueue(task)

    rows = await pg_conn.fetch(
        "SELECT payload FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1, "task did not land in queue table"
    raw = rows[0]["payload"]
    # Unclassified kwarg flows through verbatim — the baseline shape.
    assert "plain-value-no-classification" in raw


@pytest.mark.e2e
async def test_dispatcher_payload_hashes_classified_kwargs_at_enqueue(
    pg_conn: ConnectionManager,
):
    """A classified PK passed via the per-task ``kwargs`` MUST be hashed
    BEFORE the queue row is written. The persistent queue payload MUST
    NOT contain the raw classified value.

    Per the W5 acceptance: the dispatcher is a durable persistence
    surface (the SQL queue table outlives any process). It MUST honor
    the same classification policy as the checkpoint store and history
    store. If the dispatcher does not yet expose a
    ``classification_policy`` constructor kwarg, this test fails — and
    the failure surfaces the gap the W5 acceptance criterion was
    written to prevent.

    The test does NOT make the dispatcher's API exact (it uses a duck-
    typed ``classification_policy`` kwarg), so the failure mode the
    test pins is "the classified value LEAKED into the queue payload",
    not "the constructor signature is wrong".
    """
    raw_pk = "secret-customer-id-A1B2C3D4"

    class _CustomerHashPolicy:
        def get_classification(self, _node_id: str, field_name: str):
            # The dispatcher does not have a node_id/field_name shape
            # in the traditional sense; the duck-typed surface accepts
            # either ("kwargs", "<key>") or any equivalent the SDK
            # adopts. Default to HASH_PK for the classified key name.
            # node_id is part of the duck-typed policy contract but
            # this branch keys solely on field_name; underscore-
            # prefixed to silence pyright's unused-parameter check.
            if field_name == "customer_id":
                return "HASH_PK"
            return None

    # The dispatcher MUST accept a classification_policy (the spec
    # contract). If the constructor refuses the kwarg, the failure is
    # "TypeError: __init__ got unexpected keyword argument" — clear
    # signal of the gap.
    dispatcher = SQLTaskQueueDispatcher(
        pg_conn,
        classification_policy=_CustomerHashPolicy(),
    )
    await dispatcher.initialize()

    schedule_id = f"sched-{uuid.uuid4().hex[:8]}"
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    workflow_blob = json.dumps({"nodes": {}, "connections": []}).encode("utf-8")
    task = Task(
        task_id=task_id,
        schedule_id=schedule_id,
        workflow_blob=workflow_blob,
        planned_fire_time="2026-05-07T00:00:00+00:00",
        kwargs={"customer_id": raw_pk},
    )

    await dispatcher.enqueue(task)

    rows = await pg_conn.fetch(
        "SELECT payload FROM kailash_task_queue WHERE task_id = ?",
        task_id,
    )
    assert len(rows) == 1
    raw = rows[0]["payload"]
    assert raw_pk not in raw, (
        "Raw classified customer_id leaked to queue payload — write-time "
        "redaction failed at the dispatcher boundary. Per the W5 "
        "acceptance criterion the queue payload MUST hash classified "
        "kwargs before the row lands in kailash_task_queue."
    )


@pytest.mark.e2e
async def test_dispatcher_workflow_blob_hashes_classified_node_config(
    pg_conn: ConnectionManager,
):
    """A classified PK present in a workflow node's CONFIG (not runtime
    output) MUST be hashed before the workflow_blob is JSON-encoded
    into the queue payload.

    Per the W5 acceptance: "classified PK in workflow_blob hashed at
    enqueue time." The workflow_blob is a JSON dump of
    ``Workflow.to_dict()``; if a node's config dict carries a
    classified PK (e.g., a hardcoded customer_id in a PythonCodeNode
    parameter), the dispatcher MUST route the blob through redaction
    before persisting.

    If the SDK does not yet implement workflow-config redaction at the
    dispatcher boundary, this test fails loudly — the failure is the
    correct signal that the W5 acceptance criterion is unmet and a
    follow-up SDK PR is required. Do NOT amend the test to weaken the
    invariant.
    """
    raw_pk = "secret-account-id-XYZ-789"

    class _AccountHashPolicy:
        def get_classification(self, node_id: str, field_name: str):
            # Tag a node-config field for hashing.
            if node_id == "leak_node" and field_name == "code":
                return "HASH_PK"
            return None

    dispatcher = SQLTaskQueueDispatcher(
        pg_conn,
        classification_policy=_AccountHashPolicy(),
    )
    await dispatcher.initialize()

    # Build a workflow whose node config carries a classified PK in the
    # `code` parameter — the kind of authoring mistake the redaction
    # path exists to absorb gracefully.
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

    schedule_id = f"sched-{uuid.uuid4().hex[:8]}"
    task_id = f"task-{uuid.uuid4().hex[:8]}"
    task = Task(
        task_id=task_id,
        schedule_id=schedule_id,
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
    raw = rows[0]["payload"]
    assert raw_pk not in raw, (
        "Raw classified PK leaked to workflow_blob in queue payload — "
        "the dispatcher did not redact node config at enqueue time. "
        "Per the W5 acceptance criterion this is a contract violation."
    )
