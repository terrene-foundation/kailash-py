"""Retry exhaustion must not add an unconfigured attempt before owner fallback."""

import asyncio

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import ContentAwareExecutionError, LocalRuntime
from kailash.runtime.resource_manager import _retry_execution_scope
from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    RuntimeExecutionError,
    SoftTimeLimitExceeded,
    WorkflowCancelledError,
    WorkflowExecutionError,
)
from kailash.workflow.graph import Workflow

pytestmark = pytest.mark.regression


class RetrySwitch(SwitchNode):
    def run(self, **inputs):
        self.calls += 1
        if self.calls <= self.failures:
            raise ValueError("controlled retry failure")
        return super().run(**inputs)


class Consumer(Node):
    def get_parameters(self):
        return {
            "input_data": NodeParameter(name="input_data", type=dict, required=True)
        }

    def run(self, **inputs):
        self.calls += 1
        return {"result": inputs["input_data"]}


def build(nested=False):
    switch = RetrySwitch(condition_field="status", operator="==", value="active")
    switch.calls = 0
    switch.failures = 0
    consumer = Consumer()
    consumer.calls = 0
    workflow = Workflow("retry_owner", "retry_owner")
    workflow.add_node("switch", switch)
    workflow.add_node("consume", consumer)
    selected = "switch"
    if nested:
        second = RetrySwitch(condition_field="status", operator="==", value="active")
        second.calls, second.failures = 0, 0
        workflow.add_node("nested", second)
        workflow.connect("switch", "nested", {"true_output": "input_data"})
        selected = "nested"
    workflow.connect(selected, "consume", {"true_output": "input_data"})
    return workflow, switch, consumer


def runtime_for(entry, attempts, circuit=False):
    cls = AsyncLocalRuntime if entry == "async_native" else LocalRuntime
    return cls(
        conditional_execution="skip_branches",
        circuit_breaker_config=(
            {"name": "retry-test", "failure_threshold": 10} if circuit else None
        ),
        retry_policy_config={
            "default_strategy": {
                "type": "fixed_delay",
                "max_attempts": attempts,
                "delay": 0,
                "jitter": False,
            },
            "exception_rules": {
                "retriable_patterns": [{"pattern": "controlled retry failure"}]
            },
        },
    )


async def execute(runtime, entry, workflow):
    parameters = {"switch": {"input_data": {"status": "active"}}}
    if entry == "sync":
        with runtime:
            return runtime.execute(workflow, parameters=parameters)
    return await runtime.execute_async(workflow, parameters=parameters)


async def close(runtime):
    if isinstance(runtime, AsyncLocalRuntime):
        await runtime.cleanup()
    runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "async_local", "async_native"])
