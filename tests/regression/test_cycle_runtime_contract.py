"""Cycle traversal must use the prepared public runtime attempt contract."""

import asyncio
import inspect
import io
import logging
import threading

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.local import ContentAwareExecutionError, LocalRuntime
from kailash.runtime.parallel_cyclic import ParallelCyclicRuntime
from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    RuntimeExecutionError,
    SoftTimeLimitExceeded,
    WorkflowCancelledError,
)
from kailash.workflow.graph import Workflow


class Tick(Node):
    calls = 0
    mode = "ok"
    cancel_token = None
    contexts = None

    def get_parameters(self):
        return {
            "input_data": NodeParameter(
                name="input_data", type=dict, required=False, default={"n": 0}
            )
        }

    def run(self, **inputs):
        self.calls += 1
        if self.cancel_token is not None:
            self.cancel_token.cancel("requested during node")
        if self.contexts is not None:
            self.contexts.append(self._workflow_context)
        if self.mode == "error":
            raise ValueError("cycle-person@example.invalid")
        result = {"result": {"n": inputs["input_data"]["n"] + 1}}
        if self.mode == "content":
            result.update(success=False, error="declined")
        return result


class SlowTick(AsyncNode):
    calls = 0
    delay = 0.04
    started = None
    cleaning = None
    release = None
    closed = False

    def get_parameters(self):
        return Tick.get_parameters(self)

    async def async_run(self, **inputs):
        self.calls += 1
        if self.started is not None:
            self.started.set()
        try:
            await asyncio.sleep(self.delay if self.release is None else 60)
            return {"result": {"n": inputs["input_data"]["n"] + 1}}
        finally:
            if self.cleaning is not None:
                self.cleaning.set()
                await self.release.wait()
            self.closed = True


class Consume(Node):
    calls = 0

    def get_parameters(self):
        return {
            "input_data": NodeParameter(name="input_data", type=dict, required=True)
        }

    def run(self, **inputs):
        self.calls += 1
        return {"result": inputs["input_data"]}


def build(tick_type=Tick):
    workflow = Workflow("cycle_contract", "Cycle contract")
    tick, consumer = tick_type(), Consume()
    workflow.add_node("tick", tick)
    workflow.add_node("gate", SwitchNode, condition_field="n", operator="<", value=2)
    workflow.add_node("consume", consumer)
    workflow.connect("tick", "gate", {"result": "input_data"})
    workflow.connect("gate", "consume", {"false_output": "input_data"})
    workflow.create_cycle("loop").connect(
        "gate", "tick", {"true_output": "input_data"}
    ).max_iterations(3).build()
    assert workflow.has_cycles()
    return workflow, tick, consumer


async def invoke(runtime, entry, workflow, **kwargs):
    if entry == "sync":
        with runtime:
            return runtime.execute(workflow, **kwargs)
    if entry == "workflow":
        return await runtime.execute_workflow_async(workflow, inputs={}, **kwargs)
    return await runtime.execute_async(workflow, **kwargs)


async def close(runtime):
    if isinstance(runtime, AsyncLocalRuntime):
        await runtime.cleanup()
    runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "local_async", "native_async", "workflow"])
