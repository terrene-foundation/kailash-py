"""Optimized branches share the prepared attempt's durable and stop controls."""

import asyncio

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.logic.operations import SwitchNode
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.durable import decode_checkpoint_payload
from kailash.runtime.local import ContentAwareExecutionError, LocalRuntime
from kailash.sdk_exceptions import SoftTimeLimitExceeded, WorkflowCancelledError
from kailash.workflow.graph import Workflow


class CountingSwitch(SwitchNode):
    calls = 0
    fail_once = False

    def run(self, **inputs):
        self.calls += 1
        if self.fail_once and self.calls == 1:
            raise ValueError("first switch attempt")
        return super().run(**inputs)


class SlowSwitch(CountingSwitch):
    async def execute_async(self, **inputs):
        await asyncio.sleep(0.05)
        return super().execute(**inputs)


class CountingConsumer(Node):
    calls = 0
    fail_content = False
    classified_value = None

    def get_parameters(self):
        return {
            "input_data": NodeParameter(name="input_data", type=dict, required=True)
        }

    def run(self, **inputs):
        self.calls += 1
        if self.fail_content:
            return {"success": False, "error": "consumer declined"}
        result = {"result": inputs["input_data"]}
        if self.classified_value is not None:
            result["classified"] = self.classified_value
        return result


class Producer(Node):
    calls = 0

    def get_parameters(self):
        return {}

    def run(self, **inputs):
        self.calls += 1
        return {"payload": {"status": "active"}}


def build(*, nested=False, producer=False, slow=False):
    workflow = Workflow("conditional_durable", "conditional_durable")
    switch_type = SlowSwitch if slow else CountingSwitch
    root = switch_type(condition_field="status", operator="==", value="active")
    workflow.add_node("switch", root)
    nodes = {"switch": root}
    if producer:
        nodes["producer"] = Producer()
        workflow.add_node("producer", nodes["producer"])
        workflow.connect("producer", "switch", {"payload": "input_data"})
    selected = "switch"
    if nested:
        nodes["nested"] = CountingSwitch(
            condition_field="status", operator="==", value="active"
        )
        workflow.add_node("nested", nodes["nested"])
        workflow.connect("switch", "nested", {"true_output": "input_data"})
        selected = "nested"
    nodes["consume"], nodes["unselected"] = CountingConsumer(), CountingConsumer()
    workflow.add_node("consume", nodes["consume"])
    workflow.add_node("unselected", nodes["unselected"])
    workflow.connect(selected, "consume", {"true_output": "input_data"})
    workflow.connect("switch", "unselected", {"false_output": "input_data"})
    return workflow, nodes


async def close(runtime):
    if isinstance(runtime, AsyncLocalRuntime):
        await runtime.cleanup()
    runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize(
    "nested, partial_fallback", [(False, False), (True, False), (False, True)]
)
async def test_real_sqlite_replay_skips_execution_and_duplicate_publication(
    runtime_type, nested, partial_fallback, tmp_path, caplog
):
    connection = ConnectionManager(f"sqlite:///{tmp_path / 'state.db'}")
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
    workflow, nodes = build(nested=nested, producer=partial_fallback)
    nodes["switch"].fail_once = partial_fallback
    parameters = (
        {} if partial_fallback else {"switch": {"input_data": {"status": "active"}}}
    )
    try:
        result, run_id = await runtime.execute_async(
            workflow, parameters=parameters, idempotency_key="conditional-replay"
        )
        assert result["consume"] == {"result": {"status": "active"}}
        expected = (
            {"switch", "consume"}
            | ({"nested"} if nested else set())
            | ({"producer"} if partial_fallback else set())
        )
        assert {event.node_id for event in events} == expected
        assert len(events) == len(expected)
        assert all(
            event.run_id == run_id and event.idempotency_key == "conditional-replay"
            for event in events
        )
        assert nodes["unselected"].calls == 0
        assert nodes["switch"].calls == (2 if partial_fallback else 1)
        if partial_fallback:
            assert nodes["producer"].calls == 1
        before = {name: node.calls for name, node in nodes.items()}
        keys = await store.list_keys("")
        assert len(keys) == 1
        blob = await store.load(keys[0])
        payload = decode_checkpoint_payload(blob)
        assert set(payload["tracker"]["completed_nodes"]) == expected
        assert payload["tracker"]["node_outputs"]["consume"] == result["consume"]
        replay, _ = await runtime.execute_async(
            workflow, parameters=parameters, idempotency_key="conditional-replay"
        )
        assert replay["consume"] == result["consume"]
        assert {name: node.calls for name, node in nodes.items()} == before
        assert len(events) == len(expected)
        assert await store.load(keys[0]) == blob
        assert not [
            record
            for record in caplog.records
            if record.getMessage().startswith("Node input validation failed:")
        ]
    finally:
        await close(runtime)
        await store.close()
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("nested", [False, True])
@pytest.mark.parametrize("pre_cancelled", [False, True])
async def test_actual_token_stops_optimized_nodes_before_dispatch(
    nested, pre_cancelled
):
    token = CancellationToken()
    workflow, nodes = build(nested=nested)
    runtime = LocalRuntime(conditional_execution="skip_branches")
    events = []

    def completed(event):
        events.append(event)
        token.cancel("stop after switch")

    runtime.on_node_complete(completed)
    if pre_cancelled:
        token.cancel("stop before dispatch")
    try:
        with pytest.raises(WorkflowCancelledError) as caught:
            await runtime.execute_async(
                workflow,
                parameters={"switch": {"input_data": {"status": "active"}}},
                cancellation_token=token,
            )
        assert nodes["switch"].calls == (0 if pre_cancelled else 1)
        assert nodes["consume"].calls == nodes["unselected"].calls == 0
        if nested:
            assert nodes["nested"].calls == 0
        assert [event.node_id for event in events] == (
            [] if pre_cancelled else ["switch"]
        )
        assert caught.value.completed_nodes == ([] if pre_cancelled else ["switch"])
    finally:
        await close(runtime)


