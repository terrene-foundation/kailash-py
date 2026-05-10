# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0
"""Regression tests for issue #882 — DurableExecutionEngine execution_mode.

Pre-fix: ``DurableExecutionEngine.execute()`` always enqueued a task
BEFORE running in-process when both a dispatcher and a runtime were
configured. Workers polling the queue could pick up the enqueued task
and start running BEFORE the in-process path completed; the engine's
docstring claimed ``task_id`` PRIMARY KEY idempotency prevented
double-execution, but PK idempotency only prevents duplicate ENQUEUE,
not duplicate EXECUTION by two different actors.

Post-fix: ``DurableExecutionEngineBuilder.execution_mode(...)`` is the
explicit caller-intent surface. Three modes:

* ``"in_process_only"`` — skip enqueue even if a dispatcher is set;
  eliminates the race entirely.
* ``"dispatch_only"`` — skip the in-process runtime call; require the
  caller to plumb worker output downstream.
* ``"both"`` — current pre-fix behaviour; the layered W1 checkpoint
  resume + dispatcher PK idempotency contain the blast radius for
  the in-tree :class:`SQLTaskQueueDispatcher`. Custom Dispatchers MUST
  honor the ``idempotency_key`` resume contract or callers MUST
  switch to one of the other two modes.

Default behaviour is preserved: omitting ``.execution_mode(...)``
auto-detects ``"both"`` when a dispatcher is configured and
``"in_process_only"`` otherwise — every pre-fix call site continues
to work without modification.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Tuple

import pytest

from kailash.runtime.durable import DurableExecutionEngine
from kailash.workflow.builder import WorkflowBuilder

pytestmark = pytest.mark.regression


# ---------------------------------------------------------------------------
# Deterministic protocol-satisfying adapters (Tier-1 per testing.md exception)
# ---------------------------------------------------------------------------


class _FakeRuntime:
    """Records ``execute_workflow_async`` invocations.

    Issue #882 specifically tests the ROUTING decision in
    ``DurableExecutionEngine.execute`` — whether the wrapped runtime
    was invoked at all. Recording the call list is the contract.
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
        soft_time_limit: Optional[float] = None,
        time_limit: Optional[float] = None,
    ) -> Tuple[Dict[str, Any], str]:
        # Mock mirrors AsyncLocalRuntime.execute_workflow_async signature
        # (src/kailash/runtime/async_local.py:847). soft_time_limit + time_limit
        # added by #876 / #912 plumbing in DurableExecutionEngine.execute
        # (durable.py:1479–1486). Recording them lets future routing tests
        # assert kwarg forwarding without re-touching this mock.
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
        return {"step1": {"result": {"value": 1}}}, "run_fake_001"


class _FakeDispatcher:
    """Records ``enqueue`` invocations; satisfies the Dispatcher ABC shape."""

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
# Builder validation — execution_mode opt-in surface
# ---------------------------------------------------------------------------


def test_issue_882_invalid_mode_raises_value_error():
    """Builder rejects unknown mode strings at the setter call.

    Failure mode this prevents: a typo (``"in-process"``,
    ``"in_process"`` without ``_only``) silently falls through to None
    and surfaces as a routing surprise at execute() time. The setter
    raises immediately so the typo is caught in the chain.
    """
    builder = DurableExecutionEngine.builder()
    with pytest.raises(ValueError, match="execution_mode.*must be one of"):
        builder.execution_mode("in-process")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="execution_mode.*must be one of"):
        builder.execution_mode("dispatch")  # type: ignore[arg-type]


def test_issue_882_dispatch_only_without_dispatcher_raises_at_build():
    """``dispatch_only`` is meaningless without a dispatcher; reject at build.

    The caller said "send everything to the queue, do not run in-process";
    without a queue there is nowhere to send. Catching at build time is
    cheaper than catching at the first execute() call.
    """
    builder = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .execution_mode("dispatch_only")
    )
    with pytest.raises(ValueError, match="execution_mode='dispatch_only'"):
        builder.build()


def test_issue_882_both_without_dispatcher_raises_at_build():
    """Explicit ``both`` requires a dispatcher.

    Auto-detected ``both`` (mode=None + dispatcher set) produces ``both``;
    auto-detected ``in_process_only`` (mode=None + no dispatcher) produces
    ``in_process_only``. Explicit ``both`` is the caller saying "I want
    BOTH paths to run", which requires a dispatcher to dispatch through.
    """
    builder = (
        DurableExecutionEngine.builder().runtime(_FakeRuntime).execution_mode("both")
    )
    with pytest.raises(ValueError, match="execution_mode='both'"):
        builder.build()


