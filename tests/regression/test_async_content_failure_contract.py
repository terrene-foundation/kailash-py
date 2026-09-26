"""Content failures stop every runtime strategy before successful publication."""

import pytest

from kailash.nodes.base import Node, NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.runtime.async_local import AsyncLocalRuntime, ExecutionContext
from kailash.runtime.local import ContentAwareExecutionError, LocalRuntime
from kailash.sdk_exceptions import RuntimeExecutionError, WorkflowExecutionError
from kailash.workflow.graph import Workflow


class ContentSyncNode(Node):
    def get_parameters(self):
        return {"input": NodeParameter(name="input", type=dict, required=False)}

    def run(self, **kwargs):
        return self.execute(**kwargs)

    def execute(self, **kwargs):
        self.calls += 1
        return self.output


class ContentAsyncNode(AsyncNode):
    def get_parameters(self):
        return {"input": NodeParameter(name="input", type=dict, required=False)}

    async def execute_async(self, **kwargs):
        self.calls += 1
        return self.output


def _workflow(async_node, output):
    node = (ContentAsyncNode if async_node else ContentSyncNode)()
    node.calls = 0
    node.output = output
    workflow = Workflow("content_failure_contract", name="content_failure_contract")
    workflow.add_node("operation", node)
    return workflow, node


class RecordingCheckpointStore:
    def __init__(self):
        self.saves = []

    async def load(self, key):
        return next(
            (blob for saved_key, blob in reversed(self.saves) if saved_key == key), None
        )

    async def save(self, key, blob):
        self.saves.append((key, blob))


@pytest.mark.asyncio
@pytest.mark.parametrize("strategy", ["async", "sync", "mixed_sync", "analysis_off"])
@pytest.mark.parametrize("entry", ["execute_workflow_async", "execute_async"])
async def test_failed_content_raises_typed_error_for_every_strategy(strategy, entry):
    output = {"success": False, "error": "declared failure", "details": ["retained"]}
    workflow, node = _workflow(strategy in {"async", "analysis_off"}, output)
    runtime = AsyncLocalRuntime(enable_analysis=strategy != "analysis_off")
    events = []
    if strategy == "mixed_sync":
        runtime.on_node_complete(events.append)
    try:
        with pytest.raises(ContentAwareExecutionError) as caught:
            await getattr(runtime, entry)(
                workflow,
                **({"inputs": {}} if entry == "execute_workflow_async" else {}),
            )
        error = caught.value
        assert error.node_id == "operation"
        assert error.failure_data is output
        assert isinstance(error, WorkflowExecutionError)
        assert isinstance(error, RuntimeExecutionError)
        assert "declared failure" in str(error)
        assert node.calls == 1
        assert events == []
    finally:
        await runtime.cleanup()
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("async_node", [False, True])
@pytest.mark.parametrize("enabled", [False, True])
async def test_failed_content_never_records_success_checkpoint(async_node, enabled):
    output = {"success": False, "error": "checkpoint failure"}
    workflow, node = _workflow(async_node, output)
    store = RecordingCheckpointStore()
    events = []
    context = ExecutionContext()
    runtime = AsyncLocalRuntime(
        content_aware_success_detection=enabled,
        checkpoint_store=store,
        checkpoint_after_each_node=True,
    )
    runtime.on_node_complete(events.append)
    try:
        if enabled:
            with pytest.raises(ContentAwareExecutionError):
                await runtime.execute_workflow_async(
                    workflow,
                    inputs={},
                    context=context,
                    idempotency_key="content-failure",
                )
            assert not context._w1_execution_tracker.is_completed("operation")
            assert store.saves == []
            assert events == []
            assert context.metrics.error_count > 0
        else:
            result, _ = await runtime.execute_workflow_async(
                workflow, inputs={}, context=context, idempotency_key="content-failure"
            )
            assert result["operation"] is output
            assert context._w1_execution_tracker.is_completed("operation")
            assert len(store.saves) == len(events) == 1
        assert node.calls == 1
    finally:
        await runtime.cleanup()
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("async_node", [False, True])
@pytest.mark.parametrize(
    "output", [None, [], {}, {"error": "not failure"}, {"success": True}]
)
async def test_legacy_success_shapes_remain_success(async_node, output):
    workflow, node = _workflow(async_node, output)
    runtime = AsyncLocalRuntime()
    try:
        results, _ = await runtime.execute_workflow_async(workflow, inputs={})
        assert results["operation"] is output
        assert node.calls == 1
    finally:
        await runtime.cleanup()
        runtime.close()


@pytest.mark.parametrize("enabled", [False, True])
def test_local_runtime_exposes_same_typed_failure(enabled):
    output = {"success": False, "error": "sync failure"}
    workflow, node = _workflow(False, output)
    with LocalRuntime(content_aware_success_detection=enabled) as runtime:
        if enabled:
            with pytest.raises(ContentAwareExecutionError) as caught:
                runtime.execute(workflow)
            assert caught.value.node_id == "operation"
            assert caught.value.failure_data is output
            assert isinstance(caught.value, WorkflowExecutionError)
            assert isinstance(caught.value, RuntimeExecutionError)
        else:
            results, _ = runtime.execute(workflow)
            assert results["operation"] == output
    assert node.calls == 1


