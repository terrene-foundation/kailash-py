"""Concurrent sync callers retain independent execution and trust ownership."""

import asyncio
import contextvars
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

from kailash.nodes.base_async import AsyncNode
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.local import LocalRuntime
from kailash.runtime.trust.context import RuntimeTrustContext, runtime_trust_context
from kailash.runtime.trust.verifier import MockTrustVerifier
from kailash.sdk_exceptions import WorkflowCancelledError, WorkflowExecutionError
from kailash.workflow.graph import Workflow

value = contextvars.ContextVar("admission_test_value", default="unset")


class Observe(AsyncNode):
    calls = 0
    started = None
    release = None
    failure = None
    loops = None

    def get_parameters(self):
        return {}

    async def async_run(self, **inputs):
        self.calls += 1
        self.loops.append(asyncio.get_running_loop())
        if self.started is not None:
            self.started.set()
            while not self.release.is_set():
                await asyncio.sleep(0.001)
        if self.failure is not None:
            raise self.failure
        return {"value": value.get()}


def graph(node):
    node.loops = []
    workflow = Workflow("admission", "admission")
    workflow.add_node("observe", node)
    return workflow


@pytest.mark.parametrize(
    "outcome", ["success", "error", "cancel", "deny", "verify_error"]
)
def test_contended_sync_attempt_context_trust_stop_and_cleanup(outcome):
    first, second = Observe(), Observe()
    first.started, first.release = threading.Event(), threading.Event()
    first_workflow, second_workflow = graph(first), graph(second)
    verifier = MockTrustVerifier(default_allow=True)
    runtime = LocalRuntime(trust_verification_mode="enforcing", trust_verifier=verifier)
    checks = []
    original_error = ValueError("controlled observer verification")

    async def verify_workflow_access(**kwargs):
        checks.append(kwargs["trust_context"])
        if outcome == "verify_error":
            raise original_error
        return SimpleNamespace(allowed=outcome != "deny", reason="controlled denial")

    verifier.verify_workflow_access = verify_workflow_access
    context = RuntimeTrustContext(delegation_chain=["admission-agent"])
    cancellation = CancellationToken()
    if outcome == "cancel":
        cancellation.cancel("before contended dispatch")
    if outcome == "error":
        second.failure = ValueError("controlled node error")
        dependent = Observe()
        dependent.loops = []
        second_workflow.add_node("dependent", dependent)
        second_workflow.connect("observe", "dependent", {})
    try:
        with runtime, ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(runtime.execute, first_workflow)
            try:
                assert first.started.wait(3)
                persistent = runtime._persistent_loop

                def second_call():
                    token = value.set("second")
                    try:
                        with runtime_trust_context(context):
                            return runtime.execute(
                                second_workflow, cancellation_token=cancellation
                            )
                    finally:
                        value.reset(token)

                second_future = executor.submit(second_call)
                if outcome == "success":
                    result, _ = second_future.result(timeout=3)
                    assert result["observe"] == {"value": "second"}
                    assert second.calls == 1
                else:
                    expected = (
                        WorkflowCancelledError if outcome == "cancel" else Exception
                    )
                    with pytest.raises(expected) as caught:
                        second_future.result(timeout=3)
                    if outcome == "verify_error":
                        assert caught.value is original_error
                    if outcome == "deny":
                        assert isinstance(caught.value, WorkflowExecutionError)
                        assert (
                            str(caught.value)
                            == "Trust verification denied workflow execution"
                        )
                    assert second.calls == (1 if outcome == "error" else 0)
                    if outcome == "error":
                        assert dependent.calls == 0
                assert checks == [context]
                assert not first_future.done()  # Calls overlapped; no serialization.
                assert runtime._persistent_loop is persistent
                assert not persistent.is_closed()
                assert all(
                    loop is not persistent and loop.is_closed() for loop in second.loops
                )
            finally:
                first.release.set()
                first_future.result(timeout=3)
            assert not runtime._persistent_execution_lock.locked()
            third = Observe()
            runtime.execute(graph(third))
            assert third.loops == [persistent]
            assert third.calls == 1
    finally:
        first.release.set()
        runtime.close()
    assert all(loop.is_closed() for loop in first.loops)


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["persistent", "bridge", "async"])
@pytest.mark.parametrize("allowed", [False, True])
async def test_workflow_verification_once_at_all_local_public_entries(entry, allowed):
    node = Observe()
    workflow = graph(node)
    verifier = MockTrustVerifier(default_allow=True)
    checks = []
    context = RuntimeTrustContext(delegation_chain=["entry-agent"])

    async def verify_workflow_access(**kwargs):
        checks.append(kwargs["trust_context"])
        return SimpleNamespace(allowed=allowed, reason="controlled denial")

    verifier.verify_workflow_access = verify_workflow_access
    runtime = LocalRuntime(
        trust_verification_mode="enforcing",
        trust_verifier=verifier,
        trust_context=context,
    )

    async def invoke():
        if entry == "async":
            return await runtime.execute_async(workflow)
        if entry == "persistent":
            return await asyncio.to_thread(runtime.execute, workflow)
        return runtime.execute(workflow)

    try:
        with runtime:
            if allowed:
                result, _ = await invoke()
                assert result["observe"] == {"value": "unset"}
            else:
                with pytest.raises(
                    WorkflowExecutionError,
                    match="Trust verification denied workflow execution",
                ):
                    await invoke()
            assert checks == [context]
            assert node.calls == int(allowed)
            assert not runtime._persistent_execution_lock.locked()
    finally:
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("entry", ["local_async", "native_async", "native_workflow"])
@pytest.mark.parametrize("decision", ["allow", "deny", "error", "disabled"])
async def test_workflow_trust_precedes_real_checkpoint_reads(entry, decision, tmp_path):
    from kailash.runtime.async_local import AsyncLocalRuntime
    from tests.regression.test_cycle_checkpoint_publication import setup_store

    connection, store = await setup_store(tmp_path)
    events = []
    original_load = store.load
    context = RuntimeTrustContext(delegation_chain=["configured-agent"])
    override = RuntimeTrustContext(delegation_chain=["effective-agent"])
    error = ValueError("controlled verifier error")
    verifier = MockTrustVerifier(default_allow=True)

    async def load(*args, **kwargs):
        events.append("load")
        return await original_load(*args, **kwargs)

    async def verify_workflow_access(**kwargs):
        assert kwargs["trust_context"] is override
        assert kwargs["agent_id"] == "effective-agent"
        events.append("verify")
        if decision == "error":
            raise error
        return SimpleNamespace(allowed=decision == "allow", reason="controlled denial")

    store.load = load
    verifier.verify_workflow_access = verify_workflow_access
    cls = LocalRuntime if entry == "local_async" else AsyncLocalRuntime
    runtime = cls(
        checkpoint_store=store,
        trust_verifier=verifier,
        trust_verification_mode="disabled" if decision == "disabled" else "enforcing",
        trust_context=context,
    )
    node = Observe()
    workflow = graph(node)
    try:
        with runtime_trust_context(override):
            if entry == "native_workflow":
                pending = runtime.execute_workflow_async(
                    workflow, inputs={}, idempotency_key="ordered"
                )
            else:
                pending = runtime.execute_async(workflow, idempotency_key="ordered")
            if decision in {"allow", "disabled"}:
                result, _ = await pending
                assert result["observe"] == {"value": "unset"}
                assert events == (
                    ["load"] if decision == "disabled" else ["verify", "load"]
                )
                assert node.calls == 1
            else:
                with pytest.raises(Exception) as caught:
                    await pending
                assert events == ["verify"]
                assert node.calls == 0
                if decision == "deny":
                    assert isinstance(caught.value, WorkflowExecutionError)
                    assert (
                        str(caught.value)
                        == "Trust verification denied workflow execution"
                    )
                elif entry == "local_async":
                    assert caught.value is error
                else:
                    assert isinstance(caught.value, WorkflowExecutionError)
                    assert caught.value.__cause__ is error
    finally:
        if isinstance(runtime, AsyncLocalRuntime):
            await runtime.cleanup()
        runtime.close()
        await store.close()
        await connection.close()