@pytest.mark.asyncio
async def test_actual_soft_deadline_stops_after_current_conditional_node():
    workflow, nodes = build(slow=True)
    runtime = AsyncLocalRuntime(conditional_execution="skip_branches")
    events = []
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(SoftTimeLimitExceeded):
            await runtime.execute_async(
                workflow,
                parameters={"switch": {"input_data": {"status": "active"}}},
                soft_time_limit=0.005,
            )
        assert nodes["switch"].calls == 1
        assert nodes["consume"].calls == nodes["unselected"].calls == 0
        assert [event.node_id for event in events] == ["switch"]
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize("nested", [False, True])
async def test_optimized_execution_preserves_actual_node_context(runtime_type, nested):
    workflow, nodes = build(nested=nested)
    runtime = runtime_type(conditional_execution="skip_branches")
    scope = object()
    workflow_context = {"scope": scope}
    parameters = {"switch": {"input_data": {"status": "active"}}}
    if runtime_type is LocalRuntime:
        parameters["workflow_context"] = workflow_context
    else:
        # Native async consumers bind pinned transaction/resource context on
        # nodes; None at the hierarchy boundary must not erase that binding.
        for node in nodes.values():
            node.set_workflow_context("scope", scope)
    try:
        result, _ = await runtime.execute_async(workflow, parameters=parameters)
        assert result["consume"] == {"result": {"status": "active"}}
        for node_id in {"switch", "consume"} | ({"nested"} if nested else set()):
            assert nodes[node_id].get_workflow_context("scope") is scope
            if runtime_type is LocalRuntime:
                assert nodes[node_id]._workflow_context is workflow_context
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
@pytest.mark.parametrize("content_aware", [False, True])
async def test_failed_content_is_not_published_by_optimized_path(
    runtime_type, content_aware
):
    workflow, nodes = build()
    nodes["consume"].fail_content = True
    runtime = runtime_type(
        conditional_execution="skip_branches",
        content_aware_success_detection=content_aware,
    )
    events = []
    runtime.on_node_complete(events.append)
    try:
        call = runtime.execute_async(
            workflow, parameters={"switch": {"input_data": {"status": "active"}}}
        )
        if content_aware:
            with pytest.raises(ContentAwareExecutionError) as caught:
                await call
            assert caught.value.node_id == "consume"
            assert caught.value.failure_data == {
                "success": False,
                "error": "consumer declined",
            }
            assert [event.node_id for event in events] == ["switch"]
        else:
            result, _ = await call
            assert result["consume"] == {"success": False, "error": "consumer declined"}
            assert [event.node_id for event in events] == ["switch", "consume"]
        assert nodes["switch"].calls == nodes["consume"].calls == 1
    finally:
        await close(runtime)


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_shared_publisher_redacts_and_survives_observer_failure(
    runtime_type, tmp_path, caplog
):
    class Classification:
        def get_classification(self, node_id, field_name):
            return (
                "REDACT"
                if node_id == "consume" and field_name == "classified"
                else None
            )

    connection = ConnectionManager(f"sqlite:///{tmp_path / 'classified.db'}")
    store = DBCheckpointStore(connection)
    await connection.initialize()
    await store.initialize()
    workflow, nodes = build()
    nodes["consume"].classified_value = "private-checkpoint-value"
    runtime = runtime_type(
        conditional_execution="skip_branches",
        checkpoint_store=store,
        checkpoint_after_each_node=True,
    )
    runtime._classification_policy = Classification()
    events, failed_observer_calls = [], []

    def failing_observer(event):
        failed_observer_calls.append(event.node_id)
        raise ValueError("deliberate observer failure")

    runtime.on_node_complete(failing_observer)
    runtime.on_node_complete(events.append)
    try:
        result, _ = await runtime.execute_async(
            workflow,
            parameters={"switch": {"input_data": {"status": "active"}}},
            idempotency_key="classified-conditional",
        )
        assert result["consume"]["classified"] == "private-checkpoint-value"
        assert failed_observer_calls == ["switch", "consume"]
        assert [event.node_id for event in events] == ["switch", "consume"]
        assert events[-1].outputs["classified"] == "[REDACTED]"
        keys = await store.list_keys("")
        assert len(keys) == 1
        payload = decode_checkpoint_payload(await store.load(keys[0]))
        assert (
            payload["tracker"]["node_outputs"]["consume"]["classified"] == "[REDACTED]"
        )
        assert "private-checkpoint-value" not in repr(payload)
        assert (
            len(
                [
                    record
                    for record in caplog.records
                    if "subscriber" in record.getMessage().lower()
                    and record.levelname == "WARNING"
                ]
            )
            == 2
        )
    finally:
        await close(runtime)
        await store.close()
        await connection.close()
