# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``kailash.runtime.durable``.

Covers the W1 helpers in isolation — frozen-event immutability, shape-drift
refusal semantics, multi-subscriber dispatch, deterministic fingerprints,
checkpoint-key stability, classification-aware redaction, and tenant-id
resolution.  Each test is a behavioural call against the helper, not a
source-grep — see ``rules/testing.md`` § "Behavioral Regression Tests".
"""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone

import pytest

from kailash.runtime.durable import (
    NodeCompletionEvent,
    NodeCompletionHookRegistry,
    WorkflowShapeDriftError,
    build_checkpoint_key,
    check_shape_drift_or_raise,
    compute_workflow_fingerprint,
    decode_checkpoint_payload,
    encode_checkpoint_payload,
    redact_event_for_persistence,
    resolve_tenant_id,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(**overrides) -> NodeCompletionEvent:
    """Build a NodeCompletionEvent with sensible defaults for testing."""
    base = {
        "run_id": "run_test",
        "workflow_id": "wf_demo",
        "workflow_fingerprint": "f" * 64,
        "node_id": "node_a",
        "node_type": "PythonCodeNode",
        "outputs": {"result": 42},
        "started_at": datetime(2026, 5, 6, 12, 0, 0, tzinfo=timezone.utc),
        "ended_at": datetime(2026, 5, 6, 12, 0, 1, tzinfo=timezone.utc),
        "duration_ms": 1000,
        "tenant_id": None,
        "idempotency_key": None,
        "error": None,
        "metadata": {},
    }
    base.update(overrides)
    return NodeCompletionEvent(**base)


class _FakeGraph:
    """Minimal graph stand-in that exposes nodes() + edges() iter."""

    def __init__(self, nodes, edges):
        self._nodes = list(nodes)
        self._edges = list(edges)

    def nodes(self):
        return list(self._nodes)

    def edges(self):
        return list(self._edges)


def _make_fake_node(kind: str):
    """Build an instance of a dynamic class whose class name is ``kind``.

    The fingerprint reads ``node_instance.__class__.__name__`` so we MUST
    produce instances of distinct classes — assigning to ``self.__class__.__name__``
    doesn't work because ``__name__`` lives on the class, not the instance.
    """
    cls = type(kind, (), {})
    return cls()


class _FakeWorkflow:
    """Stand-in workflow that satisfies compute_workflow_fingerprint."""

    def __init__(self, nodes, edges, types):
        self.graph = _FakeGraph(nodes, edges)
        self._node_instances = {n: _make_fake_node(types.get(n, "Node")) for n in nodes}


# ---------------------------------------------------------------------------
# 1. NodeCompletionEvent immutability
# ---------------------------------------------------------------------------


def test_node_completion_event_immutable():
    """Mutating any field on a frozen NodeCompletionEvent raises."""
    event = _make_event()
    with pytest.raises(dataclasses.FrozenInstanceError):
        event.node_id = "different"  # type: ignore[misc]


def test_node_completion_event_round_trips_via_dict():
    """to_dict/from_dict preserves event identity for downstream serialise."""
    event = _make_event(metadata={"trace_id": "abc"})
    rebuilt = NodeCompletionEvent.from_dict(event.to_dict())
    assert rebuilt.node_id == event.node_id
    assert rebuilt.workflow_fingerprint == event.workflow_fingerprint
    assert rebuilt.duration_ms == event.duration_ms
    assert rebuilt.metadata == {"trace_id": "abc"}
    assert rebuilt.started_at == event.started_at


# ---------------------------------------------------------------------------
# 2. WorkflowShapeDriftError + force override
# ---------------------------------------------------------------------------


def test_workflow_shape_drift_error_raises_by_default():
    stored_payload = {"workflow_fingerprint": "old_fp_12345", "tracker": {}}
    with pytest.raises(WorkflowShapeDriftError) as excinfo:
        check_shape_drift_or_raise(
            idempotency_key="user_key",
            stored_payload=stored_payload,
            current_fingerprint="new_fp_67890",
            force_resume_with_drift=False,
        )
    # The error MUST surface BOTH fingerprints + the override mechanism.
    assert "force_resume_with_drift=True" in str(excinfo.value)
    assert excinfo.value.idempotency_key == "user_key"
    assert excinfo.value.stored_fingerprint == "old_fp_12345"
    assert excinfo.value.current_fingerprint == "new_fp_67890"


def test_workflow_shape_drift_force_override_proceeds():
    """force_resume_with_drift=True silences the refusal."""
    stored_payload = {"workflow_fingerprint": "old_fp_12345", "tracker": {}}
    # MUST not raise.
    check_shape_drift_or_raise(
        idempotency_key="user_key",
        stored_payload=stored_payload,
        current_fingerprint="new_fp_67890",
        force_resume_with_drift=True,
    )


def test_workflow_shape_drift_passes_when_fingerprints_match():
    stored_payload = {"workflow_fingerprint": "same_fp", "tracker": {}}
    check_shape_drift_or_raise(
        idempotency_key="user_key",
        stored_payload=stored_payload,
        current_fingerprint="same_fp",
        force_resume_with_drift=False,
    )


# ---------------------------------------------------------------------------
# 3. Hook registry — multi-subscriber, mixed sync + async
# ---------------------------------------------------------------------------


def test_hook_registry_multi_subscriber_dispatch():
    """3 sync + 2 async subscribers all receive each event."""
    registry = NodeCompletionHookRegistry()
    received: list[tuple[str, str]] = []

    def sync_a(event: NodeCompletionEvent) -> None:
        received.append(("sync_a", event.node_id))

    def sync_b(event: NodeCompletionEvent) -> None:
        received.append(("sync_b", event.node_id))

    def sync_c(event: NodeCompletionEvent) -> None:
        received.append(("sync_c", event.node_id))

    async def async_a(event: NodeCompletionEvent) -> None:
        received.append(("async_a", event.node_id))

    async def async_b(event: NodeCompletionEvent) -> None:
        received.append(("async_b", event.node_id))

    for cb in (sync_a, sync_b, sync_c, async_a, async_b):
        registry.register(cb)

    event = _make_event(node_id="dispatched")
    asyncio.run(registry.dispatch_async(event))

    assert registry.subscriber_count == 5
    # All five subscribers ran in registration order.
    names = [name for name, _ in received]
    assert names == ["sync_a", "sync_b", "sync_c", "async_a", "async_b"]
    assert all(node_id == "dispatched" for _, node_id in received)


def test_hook_registry_subscriber_failure_does_not_abort_dispatch():
    """One subscriber raising MUST not prevent siblings from receiving."""
    registry = NodeCompletionHookRegistry()
    received: list[str] = []

    def failing(event: NodeCompletionEvent) -> None:
        raise RuntimeError("subscriber-broke")

    def succeeding(event: NodeCompletionEvent) -> None:
        received.append(event.node_id)

    registry.register(failing)
    registry.register(succeeding)

    asyncio.run(registry.dispatch_async(_make_event(node_id="ok")))
    assert received == ["ok"]


# ---------------------------------------------------------------------------
# 4. Workflow fingerprint — deterministic, shape-sensitive
# ---------------------------------------------------------------------------


def test_compute_workflow_fingerprint_deterministic_same_shape():
    wf1 = _FakeWorkflow(
        nodes=["a", "b", "c"],
        edges=[("a", "b"), ("b", "c")],
        types={"a": "X", "b": "Y", "c": "Z"},
    )
    wf2 = _FakeWorkflow(
        nodes=["a", "b", "c"],
        edges=[("a", "b"), ("b", "c")],
        types={"a": "X", "b": "Y", "c": "Z"},
    )
    assert compute_workflow_fingerprint(wf1) == compute_workflow_fingerprint(wf2)


def test_compute_workflow_fingerprint_differs_on_extra_node():
    wf1 = _FakeWorkflow(
        nodes=["a", "b"],
        edges=[("a", "b")],
        types={"a": "X", "b": "Y"},
    )
    wf2 = _FakeWorkflow(
        nodes=["a", "b", "c"],
        edges=[("a", "b"), ("b", "c")],
        types={"a": "X", "b": "Y", "c": "Z"},
    )
    assert compute_workflow_fingerprint(wf1) != compute_workflow_fingerprint(wf2)


def test_compute_workflow_fingerprint_differs_on_node_type_change():
    wf1 = _FakeWorkflow(
        nodes=["a", "b"], edges=[("a", "b")], types={"a": "X", "b": "Y"}
    )
    wf2 = _FakeWorkflow(
        nodes=["a", "b"], edges=[("a", "b")], types={"a": "X", "b": "Y_v2"}
    )
    assert compute_workflow_fingerprint(wf1) != compute_workflow_fingerprint(wf2)


# ---------------------------------------------------------------------------
# 5. Checkpoint key — stability + parameter-sensitivity
# ---------------------------------------------------------------------------


def test_build_checkpoint_key_stable_for_same_inputs():
    fp = "f" * 64
    k1 = build_checkpoint_key(fp, "user_key", {"a": 1, "b": 2})
    k2 = build_checkpoint_key(fp, "user_key", {"b": 2, "a": 1})  # key order
    assert k1 == k2


def test_build_checkpoint_key_differs_on_different_parameters():
    fp = "f" * 64
    k1 = build_checkpoint_key(fp, "user_key", {"a": 1})
    k2 = build_checkpoint_key(fp, "user_key", {"a": 2})
    assert k1 != k2


def test_build_checkpoint_key_partitions_on_tenant():
    fp = "f" * 64
    k1 = build_checkpoint_key(fp, "user_key", {"a": 1}, tenant_id="tenant_alpha")
    k2 = build_checkpoint_key(fp, "user_key", {"a": 1}, tenant_id="tenant_beta")
    assert k1 != k2


def test_build_checkpoint_key_rejects_empty_inputs():
    with pytest.raises(ValueError):
        build_checkpoint_key("", "user_key", {})
    with pytest.raises(ValueError):
        build_checkpoint_key("f" * 64, "", {})


# ---------------------------------------------------------------------------
# 6. Redaction — classified PK hashed, classified field count partition
# ---------------------------------------------------------------------------


class _PolicyHashesPK:
    """Stub policy that returns HASH_PK for the configured field name."""

    def __init__(self, target_node: str, target_field: str) -> None:
        self._node = target_node
        self._field = target_field

    def get_classification(self, node_id: str, field_name: str):
        if node_id == self._node and field_name == self._field:
            return "HASH_PK"
        return None


class _PolicyRedactsField:
    """Stub policy that REDACTs the configured (node, field) AND HASH_PKs another."""

    def __init__(self, redact_pairs, hash_pairs) -> None:
        self._redact = set(redact_pairs)
        self._hash = set(hash_pairs)

    def get_classification(self, node_id: str, field_name: str):
        if (node_id, field_name) in self._redact:
            return "REDACT"
        if (node_id, field_name) in self._hash:
            return "HASH_PK"
        return None


def test_redact_event_classified_pk_hashed():
    """Classified PKs are hashed via the format_record_id_for_event contract."""
    event = _make_event(
        node_id="users_read",
        outputs={"id": "user-12345", "email": "alice@example.com"},
    )
    policy = _PolicyHashesPK("users_read", "id")
    redacted = redact_event_for_persistence(event, classification_policy=policy)
    assert redacted.outputs["id"].startswith("pk:")
    assert redacted.outputs["id"] != "user-12345"
    # Untouched field passes through unchanged.
    assert redacted.outputs["email"] == "alice@example.com"


def test_redact_event_classified_field_count_partition():
    """Classified field NAMES partition into (unclassified_fields, count) summary.

    Per rules/event-payload-classification.md MUST Rule 3 — classified
    field NAMES are NOT in the summary, only the count is.
    """
    event = _make_event(
        node_id="users_read",
        outputs={
            "id": "user-12345",
            "ssn": "123-45-6789",
            "name": "Alice",
            "email": "alice@example.com",
        },
    )
    policy = _PolicyRedactsField(
        redact_pairs={("users_read", "ssn")},
        hash_pairs={("users_read", "id")},
    )
    redacted = redact_event_for_persistence(event, classification_policy=policy)

    summary = redacted.metadata["classification_summary"]
    assert sorted(summary["unclassified_fields"]) == ["email", "name"]
    assert summary["classified_field_count"] == 2
    # The classified field names "ssn" and "id" MUST NOT be in the summary
    # itself — only the count is.  Schema-level identifiers stay out of
    # operator-facing logs per rules/observability.md Rule 8.
    assert "ssn" not in summary["unclassified_fields"]
    assert "id" not in summary["unclassified_fields"]
    # And the values themselves are redacted/hashed in outputs.
    assert redacted.outputs["ssn"] == "[REDACTED]"
    assert redacted.outputs["id"].startswith("pk:")


def test_redact_event_no_policy_returns_event_unchanged():
    event = _make_event(outputs={"id": "raw"})
    out = redact_event_for_persistence(event, classification_policy=None)
    assert out is event  # same instance when no policy


# ---------------------------------------------------------------------------
# 7. Tenant ID resolution
# ---------------------------------------------------------------------------


class _RuntimeWithTenant:
    class _Ctx:
        tenant_id = "tenant_42"

    user_context = _Ctx()


class _RuntimeNoTenant:
    user_context = None


def test_resolve_tenant_id_extracts_from_runtime_context():
    assert resolve_tenant_id(_RuntimeWithTenant()) == "tenant_42"


def test_resolve_tenant_id_returns_none_when_absent():
    assert resolve_tenant_id(_RuntimeNoTenant()) is None


# ---------------------------------------------------------------------------
# 8. Encode / decode round-trip
# ---------------------------------------------------------------------------


def test_encode_decode_checkpoint_payload_roundtrip():
    blob = encode_checkpoint_payload(
        workflow_fingerprint="f" * 64,
        tracker_state={"completed_nodes": ["a"], "node_outputs": {"a": {"result": 1}}},
        tenant_id="tenant_alpha",
        workflow_id="wf_demo",
        idempotency_key="user_key",
    )
    payload = decode_checkpoint_payload(blob)
    assert payload["workflow_fingerprint"] == "f" * 64
    assert payload["tenant_id"] == "tenant_alpha"
    assert payload["tracker"]["completed_nodes"] == ["a"]


def test_decode_checkpoint_payload_rejects_corrupt_blob():
    with pytest.raises(ValueError, match="UTF-8 JSON"):
        decode_checkpoint_payload(b"\x00\x01not-json")
