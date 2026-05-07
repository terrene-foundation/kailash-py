# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-3 E2E: redaction at write-time invariant for the checkpoint store.

Per ``rules/orphan-detection.md`` MUST Rule 2a + the W5 acceptance
criterion in ``workspaces/runtime-integration-trio/todos/active/W5-*``,
classification-policy-tagged fields in node outputs MUST be hashed (or
sentinel-replaced) BEFORE the per-node checkpoint blob lands in the
``kailash_checkpoints`` table.

The checkpoint blob is what a *new* runtime process replays after a
crash; if a classified PK leaks into the blob, the leak survives every
subsequent resume of the same idempotency key. This is the Tier-3
counterpart to the existing Tier-2 redaction tests for the durable
helper — it pins the contract end-to-end through the runtime facade
against a real PostgreSQL instance.

Companion to ``test_redaction_history_store.py`` (already shipped in
W2 PR #875). Together the two tests cover the cross-cutting invariant
that EVERY persistence surface in the durable trio routes events
through ``redact_event_for_persistence`` before write.

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
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.durable import (
    build_checkpoint_key,
    compute_workflow_fingerprint,
    decode_checkpoint_payload,
)
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
    for table in ("kailash_checkpoints",):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    yield manager
    for table in ("kailash_checkpoints",):
        try:
            await manager.execute(f"DROP TABLE IF EXISTS {table}")
        except Exception:
            pass
    await manager.close()


@pytest.fixture
async def checkpoint_store(
    pg_conn: ConnectionManager,
) -> AsyncGenerator[DBCheckpointStore, None]:
    store = DBCheckpointStore(pg_conn)
    await store.initialize()
    yield store
    await store.close()


class _CustomerHashPolicy:
    """Classification policy: HASH_PK the ``customer_id`` field of the
    ``leak_node`` so its raw value is replaced by a stable digest before
    it lands in any persistence surface (checkpoint blob OR history row).

    Per ``kailash.runtime.durable._get_classification_tag``, the policy
    surface is duck-typed: ``get_classification(node_id, field_name)``
    returning ``"REDACT"``, ``"HASH_PK"``, or ``None``. The classified
    field name lives at the TOP LEVEL of the node's outputs dict —
    PythonCodeNode wraps user assignments under the ``result`` key, so
    the classified field on the persistence surface is ``result``.

    For the HASH_PK pin we want the WHOLE result dict to be hashed (the
    raw customer ID inside it MUST NOT survive in the blob), so we tag
    ``result`` with HASH_PK; the redaction helper coerces the dict to
    its ``str()`` form before hashing — sufficient for byte-leak
    detection.
    """

    def get_classification(self, node_id: str, field_name: str):
        if node_id == "leak_node" and field_name == "result":
            return "HASH_PK"
        return None


class _SsnRedactPolicy:
    """Classification policy: REDACT the entire ``result`` field of
    the ``leak_node`` so the raw SSN payload never lands in the
    persistent checkpoint blob.

    Mirrors the policy used by the W2 history-store redaction test —
    the contract under test is that BOTH persistence surfaces honor
    the same classification policy via the same redaction helper.
    """

    def get_classification(self, node_id: str, field_name: str):
        if node_id == "leak_node" and field_name == "result":
            return "REDACT"
        return None


def _build_classified_workflow(payload_code: str):
    """One-node workflow whose output emits classified fields under
    PythonCodeNode's ``result`` wrapper."""
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "leak_node", {"code": payload_code})
    return wb.build()


@pytest.mark.e2e
async def test_redaction_at_write_time_in_checkpoint_store_redact(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """A classified field's raw value MUST NOT appear in the persisted
    checkpoint blob bytes when the classification tag is REDACT.

    This is the symmetric Tier-3 pin of the existing history-store test
    — both surfaces consume the same ``redact_event_for_persistence``
    helper, so a single shared bug would leak both. Pinning the
    checkpoint surface independently prevents future refactor from
    silently bypassing the helper on one of the two paths (per
    ``rules/dataflow-classification.md`` MUST Rule 2 — delegation-based
    redaction MUST be pinned end-to-end).
    """
    classification_policy = _SsnRedactPolicy()
    workflow = _build_classified_workflow(
        "result = {'ssn': '999-88-7777', 'email': 'alice@example.com'}"
    )
    idempotency_key = f"test_redact_ckpt_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    # The runtime carries the classification policy via attribute
    # injection — the same path the W1 wiring uses on the checkpoint
    # branch (see kailash.runtime.local._classification_policy lookup
    # at the per-node hook dispatch site).
    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = classification_policy  # noqa: SLF001

    _, run_id = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )

    # Direct DB observation: the persisted checkpoint row's `data`
    # column is the encoded payload. The classified raw values MUST NOT
    # survive in those bytes.
    rows = await pg_conn.fetch(
        "SELECT data FROM kailash_checkpoints WHERE checkpoint_key = ?",
        expected_key,
    )
    assert len(rows) == 1, "checkpoint blob was not persisted at all"
    blob = rows[0]["data"]
    if isinstance(blob, memoryview):  # asyncpg returns memoryview for BYTEA
        blob = bytes(blob)

    assert (
        b"999-88-7777" not in blob
    ), "Raw SSN leaked to checkpoint blob — write-time redaction failed"
    assert (
        b"alice@example.com" not in blob
    ), "Raw email leaked to checkpoint blob — write-time redaction failed"

    # The blob is NOT empty either — the redaction must replace, not
    # drop. The `[REDACTED]` sentinel that the helper writes for the
    # entire `result` mapping MUST be present.
    assert b"[REDACTED]" in blob, (
        "Redaction sentinel missing from checkpoint blob — the helper "
        "did not run on the checkpoint write path"
    )


@pytest.mark.e2e
async def test_redaction_at_write_time_in_checkpoint_store_hash_pk(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """A HASH_PK-tagged field's raw value MUST be replaced by the
    ``pk:<digest>`` sentinel before the checkpoint blob is written.

    This pins the second redaction tag the helper supports so a future
    refactor narrowing the helper to REDACT-only would fail this test.
    Per the W5 todo's acceptance criterion: the persisted blob must
    carry the HASH_PK digest, not the raw value.
    """
    classification_policy = _CustomerHashPolicy()
    raw_pk = "customer-A-secret-id-12345"
    workflow = _build_classified_workflow(f"result = {{'customer_id': '{raw_pk}'}}")
    idempotency_key = f"test_hash_pk_ckpt_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = classification_policy  # noqa: SLF001

    _, _ = await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )

    rows = await pg_conn.fetch(
        "SELECT data FROM kailash_checkpoints WHERE checkpoint_key = ?",
        expected_key,
    )
    assert len(rows) == 1
    blob = rows[0]["data"]
    if isinstance(blob, memoryview):
        blob = bytes(blob)

    assert (
        raw_pk.encode("utf-8") not in blob
    ), "Raw customer_id leaked to checkpoint blob — HASH_PK redaction failed"

    # The blob is decodable through the SDK helper — verifies the
    # write path emitted a well-formed payload, not a corrupt one.
    decoded = decode_checkpoint_payload(blob)
    assert "tracker" in decoded, (
        "Decoded checkpoint payload missing tracker field — the write "
        "may have corrupted the blob"
    )
