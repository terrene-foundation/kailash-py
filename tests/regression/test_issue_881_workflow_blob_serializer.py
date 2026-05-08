# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #881 — DurableExecutionEngine workflow_blob serializer.

Pre-fix: ``DurableExecutionEngine._enqueue_for_run`` constructed
``Task(workflow_blob=b"", ...)`` because the engine had no built-in
serializer for arbitrary workflow objects. Workers picking up a
dispatched task from the underlying ``SQLTaskQueue`` could not
reconstruct the workflow without out-of-band knowledge — the canonical
JSON contract (already used by :class:`WorkflowScheduler`) was the
unimplemented half of the contract.

Post-fix: both producer surfaces (``WorkflowScheduler`` and
``DurableExecutionEngine``) route through the shared
``runtime/_workflow_blob.py`` helper. ``Task.workflow_blob`` is now
JSON-encoded UTF-8 bytes that workers reconstruct via
``Workflow.from_dict(json.loads(blob.decode("utf-8")))``.

The contract is additive: workers using the prior local-registry
convention keep working (they ignore ``workflow_blob``); workers that
need to reconstruct without out-of-band knowledge now have JSON to
parse.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Optional, Tuple

import pytest

from kailash.runtime._workflow_blob import serialize_workflow_to_blob
from kailash.runtime.durable import DurableExecutionEngine
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Deterministic protocol-satisfying adapters (Tier-1 per testing.md exception)
# ---------------------------------------------------------------------------


class _FakeRuntime:
    """Records ``execute_workflow_async`` invocations.

    The harness does NOT exercise the wrapped runtime's behaviour —
    issue #881 is about the dispatcher-side payload contract — but the
    engine's auto-detected ``both`` mode still calls the runtime, so
    the adapter records calls without producing useful state.
    """

    def __init__(self, **kwargs: Any) -> None:
        self.constructor_kwargs: Dict[str, Any] = dict(kwargs)
        self.execute_calls: List[Dict[str, Any]] = []

    async def execute_workflow_async(
        self,
        workflow: Any,
        inputs: Mapping[str, Any],
        *,
        idempotency_key: Optional[str] = None,
        force_resume_with_drift: bool = False,
    ) -> Tuple[Dict[str, Any], str]:
        self.execute_calls.append(
            {
                "workflow": workflow,
                "inputs": dict(inputs),
                "idempotency_key": idempotency_key,
                "force_resume_with_drift": force_resume_with_drift,
            }
        )
        return {"step1": {"result": {"value": 1}}}, "run_fake_001"


class _RecordingDispatcher:
    """Records ``enqueue`` calls; the captured ``Task`` is the test surface."""

    def __init__(self) -> None:
        self.enqueued: List[Any] = []

    async def enqueue(self, task: Any) -> None:
        self.enqueued.append(task)

    def poll(self, _queue_name: str = "default"):  # pragma: no cover - unused
        async def _empty():
            if False:  # pragma: no cover
                yield None

        return _empty()

    async def ack(self, _task_id: str) -> None:  # pragma: no cover - unused
        return None

    async def nack(self, _task_id: str, *, _reason: str) -> None:
        # pragma: no cover - unused
        return None


def _build_minimal_workflow():
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "step1", {"code": "result = {'value': 1}"})
    return wb.build()


# ---------------------------------------------------------------------------
# Tier-1 structural invariants — workflow_blob is no longer empty
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_881_workflow_blob_populated_by_durable_engine():
    """``Task.workflow_blob`` MUST be non-empty UTF-8 JSON bytes.

    Pre-fix invariant the engine violated: empty ``b""`` blob; workers
    cannot reconstruct without out-of-band knowledge. Post-fix: blob
    decodes to a JSON dict whose top-level keys describe the workflow.
    """
    dispatcher = _RecordingDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .dispatch_via(dispatcher)
        .execution_mode("dispatch_only")
        .build()
    )

    workflow = _build_minimal_workflow()
    await engine.execute(workflow, inputs={}, idempotency_key="iss881-pop")

    assert len(dispatcher.enqueued) == 1
    task = dispatcher.enqueued[0]
    assert isinstance(task.workflow_blob, bytes)
    assert task.workflow_blob != b"", (
        "issue #881 regression: workflow_blob is the pre-fix empty bytes, "
        "indicating _enqueue_for_run reverted to the old ``b''`` punt."
    )
    decoded = json.loads(task.workflow_blob.decode("utf-8"))
    assert isinstance(decoded, dict)
    assert "nodes" in decoded


# ---------------------------------------------------------------------------
# Byte-parity — both producer paths emit identical bytes for the same workflow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_881_byte_parity_durable_engine_matches_canonical_helper():
    """Engine-produced bytes MUST equal the shared helper's output.

    Multi-site drift defense per ``rules/security.md`` § "Multi-Site
    Kwarg Plumbing": both producers route through
    :func:`serialize_workflow_to_blob`, so the bytes that land in the
    queue MUST match the helper called directly. If the engine grew a
    parallel inline serializer, the two bytestrings would diverge and
    workers would see different shapes from different producers.
    """
    dispatcher = _RecordingDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .dispatch_via(dispatcher)
        .execution_mode("dispatch_only")
        .build()
    )

    workflow = _build_minimal_workflow()
    expected_blob = serialize_workflow_to_blob(workflow)

    await engine.execute(workflow, inputs={}, idempotency_key="iss881-parity")

    assert len(dispatcher.enqueued) == 1
    task = dispatcher.enqueued[0]
    assert task.workflow_blob == expected_blob


# ---------------------------------------------------------------------------
# Cross-process worker replay — JSON contract end-to-end
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_881_worker_visible_blob_carries_workflow_topology():
    """A worker dequeues bytes that decode to the workflow's topology.

    Simulates the cross-process worker scenario from issue #881: a worker
    on a separate host dequeues the task, has no access to the
    orchestrator's local registry, decodes ``workflow_blob`` via
    ``json.loads(blob.decode("utf-8"))``, and sees the workflow's
    nodes + connections. The producer-side contract this test pins is
    "the dispatched bytes carry the topology"; the consumer-side
    ``Workflow.from_dict`` reconstruction has independent completeness
    constraints (some node types' runtime config is not preserved by
    ``to_dict``) that are out of scope for issue #881.
    """
    dispatcher = _RecordingDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .dispatch_via(dispatcher)
        .execution_mode("dispatch_only")
        .build()
    )

    builder = WorkflowBuilder()
    builder.add_node(
        "PythonCodeNode",
        "compute",
        {"code": "result = {'value': inputs.get('seed', 0) + 1}"},
    )
    workflow = builder.build()

    await engine.execute(workflow, inputs={"seed": 41}, idempotency_key="iss881-worker")

    task = dispatcher.enqueued[0]
    # The worker's view: a bytes payload, no out-of-band registry access.
    blob_dict = json.loads(task.workflow_blob.decode("utf-8"))

    assert "compute" in blob_dict.get("nodes", {}), (
        "Worker dequeueing the task MUST see the producer's node "
        "topology — pre-fix the blob was b'' and workers had nothing "
        "to inspect."
    )
    assert blob_dict["nodes"]["compute"]["node_type"] == "PythonCodeNode"
    assert "connections" in blob_dict
