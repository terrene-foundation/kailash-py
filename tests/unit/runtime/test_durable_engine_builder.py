# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Tier-1 unit tests for ``DurableExecutionEngine`` + ``DurableExecutionEngineBuilder``.

Per ``rules/testing.md`` 3-Tier: Tier 1 unit tests verify the builder
fluent chain, missing-primitive defaults, idempotency-default forwarding,
and the engine's no-parallel-impl contract WITHOUT touching real
infrastructure. Each test pairs the engine against a deterministic
in-memory protocol-satisfying adapter (per the testing.md exception for
``typing.Protocol``-satisfying deterministic adapters) so the unit tier
remains offline + fast while still exercising the real composition path.

What is NOT covered here (lives in
``tests/integration/test_durable_execution_engine_wiring.py``):

* Real Postgres history rows / events
* Real DBCheckpointStore blob persistence
* Real SQLTaskQueue dispatch via the W3 path

What IS covered here:

* Builder is fluent and immutable after build (build returns a new instance)
* Each setter overrides the prior value (no implicit fan-in)
* Engine construction wires every primitive into the runtime kwargs
* Engine construction with ZERO primitives still produces a working engine
* ``execute(idempotency_key=)`` falls back to ``idempotency_key_default``
* The engine forwards ``execute_workflow_async`` correctly (delegate-only,
  no parallel state machine)
* ``runtime_kwargs`` are forwarded; conflicting checkpoint/history kwargs
  are overridden at build time (composition contract)
* Type-validation gates raise typed errors, not opaque ``AttributeError``
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

import pytest

from kailash.runtime.durable import (
    DurableExecutionEngine,
    DurableExecutionEngineBuilder,
    NodeCompletionEvent,
)
from kailash.workflow.builder import WorkflowBuilder


def _build_minimal_workflow():
    """Construct a minimal real workflow with a `.graph` attribute.

    The dispatcher path computes ``compute_workflow_fingerprint`` which
    requires the real ``Workflow`` shape — opaque sentinels do not work.
    """
    wb = WorkflowBuilder()
    wb.add_node("PythonCodeNode", "step1", {"code": "result = {'value': 1}"})
    return wb.build()


# ---------------------------------------------------------------------------
# Deterministic protocol-satisfying adapters
# ---------------------------------------------------------------------------
#
# Per ``rules/testing.md`` § "3-Tier Testing" — Protocol Adapters exception:
# a class satisfying a typing.Protocol at runtime with deterministic output
# is NOT a mock. These adapters let Tier 1 unit tests verify the engine's
# composition contract (which kwargs flow where, what overrides what) without
# touching ConnectionManager / Postgres / SQLite.


class _FakeRuntime:
    """A minimal AsyncLocalRuntime-shaped runtime that records calls.

    Captures the kwargs the engine passes to ``execute_workflow_async``
    so tests can verify forwarding semantics. The factory shape mirrors
    ``AsyncLocalRuntime(**kwargs)``.
    """

    def __init__(self, **kwargs: Any) -> None:
        # Capture engine-supplied construction kwargs.
        self.constructor_kwargs: Dict[str, Any] = dict(kwargs)
        self.execute_calls: List[Dict[str, Any]] = []
        self._next_results: Dict[str, Any] = {"node_a": {"value": 1}}
        self._next_run_id: str = "run_fake_001"

    async def execute_workflow_async(
        self,
        workflow: Any,
        inputs: Mapping[str, Any],
        *,
        idempotency_key: Optional[str] = None,
        force_resume_with_drift: bool = False,
        soft_time_limit: float | None = None,
        time_limit: float | None = None,
    ) -> Tuple[Dict[str, Any], str]:
        # Record what the engine forwarded so the tests can assert
        # delegate-only behaviour (no parallel state machine).
        # soft_time_limit / time_limit recorded per #912 Shard 1 contract;
        # the fake mirrors the AsyncLocalRuntime.execute_workflow_async
        # Protocol surface that engine forwards through.
        self.execute_calls.append(
            {
                "workflow": workflow,
                "inputs": dict(inputs),
                "idempotency_key": idempotency_key,
                "force_resume_with_drift": force_resume_with_drift,
                "soft_time_limit": soft_time_limit,
                "time_limit": time_limit,
            }
        )
        return self._next_results, self._next_run_id