@pytest.mark.parametrize("attempts", [1, 3])
@pytest.mark.parametrize("outcome", ["persistent", "owner_fallback", "policy_success"])
async def test_public_retry_attempts_and_single_owner_fallback(
    entry, attempts, outcome, monkeypatch, caplog
):
    workflow, switch, consumer = build()
    switch.failures = {
        "persistent": attempts + 10,
        "owner_fallback": attempts,
        "policy_success": attempts - 1,
    }[outcome]
    runtime = runtime_for(entry, attempts)
    entries = []
    events = []
    runtime.on_node_complete(events.append)
    original = runtime._execute_conditional_approach

    async def observed(*args, **kwargs):
        entries.append(kwargs["run_id"])
        return await original(*args, **kwargs)

    monkeypatch.setattr(runtime, "_execute_conditional_approach", observed)
    try:
        if outcome == "persistent":
            with pytest.raises((RuntimeExecutionError, WorkflowExecutionError)):
                await execute(runtime, entry, workflow)
            assert switch.calls == attempts + 1
            assert consumer.calls == 0
            assert events == []
        else:
            result, run_id = await execute(runtime, entry, workflow)
            assert result["consume"] == {"result": {"status": "active"}}
            assert run_id == entries[0]
            assert switch.calls == attempts + (outcome == "owner_fallback")
            assert consumer.calls == 1
            assert [event.node_id for event in events] == ["switch", "consume"]
        assert len(entries) == 1
        assert not any("Retry policy engine error" in r.message for r in caplog.records)
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_genuine_engine_failure_retains_one_direct_fallback(
    runtime_type, monkeypatch, caplog
):
    workflow, switch, consumer = build()
    runtime = runtime_for(
        "async_native" if runtime_type is AsyncLocalRuntime else "async_local", 3
    )
    events = []
    runtime.on_node_complete(events.append)
    calls = []

    async def unavailable(func, **kwargs):
        calls.append(func)
        raise RuntimeError("engine unavailable before dispatch")

    monkeypatch.setattr(runtime._retry_policy_engine, "execute_with_retry", unavailable)
    try:
        result, _ = await execute(runtime, "async", workflow)
        assert result["consume"] == {"result": {"status": "active"}}
        assert switch.calls == consumer.calls == 1
        assert len(calls) == 2
        assert [event.node_id for event in events] == ["switch", "consume"]
        assert (
            sum("Retry policy engine error" in r.message for r in caplog.records) == 2
        )
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize(
    "error_type",
    [
        asyncio.CancelledError,
        WorkflowCancelledError,
        SoftTimeLimitExceeded,
        HardTimeLimitExceeded,
        ContentAwareExecutionError,
    ],
)
async def test_engine_control_errors_do_not_dispatch_or_fallback(
    runtime_type, error_type, monkeypatch
):
    workflow, switch, consumer = build()
    runtime = runtime_for(
        "async_native" if runtime_type is AsyncLocalRuntime else "async_local", 3
    )
    error = error_type()
    calls = []

    async def stop(func, **kwargs):
        calls.append(func)
        raise error

    monkeypatch.setattr(runtime._retry_policy_engine, "execute_with_retry", stop)
    try:
        with pytest.raises(error_type):
            await execute(runtime, "async", workflow)
        assert len(calls) == 1
        assert switch.calls == consumer.calls == 0
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_engine_failure_after_dispatch_leaves_fallback_to_workflow_owner(
    runtime_type, monkeypatch, caplog
):
    workflow, switch, consumer = build()
    switch.failures = 10
    runtime = runtime_for(
        "async_native" if runtime_type is AsyncLocalRuntime else "async_local", 3
    )
    engine = runtime._retry_policy_engine
    original = engine.select_strategy
    calls = []

    def classification_failure(strategy_name=None, exception=None):
        calls.append(exception)
        if exception is not None:
            raise RuntimeError("engine classification failed after dispatch")
        return original(strategy_name, exception)

    monkeypatch.setattr(engine, "select_strategy", classification_failure)
    try:
        with pytest.raises((RuntimeExecutionError, WorkflowExecutionError)):
            await execute(runtime, "async", workflow)
        assert len(calls) == 2 and calls[0] is None and calls[1] is not None
        # One configured attempt before engine failure, one owner fallback.
        assert switch.calls == 2
        assert consumer.calls == 0
        assert (
            sum("Retry policy engine error" in r.message for r in caplog.records) == 1
        )
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize(
    "error_type",
    [
        WorkflowCancelledError,
        SoftTimeLimitExceeded,
        HardTimeLimitExceeded,
        ContentAwareExecutionError,
    ],
)
async def test_policy_terminal_control_result_preserves_original_error(
    runtime_type, error_type, monkeypatch
):
    workflow, switch, consumer = build()
    runtime = runtime_for(
        "async_native" if runtime_type is AsyncLocalRuntime else "async_local", 3
    )
    error = error_type()
    calls = []

    def stop(**inputs):
        calls.append(inputs)
        raise error

    monkeypatch.setattr(switch, "execute", stop)
    try:
        with pytest.raises(error_type) as caught:
            await execute(runtime, "async", workflow)
        assert caught.value is error
        assert len(calls) == 1
        assert consumer.calls == 0
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts", [1, 3])
async def test_exhausted_attempt_retains_error_context_without_direct_retry(attempts):
    workflow, switch, _ = build()
    switch.failures = 10
    runtime = runtime_for("async_local", attempts)
    try:
        with pytest.raises(RuntimeExecutionError) as caught:
            await runtime._execute_single_node(
                "switch",
                workflow=workflow,
                node_instance=switch,
                node_inputs={"input_data": {"status": "active"}},
            )
        assert switch.calls == attempts
        assert caught.value.node_id == "switch"
        assert caught.value.retry_context["total_attempts"] == attempts
        assert len(caught.value.retry_context["attempt_details"]) == attempts
        assert "controlled retry failure" in str(caught.value.original_exception)
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "async_local", "async_native"])
@pytest.mark.parametrize("circuit", [False, True])
@pytest.mark.parametrize(
    "error_type",
    [
        asyncio.CancelledError,
        WorkflowCancelledError,
        SoftTimeLimitExceeded,
        HardTimeLimitExceeded,
        ContentAwareExecutionError,
    ],
)
async def test_permissive_policy_cannot_retry_runtime_controls(
    entry, circuit, error_type, monkeypatch
):
    from kailash.runtime.resource_manager import CircuitBreaker

    workflow, switch, consumer = build()
    runtime = runtime_for(entry, 3)
    engine = runtime.get_retry_policy_engine()
    engine.exception_classifier.add_retriable_pattern(".*")
    engine.enable_circuit_breaker_coordination = circuit
    engine.circuit_breaker = CircuitBreaker("terminal-control", failure_threshold=10)
    error = error_type()
    calls = []
    classifications = []
    original = engine.exception_classifier.is_retriable

    def classify(exc):
        classifications.append(exc)
        return original(exc)

    def stop(**kwargs):
        calls.append(1)
        raise error

    monkeypatch.setattr(switch, "execute", stop)
    monkeypatch.setattr(engine.exception_classifier, "is_retriable", classify)
    try:
        with pytest.raises(error_type) as caught:
            await execute(runtime, entry, workflow)
        assert caught.value is error
        assert calls == [1]
        assert classifications == []
        assert consumer.calls == 0
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("circuit", [False, True])
@pytest.mark.parametrize("observer", ["metrics", "effectiveness", "circuit"])
async def test_success_observer_error_never_retries_completed_operation(
    circuit, observer, monkeypatch
):
    from kailash.runtime.resource_manager import (
        CircuitBreaker,
        FixedDelayStrategy,
        RetryPolicyEngine,
    )

    engine = RetryPolicyEngine(
        default_strategy=FixedDelayStrategy(max_attempts=3, delay=0, jitter=False),
        enable_circuit_breaker_coordination=circuit,
        circuit_breaker=CircuitBreaker("observer"),
    )
    error = RuntimeError("observer unavailable")
    deliveries = []

    observer_calls = []

    def broken(*args, **kwargs):
        observer_calls.append(1)
        if len(observer_calls) == 1:
            raise error

    async def operation():
        deliveries.append(1)
        return {"completed": True}

    if observer == "metrics":
        monkeypatch.setattr(engine.metrics, "record_attempt", broken)
    elif observer == "effectiveness":
        monkeypatch.setattr(engine, "record_strategy_effectiveness", broken)
    else:
        monkeypatch.setattr(engine.circuit_breaker, "_on_success", broken)
    if observer == "circuit" and not circuit:
        assert (await engine.execute_with_retry(operation)).value == {"completed": True}
    else:
        with pytest.raises(RuntimeError) as caught:
            await engine.execute_with_retry(operation)
        assert caught.value is error
    assert deliveries == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize("retriable", [False, True])