def test_issue_882_in_process_only_without_dispatcher_succeeds():
    """``in_process_only`` is valid without a dispatcher — the default shape."""
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .execution_mode("in_process_only")
        .build()
    )
    assert engine.execution_mode == "in_process_only"
    assert engine.dispatcher is None


def test_issue_882_default_mode_with_dispatcher_auto_detects_both():
    """Pre-issue-882 default behaviour: dispatcher present → ``both``."""
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .dispatch_via(_FakeDispatcher())
        .build()
    )
    assert engine.execution_mode == "both"


def test_issue_882_default_mode_without_dispatcher_auto_detects_in_process_only():
    """Pre-issue-882 default behaviour: no dispatcher → ``in_process_only``."""
    engine = DurableExecutionEngine.builder().runtime(_FakeRuntime).build()
    assert engine.execution_mode == "in_process_only"


# ---------------------------------------------------------------------------
# Routing — execute() respects execution_mode
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_issue_882_in_process_only_skips_enqueue_even_with_dispatcher():
    """The bug fix: ``in_process_only`` with a dispatcher SKIPS enqueue.

    Pre-fix: when the dispatcher was configured, enqueue ALWAYS fired.
    Post-fix: explicit ``in_process_only`` keeps the dispatcher reachable
    via ``engine.dispatcher`` for inspection but does not invoke it on
    execute(). Eliminates the enqueue/in-process race entirely for
    callers who have a dispatcher configured globally but want a
    specific run to stay synchronous.
    """
    runtime_holder: List[_FakeRuntime] = []

    def factory(**kwargs: Any) -> _FakeRuntime:
        rt = _FakeRuntime(**kwargs)
        runtime_holder.append(rt)
        return rt

    dispatcher = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(factory)
        .dispatch_via(dispatcher)
        .execution_mode("in_process_only")
        .build()
    )
    workflow = _build_minimal_workflow()
    _, run_id = await engine.execute(workflow, idempotency_key="k1")

    # Runtime ran exactly once; dispatcher was NOT invoked.
    assert len(runtime_holder[0].execute_calls) == 1
    assert runtime_holder[0].execute_calls[0]["idempotency_key"] == "k1"
    assert dispatcher.enqueued == []

    # Engine still surfaces the dispatcher for inspection.
    assert engine.dispatcher is dispatcher
    assert run_id == "run_fake_001"


@pytest.mark.asyncio
async def test_issue_882_dispatch_only_skips_runtime_returns_schedule_id():
    """``dispatch_only`` invokes ONLY the dispatcher; returns ``({}, schedule_id)``.

    Eliminates the race from the other side: caller defers all execution
    to the worker pool and gets a schedule_id back to correlate downstream
    output via the history store.
    """
    runtime_holder: List[_FakeRuntime] = []

    def factory(**kwargs: Any) -> _FakeRuntime:
        rt = _FakeRuntime(**kwargs)
        runtime_holder.append(rt)
        return rt

    dispatcher = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(factory)
        .dispatch_via(dispatcher)
        .execution_mode("dispatch_only")
        .build()
    )
    workflow = _build_minimal_workflow()
    results, run_id = await engine.execute(workflow, idempotency_key="dispatch_k1")

    # Dispatcher fired exactly once; runtime was NOT invoked.
    assert len(dispatcher.enqueued) == 1
    enqueued_task = dispatcher.enqueued[0]
    assert runtime_holder[0].execute_calls == []

    # ({}, schedule_id) sentinel — empty results dict + schedule_id as run_id.
    assert results == {}
    assert run_id == enqueued_task.schedule_id
    assert run_id.startswith("engine.")


@pytest.mark.asyncio
async def test_issue_882_both_mode_invokes_both_paths_in_order():
    """Explicit ``"both"`` matches pre-issue-882 default-with-dispatcher.

    Regression lock: the existing default behaviour (the path that
    introduced the race the issue describes) MUST still work for
    callers who explicitly opt in. The structural defense for this
    mode is layered (W1 checkpoint resume + dispatcher PK idempotency)
    and is documented in the engine docstring; this test verifies the
    routing wiring, not the race-window defense itself.
    """
    runtime_holder: List[_FakeRuntime] = []

    def factory(**kwargs: Any) -> _FakeRuntime:
        rt = _FakeRuntime(**kwargs)
        runtime_holder.append(rt)
        return rt

    dispatcher = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(factory)
        .dispatch_via(dispatcher)
        .execution_mode("both")
        .build()
    )
    workflow = _build_minimal_workflow()
    results, run_id = await engine.execute(workflow, idempotency_key="both_k1")

    # Both paths fired.
    assert len(dispatcher.enqueued) == 1
    assert len(runtime_holder[0].execute_calls) == 1
    # Real results from the in-process path; not the schedule_id sentinel.
    assert results == {"step1": {"result": {"value": 1}}}
    assert run_id == "run_fake_001"


