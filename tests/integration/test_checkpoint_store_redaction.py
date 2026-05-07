# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-2 integration tests for the W6 checkpoint write-path redaction.

The W2 ``runtime.on_node_complete`` hook contract guarantees that
subscribers never observe a classified PK or a redacted field's raw
value.  W6 extends that contract to the checkpoint write-path: the
runtime previously dispatched a redacted event to hooks while writing
the RAW ``execution_tracker.to_dict()`` to the checkpoint store —
leaking every classified node output to disk.

These Tier-2 tests pin the W6 fix end-to-end through both the sync
``LocalRuntime`` and async ``AsyncLocalRuntime`` facades against a real
PostgreSQL ``DBCheckpointStore``.  Per ``rules/testing.md`` § Tier 2 —
NO mocking; per ``rules/orphan-detection.md`` MUST Rule 2 — the test
exercises the manager through the framework facade and asserts an
externally-observable effect (raw bytes absent from the persisted
``data`` column).

Companion to ``tests/e2e/test_redaction_checkpoint_store.py`` (W5
tier-3 RED tests, separate PR).  These integration tests live with the
W6 implementation so the SDK PR can ship with its own regression
coverage independent of the W5 worktree's tier-3 sweep.

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
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_checkpoints")
    except Exception:
        # Cleanup best-effort — table may not exist on first run.
        pass
    yield manager
    try:
        await manager.execute("DROP TABLE IF EXISTS kailash_checkpoints")
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


# ---------------------------------------------------------------------------
# Stub policies — duck-typed per kailash.runtime.durable._get_classification_tag
# ---------------------------------------------------------------------------


class _RedactResultFieldPolicy:
    """REDACT the ``result`` field on the configured node.

    PythonCodeNode wraps user assignments under a top-level ``result``
    key, so tagging ``result`` redacts the entire output dict at the
    persistence-surface boundary — the safest pin for byte-leak tests.
    """

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id

    def get_classification(self, node_id: str, field_name: str):
        if node_id == self._node_id and field_name == "result":
            return "REDACT"
        return None


class _HashPkResultFieldPolicy:
    """HASH_PK the ``result`` field on the configured node.

    Mirrors W5's _CustomerHashPolicy so the same byte-leak invariant is
    pinned for the HASH_PK tag as well as REDACT.
    """

    def __init__(self, node_id: str) -> None:
        self._node_id = node_id

    def get_classification(self, node_id: str, field_name: str):
        if node_id == self._node_id and field_name == "result":
            return "HASH_PK"
        return None


def _build_classified_workflow(payload_code: str):
    """One-node PythonCodeNode workflow whose output emits classified
    fields under PythonCodeNode's ``result`` wrapper."""
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "leak_node", {"code": payload_code})
    return wb.build()


# ---------------------------------------------------------------------------
# Async runtime — REDACT path
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_async_runtime_checkpoint_redacts_classified_outputs(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """AsyncLocalRuntime — REDACT-tagged node outputs MUST be replaced
    by [REDACTED] sentinel in the persisted checkpoint blob.

    Pre-W6 the checkpoint blob carried RAW
    ``execution_tracker.to_dict()`` even though the on_node_complete
    subscriber surface received a redacted event.  This test pins that
    the persisted blob now carries the same redacted shape.
    """
    raw_secret = "ssn-DO-NOT-LEAK-12345"
    workflow = _build_classified_workflow(
        f"result = {{'ssn': '{raw_secret}', 'name': 'Alice'}}"
    )
    idempotency_key = f"async_redact_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = _RedactResultFieldPolicy(  # noqa: SLF001
        "leak_node"
    )

    await runtime.execute_workflow_async(
        workflow,
        inputs={},
        idempotency_key=idempotency_key,
    )

    rows = await pg_conn.fetch(
        "SELECT data FROM kailash_checkpoints WHERE checkpoint_key = ?",
        expected_key,
    )
    assert len(rows) == 1, "checkpoint blob was not persisted"
    blob = rows[0]["data"]
    if isinstance(blob, memoryview):
        blob = bytes(blob)

    assert raw_secret.encode("utf-8") not in blob, (
        "Raw classified value leaked to checkpoint blob — "
        "redacted_tracker_state_for_checkpoint did not run on the "
        "checkpoint write path."
    )
    assert b"[REDACTED]" in blob, (
        "Redaction sentinel missing from checkpoint blob — the helper "
        "ran but did not actually redact."
    )

    # The blob is a well-formed payload — decode succeeds AND the
    # tracker's node_outputs carry the sentinel for the classified node.
    decoded = decode_checkpoint_payload(blob)
    tracker_state = decoded["tracker"]
    leak_outputs = tracker_state["node_outputs"].get("leak_node", {})
    assert leak_outputs.get("result") == "[REDACTED]", (
        "Decoded checkpoint outputs[leak_node][result] should be the "
        "sentinel; got %r" % (leak_outputs.get("result"),)
    )