@pytest.mark.parametrize("detect", [True, False])
async def test_false_content_stops_before_cycle_consumer_or_success(entry, detect):
    runtime = (
        AsyncLocalRuntime if entry in ("native_async", "workflow") else LocalRuntime
    )(content_aware_success_detection=detect)
    workflow, tick, consumer = build()
    tick.mode = "content"
    events = []
    runtime.on_node_complete(events.append)
    try:
        if detect:
            with pytest.raises(ContentAwareExecutionError) as caught:
                await invoke(runtime, entry, workflow)
            assert caught.value.node_id == "tick"
            assert caught.value.failure_data["success"] is False
            assert tick.calls == 1 and consumer.calls == 0 and events == []
        else:
            results, run_id = await invoke(runtime, entry, workflow)
            assert results["consume"] == {"result": {"n": 2}}
            assert tick.calls == 2 and consumer.calls == 1
            assert [event.node_id for event in events] == [
                "tick",
                "gate",
                "tick",
                "gate",
                "consume",
            ]
            assert all(event.run_id == run_id for event in events)
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "local_async"])
@pytest.mark.parametrize("during", [False, True])
async def test_cancel_token_prevents_next_dispatch_and_success(entry, during):
    runtime = LocalRuntime()
    workflow, tick, consumer = build()
    token = CancellationToken()
    if during:
        tick.cancel_token = token
    else:
        token.cancel()
    events = []
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(WorkflowCancelledError):
            await invoke(runtime, entry, workflow, cancellation_token=token)
        assert tick.calls == int(during) and consumer.calls == 0
        assert [e.node_id for e in events] == (["tick"] if during else [])
        assert runtime.cyclic_executor.cycle_state_manager.get_all_summaries() == {}
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "native_async", "workflow"])
async def test_soft_deadline_stops_cycle_before_downstream(entry):
    runtime = (LocalRuntime if entry == "sync" else AsyncLocalRuntime)()
    workflow, tick, consumer = build(SlowTick)
    events = []
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(SoftTimeLimitExceeded):
            await invoke(runtime, entry, workflow, soft_time_limit=0.01, time_limit=0.5)
        # The deadline also covers preparation, so dispatch may not start.
        # If it did start, the successful node closes and publishes exactly once.
        assert tick.calls in (0, 1)
        assert tick.closed is (tick.calls == 1)
        assert consumer.calls == 0
        assert [e.node_id for e in events] == ["tick"] * tick.calls
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_native_cancel_drains_node_async_finally_and_traversal(runtime_type):
    runtime = runtime_type()
    workflow, tick, consumer = build(SlowTick)
    tick.started, tick.cleaning, tick.release = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    task = asyncio.create_task(runtime.execute_async(workflow))
    try:
        await asyncio.wait_for(tick.started.wait(), 2)
        task.cancel()
        await asyncio.wait_for(tick.cleaning.wait(), 2)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
        tick.release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert tick.closed and consumer.calls == 0
        assert runtime.cyclic_executor.cycle_state_manager.get_all_summaries() == {}
    finally:
        tick.release.set()
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await close(runtime)


def test_parallel_cycle_uses_contained_runtime_and_cancellation():
    runtime = LocalRuntime()
    wrapper = ParallelCyclicRuntime(runtime=runtime)
    workflow, tick, consumer = build()
    token = CancellationToken()
    token.cancel()
    try:
        with runtime, pytest.raises(WorkflowCancelledError):
            wrapper.execute(workflow, cancellation_token=token)
        assert tick.calls == consumer.calls == 0
    finally:
        wrapper.close()
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_outer_cycle_error_keeps_public_payload_out_of_automatic_logs(
    runtime_type, caplog
):
    runtime = runtime_type()
    workflow, tick, consumer = build()
    tick.mode = "error"
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    logging.getLogger().addHandler(handler)
    try:
        with caplog.at_level(logging.WARNING):
            with pytest.raises(Exception, match="cycle-person@example.invalid"):
                await runtime.execute_async(workflow)
        assert tick.calls == 1 and consumer.calls == 0
        assert caplog.records
        assert "cycle-person@example.invalid" not in stream.getvalue()
        assert "cycle-person@example.invalid" not in repr(
            [record.__dict__ for record in caplog.records]
        )
    finally:
        logging.getLogger().removeHandler(handler)
        await close(runtime)