class _FakeHistoryStore:
    """Deterministic history-store adapter — captures recorded events."""

    def __init__(self) -> None:
        self.records: List[NodeCompletionEvent] = []
        # The store API the engine surfaces via ``engine.history``:
        self.list_runs_calls: List[Dict[str, Any]] = []
        self.get_run_calls: List[Dict[str, Any]] = []

    async def record_event(self, event: NodeCompletionEvent) -> None:
        self.records.append(event)

    async def list_runs(
        self,
        *,
        filter: Optional[Mapping[str, Any]] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        self.list_runs_calls.append(
            {"filter": dict(filter or {}), "limit": limit, "offset": offset}
        )
        return []

    async def get_run(
        self, run_id: str, *, tenant_id: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        self.get_run_calls.append({"run_id": run_id, "tenant_id": tenant_id})
        return None


class _FakeCheckpointStore:
    """Deterministic checkpoint-store adapter — protocol shape only."""

    def __init__(self) -> None:
        self.saves: List[Tuple[str, bytes]] = []
        self.loads: List[str] = []

    async def save(self, key: str, data: bytes) -> None:
        self.saves.append((key, data))

    async def load(self, key: str) -> Optional[bytes]:
        self.loads.append(key)
        return None


class _FakeDispatcher:
    """Deterministic Dispatcher adapter — captures enqueue calls."""

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


# ---------------------------------------------------------------------------
# Builder — fluent chain + override semantics
# ---------------------------------------------------------------------------


def test_builder_returns_self_for_fluent_chain():
    """Each setter MUST return the builder so the chain is one expression."""
    builder = DurableExecutionEngine.builder()
    out = (
        builder.checkpoint_store(_FakeCheckpointStore())
        .history_store(_FakeHistoryStore())
        .dispatch_via(_FakeDispatcher())
        .idempotency_key_default("default-key")
        .runtime(_FakeRuntime)
    )
    assert out is builder, "fluent setters must return the builder itself"


def test_builder_setter_overrides_prior_value():
    """Calling a setter twice MUST override (not merge) the prior value."""
    first = _FakeHistoryStore()
    second = _FakeHistoryStore()
    builder = (
        DurableExecutionEngine.builder()
        .history_store(first)
        .history_store(second)
        .runtime(_FakeRuntime)
    )
    engine = builder.build()
    assert engine.history is second, "second setter call must win"
    assert engine.history is not first, "prior value must be overridden"


def test_builder_idempotency_key_default_validates_type():
    """Type validation: non-str non-None is a TypeError, not opaque AttributeError."""
    builder = DurableExecutionEngine.builder()
    with pytest.raises(TypeError, match="must be str or None"):
        builder.idempotency_key_default(42)  # type: ignore[arg-type]


def test_builder_runtime_factory_validates_callable():
    """Type validation: non-callable factory is rejected with a typed error."""
    builder = DurableExecutionEngine.builder()
    with pytest.raises(TypeError, match="must be callable"):
        builder.runtime("not a callable")  # type: ignore[arg-type]


def test_builder_runtime_kwargs_validates_mapping():
    """Type validation: non-Mapping kwargs is rejected."""
    builder = DurableExecutionEngine.builder()
    with pytest.raises(TypeError, match="must be a Mapping"):
        builder.runtime_kwargs("max_concurrent=10")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Construction — every primitive optional
# ---------------------------------------------------------------------------


def test_engine_construction_with_zero_primitives():
    """An engine with no stores / no dispatcher MUST still build cleanly.

    The minimum viable composition is just a runtime — the engine
    degrades to the default AsyncLocalRuntime behaviour.
    """
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    assert engine.checkpoint_store is None
    assert engine.history is None
    assert engine.dispatcher is None
    assert engine.idempotency_key_default is None
    # The wrapped runtime exists and is the fake one.
    assert isinstance(engine.runtime, _FakeRuntime)
    # No checkpoint/history kwargs were forwarded since neither was set.
    assert "checkpoint_store" not in engine.runtime.constructor_kwargs
    assert "history_store" not in engine.runtime.constructor_kwargs


def test_engine_construction_with_only_checkpoint_store():
    """Engine with checkpoint store only — checkpoint_after_each_node defaults to True."""
    cp = _FakeCheckpointStore()
    engine = (
        DurableExecutionEngine.builder()
        .checkpoint_store(cp)
        .runtime(_FakeRuntime)
        .build()
    )
    assert engine.checkpoint_store is cp
    # The W1 contract requires BOTH the store AND the opt-in flag.
    kwargs = engine.runtime.constructor_kwargs
    assert kwargs["checkpoint_store"] is cp
    assert kwargs["checkpoint_after_each_node"] is True
    # No history wiring happened.
    assert "history_store" not in kwargs


def test_engine_construction_with_only_history_store():
    """Engine with history store only — runtime auto-subscribes record_event."""
    hs = _FakeHistoryStore()
    engine = (
        DurableExecutionEngine.builder().history_store(hs).runtime(_FakeRuntime).build()
    )
    assert engine.history is hs
    kwargs = engine.runtime.constructor_kwargs
    assert kwargs["history_store"] is hs
    # No checkpoint wiring happened.
    assert "checkpoint_store" not in kwargs


def test_engine_construction_with_only_dispatcher():
    """Engine with dispatcher only — checkpoint/history kwargs absent."""
    disp = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .dispatch_via(disp)
        .runtime(_FakeRuntime)
        .build()
    )
    assert engine.dispatcher is disp
    kwargs = engine.runtime.constructor_kwargs
    assert "checkpoint_store" not in kwargs
    assert "history_store" not in kwargs


def test_engine_construction_with_all_primitives():
    """Full composition — every primitive flows to the right place."""
    cp = _FakeCheckpointStore()
    hs = _FakeHistoryStore()
    disp = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .checkpoint_store(cp)
        .history_store(hs)
        .dispatch_via(disp)
        .idempotency_key_default("user-42")
        .runtime(_FakeRuntime)
        .build()
    )
    assert engine.checkpoint_store is cp
    assert engine.history is hs
    assert engine.dispatcher is disp
    assert engine.idempotency_key_default == "user-42"
    kwargs = engine.runtime.constructor_kwargs
    assert kwargs["checkpoint_store"] is cp
    assert kwargs["checkpoint_after_each_node"] is True
    assert kwargs["history_store"] is hs