async def test_retry_diagnostics_preserve_payload_only_in_public_result(
    retriable, caplog
):
    import io
    import logging

    from kailash.runtime.resource_manager import FixedDelayStrategy, RetryPolicyEngine

    marker = "retry-person@example.invalid"
    error = ValueError(marker)
    engine = RetryPolicyEngine(
        default_strategy=FixedDelayStrategy(max_attempts=2, delay=0, jitter=False)
    )
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    log = logging.getLogger("kailash.runtime.resource_manager")
    log.addHandler(handler)
    calls = []

    async def operation():
        calls.append(1)
        raise error

    try:
        with caplog.at_level(logging.DEBUG, logger=log.name):
            if retriable:
                engine.exception_classifier.add_retriable_pattern(marker)
            else:
                engine.exception_classifier.add_non_retriable_pattern(marker)
            result = await engine.execute_with_retry(operation)
        assert result.final_exception is error
        assert result.attempts[0].error_message == marker
        assert len(calls) == (2 if retriable else 1)
        assert marker not in stream.getvalue()
        records = [r for r in caplog.records if r.name == log.name]
        assert records
        assert marker not in repr([r.__dict__ for r in records])
        assert any("ValueError" in r.getMessage() for r in records)
    finally:
        log.removeHandler(handler)
        handler.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "async_local", "async_native"])
