"""Conditional failures enter the owner's standard strategy at most once."""

import asyncio

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.local import ContentAwareExecutionError, LocalRuntime
from kailash.sdk_exceptions import (
    HardTimeLimitExceeded,
    RuntimeExecutionError,
    SoftTimeLimitExceeded,
    WorkflowCancelledError,
    WorkflowExecutionError,
)
from kailash.workflow.graph import Workflow


class ControlledSwitch(SwitchNode):
    def run(self, **inputs):
        self.calls += 1
        if self.mode == "cancel" or (
            self.mode == "fallback_cancel" and self.calls == 2
        ):
            raise self.cancellation
        if self.mode == "content":
            return {"success": False, "error": "declared switch failure"}
        if self.mode == "persistent" or (
            self.mode in {"transient", "fallback_cancel"} and self.calls == 1
        ):
            raise ValueError("conditional operator failed")
        return super().run(**inputs)


class Consumer(Node):
    def get_parameters(self):
        return {
            "input_data": NodeParameter(name="input_data", type=dict, required=True)
        }

    def run(self, **inputs):
        self.calls += 1
        return {"result": inputs["input_data"]}


def make_workflow(mode):
    switch = ControlledSwitch(condition_field="status", operator="==", value="active")
    switch.mode, switch.calls = mode, 0
    switch.cancellation = asyncio.CancelledError("caller cancelled")
    consumer = Consumer()
    consumer.calls = 0
    workflow = Workflow("conditional_fallback_owner", "conditional_fallback_owner")
    workflow.add_node("switch", switch)
    workflow.add_node("consume", consumer)
    workflow.connect("switch", "consume", {"true_output": "input_data"})
    return workflow, switch, consumer


async def close(runtime):
    if isinstance(runtime, AsyncLocalRuntime):
        await runtime.cleanup()
    runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize(
    "mode",
    ["persistent", "transient", "success", "content", "cancel", "fallback_cancel"],
)
async def test_conditional_owner_bounds_attempts_and_preserves_terminal_failures(
    runtime_type, mode, monkeypatch
):
    workflow, switch, consumer = make_workflow(mode)
    runtime = runtime_type(conditional_execution="skip_branches")
    original = runtime._execute_conditional_approach
    entries = []

    class RecursiveDispatch(BaseException):
        pass

    async def bounded(*args, **kwargs):
        entries.append(kwargs.get("run_id"))
        if len(entries) > 1:
            raise RecursiveDispatch("conditional owner re-entered")
        return await original(*args, **kwargs)

    monkeypatch.setattr(runtime, "_execute_conditional_approach", bounded)
    try:
        call = runtime.execute_async(
            workflow, parameters={"switch": {"input_data": {"status": "active"}}}
        )
        if mode in {"transient", "success"}:
            result, run_id = await call
            assert result["consume"] == {"result": {"status": "active"}}
            assert run_id == entries[0]
            assert switch.calls == (2 if mode == "transient" else 1)
            assert consumer.calls == 1
        elif mode == "persistent":
            expected = (
                RuntimeExecutionError
                if runtime_type is LocalRuntime
                else WorkflowExecutionError
            )
            with pytest.raises(expected):
                await call
            assert switch.calls == 2
            assert consumer.calls == 0
        elif mode == "content":
            with pytest.raises(ContentAwareExecutionError) as caught:
                await call
            assert caught.value.node_id == "switch"
            assert caught.value.failure_data["success"] is False
            assert switch.calls == 1
            assert consumer.calls == 0
        else:
            with pytest.raises(asyncio.CancelledError) as caught:
                await call
            assert caught.value is switch.cancellation
            assert switch.calls == (2 if mode == "fallback_cancel" else 1)
            assert consumer.calls == 0
        assert len(entries) == 1
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize(
    "error_type", [WorkflowCancelledError, SoftTimeLimitExceeded, HardTimeLimitExceeded]
)
async def test_conditional_terminal_control_error_never_starts_fallback(
    runtime_type, error_type, monkeypatch
):
    workflow, switch, consumer = make_workflow("success")
    runtime = runtime_type(conditional_execution="skip_branches")
    error = error_type("terminal execution control")
    hits = []

    async def cancelled_phase(*args, **kwargs):
        hits.append(1)
        raise error

    monkeypatch.setattr(runtime, "_execute_switch_nodes", cancelled_phase)
    try:
        with pytest.raises(error_type) as caught:
            await runtime.execute_async(
                workflow, parameters={"switch": {"input_data": {"status": "active"}}}
            )
        assert caught.value is error
        assert hits == [1]
        assert switch.calls == consumer.calls == 0
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_fallback_retains_checkpoint_and_single_completion_publication(
    runtime_type, tmp_path
):
    from kailash.db.connection import ConnectionManager
    from kailash.infrastructure.checkpoint_store import DBCheckpointStore
    from kailash.runtime.durable import decode_checkpoint_payload

    connection = ConnectionManager(f"sqlite:///{tmp_path / 'fallback.db'}")
    store = DBCheckpointStore(connection)
    await connection.initialize()
    await store.initialize()
    runtime = runtime_type(
        conditional_execution="skip_branches",
        checkpoint_store=store,
        checkpoint_after_each_node=True,
    )
    events = []
    runtime.on_node_complete(events.append)
    workflow, switch, consumer = make_workflow("transient")
    try:
        result, run_id = await runtime.execute_async(
            workflow,
            parameters={"switch": {"input_data": {"status": "active"}}},
            idempotency_key="conditional-fallback",
        )
        assert result["consume"] == {"result": {"status": "active"}}
        assert (switch.calls, consumer.calls) == (2, 1)
        assert [event.node_id for event in events] == ["switch", "consume"]
        assert all(event.run_id == run_id for event in events)
        keys = await store.list_keys("")
        assert len(keys) == 1
        payload = decode_checkpoint_payload(await store.load(keys[0]))
        assert payload["idempotency_key"] == "conditional-fallback"
        assert set(payload["tracker"]["completed_nodes"]) == {"switch", "consume"}
    finally:
        await close(runtime)
        await store.close()
        await connection.close()