def test_runtime_kwargs_forwarded_but_overridden_by_primitive_wiring():
    """``runtime_kwargs`` forwards extra construction args, BUT primitive
    wiring (checkpoint_store, history_store) wins when both are set.
    """
    cp = _FakeCheckpointStore()
    hs = _FakeHistoryStore()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .runtime_kwargs(
            {
                "max_concurrent_nodes": 5,
                # These conflict with the primitive setters — primitive setters MUST win.
                "checkpoint_store": _FakeCheckpointStore(),
                "history_store": _FakeHistoryStore(),
            }
        )
        .checkpoint_store(cp)
        .history_store(hs)
        .build()
    )
    kwargs = engine.runtime.constructor_kwargs
    # Custom non-conflicting kwarg flows through.
    assert kwargs["max_concurrent_nodes"] == 5
    # Primitive setters override conflicting runtime_kwargs entries (via setdefault).
    # The primitives go in FIRST when set, so runtime_kwargs cannot displace them.
    assert kwargs["checkpoint_store"] is cp
    assert kwargs["history_store"] is hs


def test_runtime_factory_must_return_compatible_runtime():
    """A factory returning a non-runtime object raises a typed error."""

    class _BadRuntime:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        # Intentionally lacks execute_workflow_async.

    with pytest.raises(TypeError, match="execute_workflow_async"):
        DurableExecutionEngine.builder().runtime(_BadRuntime).build()


# ---------------------------------------------------------------------------
# Execute — delegate-only, no parallel state machine
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_forwards_idempotency_key_to_runtime():
    """Engine.execute(idempotency_key=...) MUST forward to the runtime."""
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    workflow = object()  # opaque sentinel — runtime is fake, doesn't introspect
    results, run_id = await engine.execute(
        workflow, idempotency_key="explicit-key", inputs={"x": 1}
    )
    assert results == {"node_a": {"value": 1}}
    assert run_id == "run_fake_001"
    assert len(engine.runtime.execute_calls) == 1
    call = engine.runtime.execute_calls[0]
    assert call["idempotency_key"] == "explicit-key"
    assert call["inputs"] == {"x": 1}
    assert call["force_resume_with_drift"] is False


@pytest.mark.asyncio
async def test_execute_falls_back_to_idempotency_key_default():
    """Omitting idempotency_key uses the builder default."""
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .idempotency_key_default("builder-default")
        .build()
    )
    await engine.execute(object(), inputs={})
    assert engine.runtime.execute_calls[0]["idempotency_key"] == "builder-default"


@pytest.mark.asyncio
async def test_execute_explicit_key_overrides_default():
    """Explicit idempotency_key on execute() overrides the builder default."""
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .idempotency_key_default("builder-default")
        .build()
    )
    await engine.execute(object(), idempotency_key="per-call", inputs={})
    assert engine.runtime.execute_calls[0]["idempotency_key"] == "per-call"


@pytest.mark.asyncio
async def test_execute_default_inputs_is_empty_dict():
    """When inputs= is omitted, the engine forwards an empty dict (not None)."""
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    await engine.execute(object())
    assert engine.runtime.execute_calls[0]["inputs"] == {}


@pytest.mark.asyncio
async def test_execute_forwards_force_resume_with_drift():
    """The W1 force_resume_with_drift flag is forwarded to the runtime."""
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    await engine.execute(object(), force_resume_with_drift=True)
    assert engine.runtime.execute_calls[0]["force_resume_with_drift"] is True