@pytest.mark.asyncio
async def test_local_async_entry_preserves_typed_error_and_failure_bookkeeping(
    monkeypatch,
):
    output = {"success": False, "error": "local async failure"}
    workflow, _ = _workflow(True, output)
    store = RecordingCheckpointStore()
    events = []
    runtime = LocalRuntime(
        checkpoint_store=store, checkpoint_after_each_node=True, enable_audit=True
    )
    audit_events = []

    async def record_audit(event_type, details):
        audit_events.append((event_type, details))

    monkeypatch.setattr(runtime, "_log_audit_event_async", record_audit)
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(ContentAwareExecutionError) as caught:
            await runtime.execute_async(workflow, idempotency_key="local-failure")
        assert caught.value.node_id == "operation"
        assert caught.value.failure_data is output
        assert isinstance(caught.value, WorkflowExecutionError)
        assert isinstance(caught.value, RuntimeExecutionError)
        assert store.saves == []
        assert events == []
        assert [kind for kind, _ in audit_events] == [
            "workflow_execution_start",
            "workflow_execution_failed",
        ]
        assert "local async failure" in audit_events[-1][1]["error"]
    finally:
        runtime.close()


@pytest.mark.asyncio
async def test_resume_rejects_failed_output_saved_with_detection_disabled():
    output = {"success": False, "error": "old checkpoint failure"}
    workflow, node = _workflow(True, output)
    store = RecordingCheckpointStore()
    for enabled in (False, True):
        runtime = AsyncLocalRuntime(
            content_aware_success_detection=enabled,
            checkpoint_store=store,
            checkpoint_after_each_node=True,
        )
        try:
            if enabled:
                with pytest.raises(ContentAwareExecutionError) as caught:
                    await runtime.execute_workflow_async(
                        workflow, inputs={}, idempotency_key="resume-failure"
                    )
                assert caught.value.failure_data == output
            else:
                await runtime.execute_workflow_async(
                    workflow, inputs={}, idempotency_key="resume-failure"
                )
        finally:
            await runtime.cleanup()
            runtime.close()
    assert node.calls == 1
    assert len(store.saves) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("hierarchical", [False, True])
@pytest.mark.parametrize(
    "enabled, success", [(True, False), (False, False), (True, True)]
)
@pytest.mark.parametrize("phase", ["switch_dependency", "selected_branch"])
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_conditional_failure_stops_without_fallback_or_reexecution(
    phase, runtime_type, enabled, success, hierarchical
):
    from kailash.nodes.logic.operations import SwitchNode

    output = {
        "success": success,
        "error": "conditional failure",
        "payload": {"status": "active"},
    }
    workflow, node = _workflow(False, output)
    workflow.add_node(
        "switch", SwitchNode(condition_field="status", operator="==", value="active")
    )
    last_switch = "switch"
    if hierarchical:
        workflow.add_node(
            "second_switch",
            SwitchNode(condition_field="status", operator="==", value="active"),
        )
        workflow.connect("switch", "second_switch", {"true_output": "input_data"})
        last_switch = "second_switch"
    if phase == "switch_dependency":
        workflow.connect("operation", "switch", {"payload": "input_data"})
        parameters = {}
    else:
        workflow.connect(last_switch, "operation", {"true_output": "input"})
        parameters = {"switch": {"input_data": {"status": "active"}}}
    runtime = runtime_type(
        conditional_execution="skip_branches", content_aware_success_detection=enabled
    )
    try:
        if hierarchical:
            assert runtime._should_use_hierarchical_execution(
                workflow, ["switch", "second_switch"]
            )
        if enabled and not success:
            with pytest.raises(ContentAwareExecutionError) as caught:
                await runtime.execute_async(workflow, parameters=parameters)
            assert caught.value.node_id == "operation"
            assert caught.value.failure_data is output
        else:
            results, _ = await runtime.execute_async(workflow, parameters=parameters)
            assert results["operation"] is output
        assert node.calls == 1
    finally:
        if isinstance(runtime, AsyncLocalRuntime):
            await runtime.cleanup()
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_hierarchical_gather_preserves_typed_failure(runtime_type, monkeypatch):
    from kailash.nodes.logic.operations import SwitchNode

    workflow = Workflow("gather_content_failure", "gather_content_failure")
    switch = SwitchNode(condition_field="status", operator="==", value="active")
    workflow.add_node("switch", switch)
    workflow.add_node(
        "second", SwitchNode(condition_field="status", operator="==", value="active")
    )
    workflow.connect("switch", "second", {"true_output": "input_data"})
    original = switch.execute
    outputs = []

    def declared_failure(**inputs):
        if outputs:
            pytest.fail("Conditional fallback re-executed a failed switch")
        output = original(**inputs)
        output.update(success=False, error="switch content failure")
        outputs.append(output)
        return output

    monkeypatch.setattr(switch, "execute", declared_failure)
    runtime = runtime_type(conditional_execution="skip_branches")
    try:
        assert runtime._should_use_hierarchical_execution(
            workflow, ["switch", "second"]
        )
        with pytest.raises(ContentAwareExecutionError) as caught:
            await runtime.execute_async(
                workflow, parameters={"switch": {"input_data": {"status": "active"}}}
            )
        assert len(outputs) == 1
        assert caught.value.node_id == "switch"
        assert caught.value.failure_data is outputs[0]
    finally:
        if isinstance(runtime, AsyncLocalRuntime):
            await runtime.cleanup()
        runtime.close()