@pytest.mark.parametrize("circuit", [False, True])
@pytest.mark.parametrize("nested", [False, True])
async def test_public_observer_failure_keeps_identity_without_owner_fallback(
    entry, circuit, nested, monkeypatch
):
    from kailash.runtime.resource_manager import CircuitBreaker

    workflow, switch, consumer = build(nested=nested)
    runtime = runtime_for(entry, 3)
    engine = runtime.get_retry_policy_engine()
    engine.enable_circuit_breaker_coordination = circuit
    engine.circuit_breaker = CircuitBreaker("public-observer")
    error = RuntimeError("metrics observer failed after delivery")

    def broken(attempt):
        raise error

    monkeypatch.setattr(engine.metrics, "record_attempt", broken)
    events = []
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(RuntimeError) as caught:
            await execute(runtime, entry, workflow)
        assert caught.value is error
        assert switch.calls == 1
        assert consumer.calls == 0
        assert events == []
    finally:
        await close(runtime)


@pytest.mark.asyncio
@_retry_execution_scope
async def test_observer_provenance_nested_engine_and_exception_reuse(monkeypatch):
    from kailash.runtime.resource_manager import FixedDelayStrategy, RetryPolicyEngine

    def make():
        return RetryPolicyEngine(
            default_strategy=FixedDelayStrategy(max_attempts=2, delay=0, jitter=False)
        )

    outer, inner = make(), make()
    error = RuntimeError("same reusable error")
    deliveries = []

    async def operation():
        deliveries.append(1)
        return True

    def broken(attempt):
        raise error

    monkeypatch.setattr(inner.metrics, "record_attempt", broken)

    async def nested():
        return await inner.execute_with_retry(operation)

    with pytest.raises(RuntimeError) as caught:
        await outer.execute_with_retry(nested)
    assert caught.value is error
    assert deliveries == [1]
    ordinary_calls = []

    async def ordinary():
        ordinary_calls.append(1)
        raise error

    result = await outer.execute_with_retry(ordinary)
    assert result.final_exception is error
    assert ordinary_calls == [1, 1]


@pytest.mark.asyncio
async def test_observer_provenance_ignores_hostile_attribute_hooks(monkeypatch):
    from kailash.runtime.resource_manager import FixedDelayStrategy, RetryPolicyEngine

    class HostileError(RuntimeError):
        def __setattr__(self, key, value):
            raise AssertionError("caller attribute hook invoked")

        @property
        def _kailash_retry_observer(self):
            raise AssertionError("caller descriptor invoked")

    error = HostileError("observer failed")
    engine = RetryPolicyEngine(
        default_strategy=FixedDelayStrategy(max_attempts=2, delay=0)
    )

    def broken(attempt):
        raise error

    monkeypatch.setattr(engine.metrics, "record_attempt", broken)
    calls = []

    async def operation():
        calls.append(1)
        return True

    with pytest.raises(HostileError) as caught:
        await engine.execute_with_retry(operation)
    assert caught.value is error
    assert calls == [1]