@pytest.mark.asyncio
async def test_issue_882_default_with_dispatcher_matches_explicit_both():
    """Default + dispatcher == explicit ``"both"`` (backward-compat anchor).

    Pre-issue-882 callers who construct ``builder().dispatch_via(d).build()``
    without ``.execution_mode(...)`` MUST continue to get the both-paths
    behaviour. This regression test pins that contract.
    """
    runtime_holder: List[_FakeRuntime] = []

    def factory(**kwargs: Any) -> _FakeRuntime:
        rt = _FakeRuntime(**kwargs)
        runtime_holder.append(rt)
        return rt

    dispatcher = _FakeDispatcher()
    engine = (
        DurableExecutionEngine.builder()
        .runtime(factory)
        .dispatch_via(dispatcher)
        .build()  # no .execution_mode(...) — auto-detect
    )
    assert engine.execution_mode == "both"
    workflow = _build_minimal_workflow()
    await engine.execute(workflow, idempotency_key="default_k1")
    assert len(dispatcher.enqueued) == 1
    assert len(runtime_holder[0].execute_calls) == 1


@pytest.mark.asyncio
async def test_issue_882_default_without_dispatcher_runs_in_process_only():
    """Default + no dispatcher == ``in_process_only`` (backward-compat anchor)."""
    runtime_holder: List[_FakeRuntime] = []

    def factory(**kwargs: Any) -> _FakeRuntime:
        rt = _FakeRuntime(**kwargs)
        runtime_holder.append(rt)
        return rt

    engine = DurableExecutionEngine.builder().runtime(factory).build()
    assert engine.execution_mode == "in_process_only"
    workflow = _build_minimal_workflow()
    results, run_id = await engine.execute(workflow, idempotency_key="solo_k1")
    assert len(runtime_holder[0].execute_calls) == 1
    assert results == {"step1": {"result": {"value": 1}}}
    assert run_id == "run_fake_001"


@pytest.mark.asyncio
async def test_issue_882_time_limit_kwargs_forwarded_to_runtime():
    """``soft_time_limit`` / ``time_limit`` flow from ``engine.execute(...)``
    to ``runtime.execute_workflow_async(...)``.

    Structural defense against the silent-fallback failure mode in
    ``zero-tolerance.md`` Rule 3c (Documented Kwargs Accepted But Unused):
    the engine docstring at ``durable.py:1374-1383`` advertises these
    kwargs as forwarded; this test pins the contract behaviorally so a
    future refactor that drops the kwarg on the floor surfaces here, not
    at runtime when soft-time-limit alerting silently never fires.
    """
    runtime_holder: List[_FakeRuntime] = []

    def factory(**kwargs: Any) -> _FakeRuntime:
        rt = _FakeRuntime(**kwargs)
        runtime_holder.append(rt)
        return rt

    engine = DurableExecutionEngine.builder().runtime(factory).build()
    workflow = _build_minimal_workflow()
    await engine.execute(
        workflow,
        idempotency_key="time_k1",
        soft_time_limit=2.5,
        time_limit=5.0,
    )

    assert len(runtime_holder[0].execute_calls) == 1
    call = runtime_holder[0].execute_calls[0]
    assert call["soft_time_limit"] == 2.5
    assert call["time_limit"] == 5.0


def test_issue_882_engine_execution_mode_property_exposed():
    """``engine.execution_mode`` is a public read-only property.

    Surfaces the resolved mode for callers who construct the engine via
    a factory and want to verify the routing without re-deriving it.
    """
    engine = (
        DurableExecutionEngine.builder()
        .runtime(_FakeRuntime)
        .execution_mode("in_process_only")
        .build()
    )
    assert engine.execution_mode == "in_process_only"
    # Property is read-only — no setter exposed (engine is immutable).
    assert isinstance(
        type(DurableExecutionEngine).__dict__.get("execution_mode")
        or DurableExecutionEngine.__dict__["execution_mode"],
        property,
    )