@pytest.mark.asyncio
async def test_cancel_between_iterations_preserves_prior_completions():
    runtime = LocalRuntime()
    workflow, tick, consumer = build()
    token = CancellationToken()
    events = []

    def completed(event):
        events.append(event)
        if event.node_id == "gate":
            token.cancel("completed first iteration")

    runtime.on_node_complete(completed)
    try:
        with pytest.raises(WorkflowCancelledError):
            await runtime.execute_async(workflow, cancellation_token=token)
        assert tick.calls == 1 and consumer.calls == 0
        assert [event.node_id for event in events] == ["tick", "gate"]
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_cycle_nodes_retain_canonical_workflow_context(runtime_type):
    runtime = runtime_type()
    workflow, tick, consumer = build()
    shared = {"active_transaction": object()}
    tick.contexts = []
    if runtime_type is AsyncLocalRuntime:
        for node in workflow._node_instances.values():
            node._workflow_context = shared
        kwargs = {}
    else:
        kwargs = {"parameters": {"workflow_context": shared}}
    try:
        result, _ = await runtime.execute_async(workflow, **kwargs)
        assert result["consume"] == {"result": {"n": 2}}
        assert len(tick.contexts) == 2 and all(
            value is shared for value in tick.contexts
        )
    finally:
        await close(runtime)


def test_parallel_owned_runtime_preserves_async_constructor_option():
    runtime = ParallelCyclicRuntime(enable_async=False)
    try:
        assert runtime.local_runtime.enable_async is False
    finally:
        runtime.close()


class ObservedTick(SlowTick):
    async def async_run(self, **inputs):
        self.iterations = getattr(self, "iterations", [])
        self.iterations.append(inputs["context"]["cycle"]["iteration"])
        return await super().async_run(**inputs)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_concurrent_cycles_keep_independent_attempt_state(runtime_type, caplog):
    runtime = runtime_type()
    a, first, _ = build(ObservedTick)
    b, second, _ = build(ObservedTick)
    safety = runtime.cyclic_executor.safety_manager
    safety.set_global_limits(memory_limit=100000, timeout=10)
    fork = runtime.cyclic_executor._fork_for_execution()
    assert fork.safety_manager.global_memory_limit == 100000
    assert fork.safety_manager.global_timeout == 10
    assert fork.safety_manager.active_cycles is not safety.active_cycles
    assert fork.cycle_state_manager is not runtime.cyclic_executor.cycle_state_manager
    try:
        with caplog.at_level(logging.WARNING):
            result_a, result_b = await asyncio.gather(
                runtime.execute_async(a),
                runtime.execute_async(b),
                return_exceptions=True,
            )
        assert isinstance(result_a, tuple) and isinstance(result_b, tuple)
        assert result_a[0]["consume"] == result_b[0]["consume"] == {"result": {"n": 2}}
        assert first.iterations == second.iterations == [0, 1]
        assert first.calls == second.calls == 2
        assert safety.active_cycles == {}
        assert not [
            record for record in caplog.records if record.levelno >= logging.WARNING
        ]
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "native_async"])
async def test_hard_deadline_remains_typed_and_prevents_next_dispatch(entry):
    runtime = (LocalRuntime if entry == "sync" else AsyncLocalRuntime)()
    workflow, tick, consumer = build(SlowTick)
    tick.delay = 1.1
    events = []
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(HardTimeLimitExceeded):
            await invoke(runtime, entry, workflow, time_limit=0.005)
        assert tick.calls == 1 and tick.closed and consumer.calls == 0
        assert [e.node_id for e in events] == ["tick"]
    finally:
        await close(runtime)