# ---------------------------------------------------------------------------
# Async runtime — HASH_PK path
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_async_runtime_checkpoint_hash_pk_classified_outputs(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """AsyncLocalRuntime — HASH_PK-tagged node outputs MUST be replaced
    by the ``pk:<digest>`` sentinel in the persisted checkpoint blob.

    Pins the second redaction tag so a future refactor narrowing the
    helper to REDACT-only would fail this test.
    """
    raw_pk = "customer-pk-A1B2C3-CONFIDENTIAL"
    workflow = _build_classified_workflow(f"result = {{'pk': '{raw_pk}'}}")
    idempotency_key = f"async_hash_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = _HashPkResultFieldPolicy(  # noqa: SLF001
        "leak_node"
    )

    await runtime.execute_workflow_async(
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

    assert raw_pk.encode("utf-8") not in blob, (
        "Raw classified PK leaked to checkpoint blob — HASH_PK redaction "
        "did not run on the checkpoint write path."
    )

    decoded = decode_checkpoint_payload(blob)
    tracker_state = decoded["tracker"]
    leak_result = tracker_state["node_outputs"].get("leak_node", {}).get("result")
    assert isinstance(leak_result, str) and leak_result.startswith(
        "pk:"
    ), "Decoded leak_node result should be a 'pk:<digest>' sentinel; " "got %r" % (
        leak_result,
    )


# ---------------------------------------------------------------------------
# No-policy back-compat path
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_async_runtime_checkpoint_no_policy_passes_through(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """When no classification_policy is set, node outputs flow through
    to the checkpoint blob unchanged — the W6 helper is opt-in via the
    runtime's existing _classification_policy attribute and MUST NOT
    silently degrade existing single-tenant single-classification
    deployments.
    """
    plaintext = "value-with-no-classification-tag"
    workflow = _build_classified_workflow(f"result = {{'public_field': '{plaintext}'}}")
    idempotency_key = f"async_nopol_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    # Intentionally NO classification policy assignment.

    await runtime.execute_workflow_async(
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

    # No-policy path: unclassified value flows through verbatim.  This
    # is the back-compat baseline — the W6 helper is opt-in.
    assert plaintext.encode("utf-8") in blob


# ---------------------------------------------------------------------------
# Sync runtime — REDACT path (parity with async)
# ---------------------------------------------------------------------------


@pytest.mark.integration
async def test_sync_runtime_checkpoint_redacts_classified_outputs(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """LocalRuntime parity test — sync path MUST redact identically.

    The W6 fix wires the same helper into both runtimes; if the sync
    path ever drifts (e.g., a future refactor inlines the encode call
    without the helper), this test fails.  Mirrors the rule in
    rules/dataflow-classification.md MUST Rule 2 (delegation-based
    redaction MUST be pinned) for the sync path.
    """
    # The sync runtime's checkpoint block at local.py:2731-2785 is
    # reached via LocalRuntime.execute_async (the path Nexus and similar
    # wrappers use, per the existing test_local_runtime_checkpoint_wiring
    # § "Hook + checkpoint co-exist in LocalRuntime (sync entrypoint)").
    # This test pins the W6 fix on that path independently of the async
    # runtime's own checkpoint block (async_local.py:640-682).
    from kailash.runtime.local import LocalRuntime

    raw_secret = "sync-side-leak-XYZ-789"
    workflow = _build_classified_workflow(f"result = {{'ssn': '{raw_secret}'}}")
    idempotency_key = f"sync_redact_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    runtime = LocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = _RedactResultFieldPolicy(  # noqa: SLF001
        "leak_node"
    )

    # LocalRuntime.execute_async is the path that contains the W6
    # checkpoint block in src/kailash/runtime/local.py:2731-2785.
    await runtime.execute_async(workflow, idempotency_key=idempotency_key)

    rows = await pg_conn.fetch(
        "SELECT data FROM kailash_checkpoints WHERE checkpoint_key = ?",
        expected_key,
    )
    assert len(rows) == 1
    blob = rows[0]["data"]
    if isinstance(blob, memoryview):
        blob = bytes(blob)

    assert raw_secret.encode("utf-8") not in blob, (
        "Raw classified value leaked to checkpoint blob from sync "
        "runtime — local.py W6 fix did not run on the sync checkpoint "
        "write path."
    )
    assert b"[REDACTED]" in blob


# ---------------------------------------------------------------------------
# W6 round-2 — nested-dict redaction (security-reviewer Finding 1)
# ---------------------------------------------------------------------------


class _NestedLeafRedactPolicy:
    """REDACT a nested-leaf path (e.g. ``customer.ssn``) but leave
    sibling leaves and the wrapper alone.  Pre-W6-round-2 the
    ``redact_event_for_persistence`` helper iterated only top-level
    keys — wrapper-only tagging worked, leaf tagging silently passed
    the raw value through.
    """

    def __init__(self, target_path: str) -> None:
        self._target = target_path

    def get_classification(self, _node_id: str, field_path: str):
        if field_path == self._target:
            return "REDACT"
        return None


class _NestedWrapperRedactPolicy:
    """REDACT the wrapper itself (``customer``) — verifies that
    wrapper-level tagging still replaces the entire subtree.  This is
    the pre-W6-round-2 behavior baseline; the test guards against a
    future refactor that accidentally narrows it.
    """

    def get_classification(self, _node_id: str, field_path: str):
        if field_path == "customer":
            return "REDACT"
        return None


def _build_nested_workflow(payload_code: str):
    """One-node PythonCodeNode workflow whose output emits nested
    dicts and lists under PythonCodeNode's ``result`` wrapper."""
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "leak_node", {"code": payload_code})
    return wb.build()


@pytest.mark.integration
async def test_redact_event_persistence_nested_dict_leaf_redacted(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """A nested-leaf classified field MUST be replaced by the
    [REDACTED] sentinel while UNCLASSIFIED siblings AND the wrapper
    survive verbatim.  Pre-W6-round-2 the persisted blob carried the
    raw nested SSN because the helper iterated only top-level keys.
    """
    raw_ssn = "555-12-3456-DO-NOT-LEAK"
    public_name = "Alice-public-survives"
    workflow = _build_nested_workflow(
        f"result = {{'customer': {{'ssn': '{raw_ssn}', 'name': '{public_name}'}}}}"
    )
    idempotency_key = f"async_nested_leaf_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = _NestedLeafRedactPolicy(  # noqa: SLF001
        "result.customer.ssn"
    )

    await runtime.execute_workflow_async(
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

    assert raw_ssn.encode("utf-8") not in blob, (
        "Raw nested SSN leaked to checkpoint blob — recursive "
        "redaction did not redact result.customer.ssn at depth 3."
    )
    assert b"[REDACTED]" in blob, (
        "Sentinel missing from checkpoint blob — recursive helper " "did not run."
    )
    # Unclassified sibling at the same depth survives.
    assert public_name.encode("utf-8") in blob, (
        "Sibling result.customer.name was over-redacted — recursive "
        "helper is touching fields outside the policy's scope."
    )

    # Decoded shape: the wrapper dict survives; only the leaf is sentinel.
    decoded = decode_checkpoint_payload(blob)
    leak_outputs = decoded["tracker"]["node_outputs"].get("leak_node", {})
    customer = leak_outputs.get("result", {}).get("customer", {})
    assert customer.get("ssn") == "[REDACTED]"
    assert customer.get("name") == public_name


@pytest.mark.integration
async def test_redact_event_persistence_nested_dict_wrapper_redacted(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """When the WRAPPER is tagged (``result.customer``), the entire
    subtree MUST be replaced — neither the leaf nor the sibling
    survives.  Backwards-compat with pre-W6-round-2 wrapper-only
    tagging behavior; locks it as a contract.
    """
    raw_ssn = "888-12-3456-DO-NOT-LEAK"
    raw_name = "should-also-be-gone"
    workflow = _build_nested_workflow(
        f"result = {{'customer': {{'ssn': '{raw_ssn}', 'name': '{raw_name}'}}, 'public_field': 'OK'}}"
    )
    idempotency_key = f"async_nested_wrapper_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    class _ResultCustomerWrapperPolicy:
        def get_classification(self, _node_id: str, field_path: str):
            if field_path == "result.customer":
                return "REDACT"
            return None

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = _ResultCustomerWrapperPolicy()  # noqa: SLF001

    await runtime.execute_workflow_async(
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

    # Both nested leaves gone (whole subtree replaced).
    assert raw_ssn.encode("utf-8") not in blob
    assert raw_name.encode("utf-8") not in blob
    # Sibling top-level field survives.
    assert b"OK" in blob

    # Decoded: result.customer is the literal sentinel string.
    decoded = decode_checkpoint_payload(blob)
    leak_outputs = decoded["tracker"]["node_outputs"].get("leak_node", {})
    assert leak_outputs.get("result", {}).get("customer") == "[REDACTED]"
    assert leak_outputs.get("result", {}).get("public_field") == "OK"


@pytest.mark.integration
async def test_redact_event_persistence_nested_list_index_redacted(
    pg_conn: ConnectionManager,
    checkpoint_store: DBCheckpointStore,
):
    """A classified field inside a list item MUST be redacted via
    indexed path (``items.0.password``).  Pre-W6-round-2 lists were
    invisible to the helper — every list-of-dicts shape silently
    leaked classified fields.  Pins recursion through Sequence values.
    """
    raw_pwd = "shared-secret-pwd-XYZ-789"
    public_user = "username-survives"
    workflow = _build_nested_workflow(
        f"result = {{'items': [{{'password': '{raw_pwd}', 'username': '{public_user}'}}]}}"
    )
    idempotency_key = f"async_nested_list_{uuid.uuid4().hex[:8]}"
    fingerprint = compute_workflow_fingerprint(workflow)
    expected_key = build_checkpoint_key(fingerprint, idempotency_key, None)

    class _ListIndexRedactPolicy:
        def get_classification(self, _node_id: str, field_path: str):
            if field_path == "result.items.0.password":
                return "REDACT"
            return None

    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = _ListIndexRedactPolicy()  # noqa: SLF001

    await runtime.execute_workflow_async(
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

    assert raw_pwd.encode("utf-8") not in blob, (
        "Raw password in list item leaked to checkpoint blob — list "
        "recursion did not run on result.items.0.password."
    )
    assert public_user.encode("utf-8") in blob, (
        "Sibling username field over-redacted; list recursion " "exceeded policy scope."
    )
    assert b"[REDACTED]" in blob

    # Decoded: items[0].password is sentinel, items[0].username is raw.
    decoded = decode_checkpoint_payload(blob)
    leak_outputs = decoded["tracker"]["node_outputs"].get("leak_node", {})
    items = leak_outputs.get("result", {}).get("items", [])
    assert len(items) == 1
    assert items[0].get("password") == "[REDACTED]"
    assert items[0].get("username") == public_user