@pytest.mark.asyncio
async def test_execute_with_dispatcher_enqueues_before_runtime():
    """When a dispatcher is configured, execute() MUST enqueue the task."""
    disp = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .dispatch_via(disp)
        .build()
    )
    workflow = _build_minimal_workflow()
    await engine.execute(workflow, idempotency_key="test-key", inputs={"a": 1})
    # Exactly one enqueue happened.
    assert len(disp.enqueued) == 1
    task = disp.enqueued[0]
    # The Task carries the engine's idempotency_key + inputs in its kwargs.
    assert task.kwargs["idempotency_key"] == "test-key"
    assert task.kwargs["inputs"] == {"a": 1}
    assert task.kwargs["engine"] == "DurableExecutionEngine"
    assert task.queue_name == "default"
    # The runtime ALSO ran in-process (the engine drives both).
    assert len(engine.runtime.execute_calls) == 1


@pytest.mark.asyncio
async def test_execute_dispatcher_idempotency_via_schedule_id():
    """Two execute() calls with the same key produce the same schedule_id.

    The deterministic schedule_id is what the dispatcher's idempotency
    gate (Dispatcher MUST Rule 1) uses to drop duplicates.
    """
    disp = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .dispatch_via(disp)
        .build()
    )
    workflow = _build_minimal_workflow()
    await engine.execute(workflow, idempotency_key="same-key", inputs={})
    await engine.execute(workflow, idempotency_key="same-key", inputs={})
    assert len(disp.enqueued) == 2
    # Both tasks share the schedule_id (the workflow + key are the same).
    assert disp.enqueued[0].schedule_id == disp.enqueued[1].schedule_id


@pytest.mark.asyncio
async def test_execute_without_dispatcher_does_not_enqueue():
    """No dispatcher configured → no enqueue path fires."""
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    await engine.execute(object())
    # No dispatcher means the in-process path is the only one.
    # soft_time_limit / time_limit are None when caller does not pass them
    # (#912 Shard 1 additive contract — slot accepted, default None).
    assert engine.runtime.execute_calls == [
        {
            "workflow": engine.runtime.execute_calls[0]["workflow"],
            "inputs": {},
            "idempotency_key": None,
            "force_resume_with_drift": False,
            "soft_time_limit": None,
            "time_limit": None,
        }
    ]


# ---------------------------------------------------------------------------
# History accessor surface
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_history_property_exposes_native_store_api():
    """``engine.history`` exposes the underlying store directly so callers
    can use the native ``list_runs`` / ``get_run`` / ``get_run_events`` API.
    """
    hs = _FakeHistoryStore()
    engine = (
        DurableExecutionEngine.builder().history_store(hs).runtime(_FakeRuntime).build()
    )
    # The property returns the SAME instance the builder received.
    assert engine.history is hs
    # The native API is callable through the property.
    await engine.history.list_runs(filter={"tenant_id": "default"})
    await engine.history.get_run("run_x", tenant_id="default")
    assert len(hs.list_runs_calls) == 1
    assert hs.list_runs_calls[0]["filter"] == {"tenant_id": "default"}
    assert hs.get_run_calls == [{"run_id": "run_x", "tenant_id": "default"}]


def test_history_property_returns_none_when_unconfigured():
    """No history_store configured → engine.history is None (not a stub)."""
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    assert engine.history is None


# ---------------------------------------------------------------------------
# Builder produces independent engines
# ---------------------------------------------------------------------------


def test_builder_build_can_be_called_multiple_times():
    """Each ``.build()`` produces a fresh engine — the builder is not consumed."""
    builder = DurableExecutionEngine.builder().runtime(_FakeRuntime)
    engine_a = builder.build()
    engine_b = builder.build()
    assert engine_a is not engine_b
    # Each engine has its own underlying runtime instance (factory ran twice).
    assert engine_a.runtime is not engine_b.runtime


def test_engine_is_immutable_after_build():
    """The engine has no public setters — composition cannot change post-build."""
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    # The properties are read-only — assignment raises AttributeError because
    # @property has no setter defined.
    with pytest.raises(AttributeError):
        engine.history = _FakeHistoryStore()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        engine.checkpoint_store = _FakeCheckpointStore()  # type: ignore[misc]
    with pytest.raises(AttributeError):
        engine.dispatcher = _FakeDispatcher()  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Default factory — uses AsyncLocalRuntime when none specified
# ---------------------------------------------------------------------------


def test_builder_default_runtime_factory_is_async_local_runtime():
    """Omitting .runtime() defers to AsyncLocalRuntime."""
    from kailash.runtime.async_local import AsyncLocalRuntime

    engine = DurableExecutionEngine.builder().build()
    assert isinstance(engine.runtime, AsyncLocalRuntime)