def test_parallel_cycle_keeps_real_task_tracking_and_parameters(tmp_path):
    from kailash.tracking import TaskManager
    from kailash.tracking.storage.database import SQLiteStorage

    storage = SQLiteStorage(str(tmp_path / "cycle-tasks.db"))
    manager = TaskManager(storage)
    runtime = ParallelCyclicRuntime()
    workflow, tick, consumer = build()
    try:
        results, run_id = runtime.execute(
            workflow,
            task_manager=manager,
            parameters={"tick": {"input_data": {"n": 1}}},
        )
        assert results["consume"] == {"result": {"n": 2}}
        assert tick.calls == consumer.calls == 1
        assert isinstance(run_id, str) and manager.get_run_tasks(run_id)
        assert any(task.node_id == "consume" for task in manager.get_run_tasks(run_id))
    finally:
        runtime.close()
        storage.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_cancel_during_future_registration_drains_running_node(
    runtime_type, monkeypatch
):
    runtime = runtime_type()
    workflow, tick, consumer = build(SlowTick)
    tick.started, tick.cleaning, tick.release = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    admitted, release_registration = threading.Event(), threading.Event()
    futures = []
    original = asyncio.run_coroutine_threadsafe

    def delayed(coroutine, loop):
        future = original(coroutine, loop)
        if coroutine.cr_code.co_name == "execute_node":
            futures.append(future)
            admitted.set()
            assert release_registration.wait(2)
        return future

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", delayed)
    events = []
    runtime.on_node_complete(events.append)
    task = asyncio.create_task(runtime.execute_async(workflow))
    try:
        await asyncio.wait_for(tick.started.wait(), 2)
        assert admitted.is_set()
        task.cancel()
        await asyncio.sleep(0.01)
        release_registration.set()
        await asyncio.wait_for(tick.cleaning.wait(), 2)
        assert not task.done() and futures[0].cancelled()
        tick.release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        assert tick.calls == 1 and tick.closed and consumer.calls == 0 and events == []
    finally:
        release_registration.set()
        for future in futures:
            future.cancel()
        tick.release.set()
        await asyncio.gather(task, return_exceptions=True)
        await close(runtime)


@pytest.mark.asyncio
async def test_rejected_owner_submission_closes_unstarted_coroutine(monkeypatch):
    runtime = LocalRuntime()
    workflow, tick, consumer = build()
    coroutines = []

    def reject(coroutine, loop):
        coroutines.append(coroutine)
        raise RuntimeError("owner submission rejected")

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", reject)
    try:
        with pytest.raises(RuntimeExecutionError, match="owner submission rejected"):
            await runtime.execute_async(workflow)
        assert (
            len(coroutines) == 1
            and inspect.getcoroutinestate(coroutines[0]) == inspect.CORO_CLOSED
        )
        assert tick.calls == consumer.calls == 0
    finally:
        for coroutine in coroutines:
            coroutine.close()
        await close(runtime)


@pytest.mark.parametrize("managed", [False, True])
def test_parallel_borrow_preserves_callers_lifecycle_configuration(managed):
    runtime = LocalRuntime()
    if managed:
        runtime.mark_externally_managed()
    wrapper = ParallelCyclicRuntime(runtime=runtime)
    try:
        assert (
            wrapper.local_runtime is runtime and runtime._externally_managed is managed
        )
        assert runtime._ref_count == 2
        wrapper.close()
        assert runtime._ref_count == 1 and runtime._externally_managed is managed
    finally:
        wrapper.close()
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_interrupted_node_hard_error_never_publishes(runtime_type):
    class InterruptedTick(SlowTick):
        async def execute_async(self, **inputs):
            self.calls += 1
            raise HardTimeLimitExceeded("interrupted node")

    runtime = runtime_type()
    workflow, tick, consumer = build(InterruptedTick)
    events = []
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(HardTimeLimitExceeded, match="interrupted node"):
            await runtime.execute_async(workflow)
        assert tick.calls == 1 and consumer.calls == 0 and events == []
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_successful_node_cancelling_owner_publishes_before_next_suspension(
    runtime_type,
):
    owner = None

    class CancelOwnerTick(Tick):
        def run(self, **inputs):
            result = super().run(**inputs)
            owner.cancel()
            return result

    runtime = runtime_type()
    workflow, tick, consumer = build(CancelOwnerTick)
    events = []
    runtime.on_node_complete(events.append)
    try:
        owner = asyncio.create_task(runtime.execute_async(workflow))
        with pytest.raises(asyncio.CancelledError):
            await owner
        assert tick.calls == 1 and consumer.calls == 0
        assert [event.node_id for event in events] == ["tick"]
        assert events[0].outputs == {"result": {"n": 1}}
    finally:
        if owner is not None and not owner.done():
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
        await close(runtime)