@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [False, True])
async def test_enterprise_retry_circuit_passes_callable_and_real_inputs(sync):
    from kailash.runtime.resource_manager import CircuitBreaker

    runtime = runtime_for("async_local", 2, circuit=True)
    node = Consumer()
    node.calls = 0
    try:
        if sync:
            result = runtime.execute_node_with_enterprise_features_sync(
                node, "consume", {"input_data": {"value": 17}}
            )
        else:
            result = await runtime.execute_node_with_enterprise_features(
                node, "consume", {"input_data": {"value": 17}}
            )
        assert result == {"result": {"value": 17}}
        assert node.calls == 1
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("sync", [False, True])
async def test_enterprise_observer_failure_not_replayed_by_sync_wrapper(
    sync, monkeypatch
):
    from kailash.runtime.resource_manager import CircuitBreaker

    runtime = runtime_for("async_local", 2, circuit=True)
    node = Consumer()
    node.calls = 0
    error = RuntimeError("can't start new thread")

    def broken():
        raise error

    monkeypatch.setattr(runtime._circuit_breaker, "_on_success", broken)
    try:
        with pytest.raises(RuntimeError) as caught:
            if sync:
                runtime.execute_node_with_enterprise_features_sync(
                    node, "consume", {"input_data": {"value": 17}}
                )
            else:
                await runtime.execute_node_with_enterprise_features(
                    node, "consume", {"input_data": {"value": 17}}
                )
        assert caught.value is error
        assert node.calls == 1
    finally:
        await close(runtime)


@pytest.mark.asyncio
async def test_concurrent_observer_scope_and_reused_exception_remain_independent(
    monkeypatch,
):
    from kailash.runtime.resource_manager import (
        _RETRY_EXECUTION_SCOPE,
        _RETRY_INVOCATIONS,
    )

    error = RuntimeError("reused observer exception")

    async def attempt(observer):
        runtime = runtime_for("async_native", 2)
        workflow, switch, consumer = build()
        engine = runtime.get_retry_policy_engine()
        engine.exception_classifier.add_retriable_pattern(".*")
        events = []
        if observer:

            def broken(result):
                raise error

            monkeypatch.setattr(engine.metrics, "record_attempt", broken)
        else:

            def fail(**inputs):
                events.append(1)
                raise error

            monkeypatch.setattr(switch, "execute", fail)
        try:
            with pytest.raises(Exception) as caught:
                await execute(runtime, "async_native", workflow)
            if observer:
                assert caught.value is error
                assert switch.calls == 1
            else:
                assert len(events) == 3  # two configured + one owner fallback
            assert consumer.calls == 0
        finally:
            await close(runtime)

    await attempt(True)
    await attempt(False)
    await asyncio.gather(attempt(True), attempt(True))
    assert _RETRY_EXECUTION_SCOPE.get() is None
    assert _RETRY_INVOCATIONS.get() == ()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["sync", "async_local", "async_native"])
async def test_public_retry_warning_has_no_private_exception_payload(
    entry, monkeypatch, caplog
):
    import io
    import logging

    marker = "retry-person@example.invalid"
    workflow, switch, consumer = build()
    runtime = runtime_for(entry, 2)
    runtime.get_retry_policy_engine().exception_classifier.add_retriable_pattern(".*")
    original = switch.execute
    calls = []

    def flaky(**inputs):
        calls.append(1)
        if len(calls) == 1:
            raise ValueError(marker)
        return original(**inputs)

    monkeypatch.setattr(switch, "execute", flaky)
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        with caplog.at_level(logging.DEBUG):
            result, _ = await execute(runtime, entry, workflow)
        assert result["consume"] == {"result": {"status": "active"}}
        assert len(calls) == 2
        assert consumer.calls == 1
        assert any("retrying in" in r.getMessage() for r in caplog.records)
        assert marker not in stream.getvalue()
        assert marker not in repr([r.__dict__ for r in caplog.records])
    finally:
        root.removeHandler(handler)
        handler.close()
        await close(runtime)