@pytest.mark.parametrize("borrowed", [False, True])
@pytest.mark.parametrize("replacement", [False, True])
def test_parallel_cycle_policy_uses_single_owner_executor(
    borrowed, replacement, caplog
):
    from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor
    from kailash.workflow.safety import CycleSafetyManager

    class ConfiguredSafety(CycleSafetyManager):
        admissions = None

        def start_monitoring(self, *args, **kwargs):
            self.admissions.append(self.global_timeout)
            return super().start_monitoring(*args, **kwargs)

    owner = LocalRuntime() if borrowed else None
    if owner is not None:
        configured = owner.cyclic_executor
        configured.safety_manager.set_global_limits(timeout=0.001)
    wrapper = ParallelCyclicRuntime(runtime=owner)
    executor = wrapper.cyclic_executor
    original = executor
    if owner is not None:
        assert executor is not configured and owner.cyclic_executor is configured
    safety = ConfiguredSafety()
    safety.admissions = []
    safety.set_global_limits(timeout=0.001)
    if replacement:
        executor = CyclicWorkflowExecutor(safety_manager=safety)
        wrapper.cyclic_executor = executor
    else:
        executor.safety_manager = safety
    workflow, tick, consumer = build(SlowTick)
    try:
        # Context ownership is explicit for borrowed runtimes, without changing
        # their lifecycle configuration merely by wrapping them.
        if owner is not None:
            with owner:
                result, run_id = wrapper.execute(workflow)
        else:
            result, run_id = wrapper.execute(workflow)
        assert wrapper.cyclic_executor is executor
        if owner is not None:
            assert owner.cyclic_executor is configured
            assert owner.enable_cycles is True
        assert tick.calls == 1 and consumer.calls == 0
        assert result["tick"] == {"result": {"n": 1}}
        assert safety.admissions == [0.001]
        assert safety.active_cycles == {}
        assert executor.cycle_state_manager.get_all_summaries() == {}
        assert isinstance(run_id, str)
        if replacement:
            assert executor is not original
        assert any(
            "safety violation count=" in record.getMessage()
            for record in caplog.records
        )
    finally:
        wrapper.close()
        if owner is not None:
            owner.close()


def test_parallel_borrowed_disabled_owner_keeps_wrapper_cycle_mode():
    owner = LocalRuntime(enable_cycles=False)
    wrapper = ParallelCyclicRuntime(runtime=owner, enable_cycles=True)
    original = getattr(owner, "cyclic_executor", None)
    workflow, tick, consumer = build()
    try:
        with owner:
            result, run_id = wrapper.execute(workflow)
        assert result["consume"] == {"result": {"n": 2}}
        assert tick.calls == 2 and consumer.calls == 1
        assert owner.enable_cycles is False
        assert getattr(owner, "cyclic_executor", None) is original
        assert isinstance(run_id, str)
    finally:
        wrapper.close()
        owner.close()


@pytest.mark.parametrize("foreign", [False, True])
def test_wrapper_policy_is_consumed_before_nested_public_execution(foreign):
    owner = LocalRuntime(enable_cycles=True)
    nested_owner = LocalRuntime() if foreign else owner
    wrapper = ParallelCyclicRuntime(runtime=owner)
    wrapper.cyclic_executor.safety_manager.set_global_limits(timeout=0.001)
    nested, nested_tick, nested_consumer = build(SlowTick)
    nested_results = []

    class NestedTick(Tick):
        def run(self, **inputs):
            nested_results.append(nested_owner.execute(nested)[0])
            return super().run(**inputs)

    workflow, tick, consumer = build(NestedTick)
    original = owner.cyclic_executor
    try:
        with owner:
            if foreign:
                with nested_owner:
                    wrapper.execute(workflow)
            else:
                wrapper.execute(workflow)
        assert tick.calls == 1 and consumer.calls == 0
        assert nested_tick.calls == 2 and nested_consumer.calls == 1
        assert nested_results == [
            {
                "tick": {"result": {"n": 2}},
                "gate": {
                    "true_output": None,
                    "false_output": {"n": 2},
                    "condition_result": False,
                },
                "consume": {"result": {"n": 2}},
            }
        ]
        assert owner.cyclic_executor is original
        assert original.safety_manager.global_timeout is None
    finally:
        wrapper.close()
        if foreign:
            nested_owner.close()
        owner.close()


def test_wrapper_policy_scope_restores_caller_after_public_error():
    from kailash.runtime.mixins.cycle_execution import _cycle_attempt_executor

    owner = LocalRuntime()
    wrapper = ParallelCyclicRuntime(runtime=owner)
    workflow, tick, consumer = build()
    tick.mode = "content"
    sentinel = (object(), object())
    token = _cycle_attempt_executor.set(sentinel)
    try:
        with owner, pytest.raises(ContentAwareExecutionError):
            wrapper.execute(workflow)
        assert _cycle_attempt_executor.get() is sentinel
        assert tick.calls == 1 and consumer.calls == 0
    finally:
        _cycle_attempt_executor.reset(token)
        wrapper.close()
        owner.close()


@pytest.mark.parametrize("nested_owner", [False, True])
@pytest.mark.parametrize("prelude", [False, True])
@pytest.mark.parametrize("execution_timeout", [0, 5])
def test_native_wrapper_captures_policy_before_verifier_delegation(
    prelude, execution_timeout, nested_owner
):
    from kailash.runtime.trust.context import RuntimeTrustContext
    from kailash.runtime.trust.verifier import (
        TrustVerifier,
        TrustVerifierConfig,
        VerificationResult,
    )

    foreign = LocalRuntime()
    inner, inner_tick, inner_consumer = build(SlowTick)
    inner.workflow_id = "inner_policy_workflow"
    workflow, tick, consumer = build(SlowTick)
    verifier = TrustVerifier(
        config=TrustVerifierConfig(mode="enforcing", fallback_allow=True)
    )
    context = RuntimeTrustContext(delegation_chain=["policy-agent"])
    verifier._set_cache(
        f"wf\x00{workflow.workflow_id}\x00policy-agent",
        VerificationResult(allowed=True, reason="configured allow"),
    )
    verifier._set_cache(
        f"wf\x00{inner.workflow_id}\x00policy-agent",
        VerificationResult(allowed=True, reason="configured inner allow"),
    )
    verify = verifier.verify_workflow_access
    tasks = []

    async def delegated(*args, **kwargs):
        outer = kwargs["workflow_id"] == workflow.workflow_id
        if outer:
            tasks.append(asyncio.current_task())
        if prelude and outer:
            result, _ = await (owner if nested_owner else foreign).execute_async(inner)
            assert result["consume"] == {"result": {"n": 2}}
        if outer:
            tasks.append(asyncio.current_task())
        return await verify(*args, **kwargs)

    verifier.verify_workflow_access = delegated
    owner = AsyncLocalRuntime(
        trust_context=context,
        trust_verifier=verifier,
        trust_verification_mode="enforcing",
        execution_timeout=execution_timeout,
    )
    wrapper = ParallelCyclicRuntime(runtime=owner)
    wrapper.cyclic_executor.safety_manager.set_global_limits(timeout=0.001)
    original_owner_executor, original_foreign_executor = (
        owner.cyclic_executor,
        foreign.cyclic_executor,
    )
    try:
        result, _ = wrapper.execute(workflow)
        assert tick.calls == 1 and consumer.calls == 0
        assert result["tick"] == {"result": {"n": 1}}
        assert inner_tick.calls == (2 if prelude else 0)
        assert inner_consumer.calls == int(prelude)
        assert tasks[0] is tasks[1]
        assert owner.cyclic_executor is original_owner_executor
        assert foreign.cyclic_executor is original_foreign_executor
        assert owner.enable_cycles and foreign.enable_cycles
        assert wrapper.cyclic_executor.safety_manager.active_cycles == {}
    finally:
        wrapper.close()
        asyncio.run(owner.cleanup())
        owner.close()
        foreign.close()