@pytest.mark.parametrize("circuit", [False, True])
def test_cyclic_executor_receives_node_output_from_enterprise_adapter(circuit):
    from kailash.workflow.cyclic_runner import CyclicWorkflowExecutor

    runtime = runtime_for("async_local", 2, circuit=circuit)
    node = Consumer(input_data={"value": 42})
    node.calls = 0
    workflow = Workflow("cyclic-adapter", "cyclic-adapter")
    workflow.add_node("consume", node)
    workflow.create_cycle("proof").connect(
        "consume", "consume", {"result": "input_data"}
    ).max_iterations(2).converge_when("value == 42").build()
    engine = runtime.get_retry_policy_engine()
    try:
        result, _ = CyclicWorkflowExecutor().execute(workflow, runtime=runtime)
        assert result["consume"] == {"result": {"value": 42}}
        assert node.calls == 1
        assert engine.metrics.total_successes == 1
    finally:
        runtime.close()


@pytest.mark.parametrize("error_type", [SoftTimeLimitExceeded, HardTimeLimitExceeded])
def test_scheduler_retry_spec_keeps_separate_timeout_policy(error_type):
    from kailash.runtime.scheduler import RetrySpec

    error = error_type()
    assert RetrySpec(retry_on=(error_type,)).is_retryable(error)
    assert not RetrySpec(dont_retry_on=(error_type,)).is_retryable(error)


@pytest.mark.asyncio
async def test_enterprise_submit_rejection_creates_no_unowned_coroutine(monkeypatch):
    import concurrent.futures
    import inspect

    submitted = []

    class RejectLaunch:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def submit(self, *args):
            submitted.extend(args)
            raise RuntimeError("can't start new thread")

    runtime = runtime_for("async_local", 2)
    node = Consumer()
    node.calls = 0
    monkeypatch.setattr(concurrent.futures, "ThreadPoolExecutor", RejectLaunch)
    try:
        result = runtime.execute_node_with_enterprise_features_sync(
            node, "consume", {"input_data": {"value": 42}}
        )
        assert result == {"result": {"value": 42}}
        assert node.calls == 1
        assert submitted
        assert not any(inspect.iscoroutine(arg) for arg in submitted)
    finally:
        for arg in submitted:
            if inspect.iscoroutine(arg):
                arg.close()
        await close(runtime)


@pytest.mark.parametrize("fallback_rejects", [False, True])
def test_enterprise_runner_rejection_closes_each_owned_coroutine(
    monkeypatch, fallback_rejects
):
    import inspect

    runtime = runtime_for("async_local", 2)
    node = Consumer()
    node.calls = 0
    coroutines = []
    loops = []
    original_new_loop = asyncio.new_event_loop
    error = RuntimeError("new loop refused before entry")

    def reject_run(coroutine):
        coroutines.append(coroutine)
        raise RuntimeError("cannot be called from a running event loop")

    def new_loop():
        loop = original_new_loop()
        loops.append(loop)
        original_run = loop.run_until_complete

        def observed(coroutine):
            coroutines.append(coroutine)
            if fallback_rejects:
                raise error
            return original_run(coroutine)

        monkeypatch.setattr(loop, "run_until_complete", observed)
        return loop

    monkeypatch.setattr(asyncio, "run", reject_run)
    monkeypatch.setattr(asyncio, "new_event_loop", new_loop)
    try:
        if fallback_rejects:
            with pytest.raises(RuntimeError) as caught:
                runtime.execute_node_with_enterprise_features_sync(
                    node, "consume", {"input_data": {"value": 42}}
                )
            assert caught.value is error
            assert node.calls == 0
        else:
            result = runtime.execute_node_with_enterprise_features_sync(
                node, "consume", {"input_data": {"value": 42}}
            )
            assert result == {"result": {"value": 42}}
            assert node.calls == 1
        assert len(coroutines) == 2
        assert all(
            inspect.getcoroutinestate(c) == inspect.CORO_CLOSED for c in coroutines
        )
        assert len(loops) == 1 and loops[0].is_closed()
    finally:
        for coroutine in coroutines:
            coroutine.close()
        for loop in loops:
            if not loop.is_closed():
                loop.close()
        asyncio.set_event_loop(None)
        runtime.close()
