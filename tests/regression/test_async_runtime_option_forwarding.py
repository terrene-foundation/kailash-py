"""Public AsyncLocalRuntime wrappers preserve supported execution controls."""

import asyncio

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.nodes.base import Node
from kailash.nodes.base_async import AsyncNode
from kailash.runtime.async_local import AsyncLocalRuntime, ExecutionContext
from kailash.runtime.durable import (
    WorkflowShapeDriftError,
    decode_checkpoint_payload,
    encode_checkpoint_payload,
)
from kailash.sdk_exceptions import HardTimeLimitExceeded, SoftTimeLimitExceeded
from kailash.workflow.graph import Workflow

pytestmark = pytest.mark.regression


class CountingNode(Node):
    def get_parameters(self):
        return {}

    def run(self, **kwargs):
        self.calls += 1
        return {"value": 42}


class SleepingNode(AsyncNode):
    def get_parameters(self):
        return {}

    async def execute_async(self, **kwargs):
        self.calls += 1
        await asyncio.sleep(self.delay)
        return {"value": 42}


def workflow_for(node):
    node.calls = 0
    workflow = Workflow("wrapper-options", name="wrapper-options")
    workflow.add_node("operation", node)
    return workflow


@pytest.fixture(params=["execute", "execute_async"])
def entry(request):
    return request.param


def invoke(runtime, entry, workflow, **kwargs):
    if entry == "execute":
        return runtime.execute(workflow, **kwargs)
    return asyncio.run(runtime.execute_async(workflow, **kwargs))


def close_runtime(runtime):
    try:
        asyncio.run(runtime.cleanup())
    finally:
        runtime.close()


@pytest.fixture
def checkpoint_store(tmp_path):
    connection = ConnectionManager(f"sqlite:///{tmp_path / 'checkpoint.db'}")
    store = DBCheckpointStore(connection)
    try:
        asyncio.run(connection.initialize())
        asyncio.run(store.initialize())
        yield store
    finally:
        asyncio.run(store.close())
        asyncio.run(connection.close())


def test_wrapper_checkpoint_resume_uses_real_sqlite(entry, checkpoint_store):
    node = CountingNode()
    workflow = workflow_for(node)
    for _ in range(2):
        context = ExecutionContext()
        runtime = AsyncLocalRuntime(
            checkpoint_store=checkpoint_store, checkpoint_after_each_node=True
        )
        try:
            result, run_id = invoke(
                runtime,
                entry,
                workflow,
                context=context,
                idempotency_key="wrapper-resume",
                force_resume_with_drift=False,
            )
            assert result == {"operation": {"value": 42}}
            assert isinstance(run_id, str) and run_id
            assert context._w1_idempotency_key == "wrapper-resume"
            keys = asyncio.run(checkpoint_store.list_keys(""))
            assert len(keys) == 1
            payload = decode_checkpoint_payload(
                asyncio.run(checkpoint_store.load(keys[0]))
            )
            assert payload["idempotency_key"] == "wrapper-resume"
            assert node.calls == 1  # A second execution must restore persisted output.
        finally:
            close_runtime(runtime)


def test_wrapper_forwards_explicit_drift_override(entry, checkpoint_store, caplog):
    node = CountingNode()
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store, checkpoint_after_each_node=True
    )
    try:
        invoke(runtime, entry, workflow, idempotency_key="drift")
        keys = asyncio.run(checkpoint_store.list_keys(""))
        assert len(keys) == 1
        payload = decode_checkpoint_payload(asyncio.run(checkpoint_store.load(keys[0])))
        asyncio.run(
            checkpoint_store.save(
                keys[0],
                encode_checkpoint_payload(
                    workflow_fingerprint="different-stored-shape",
                    tracker_state=payload["tracker"],
                    idempotency_key="drift",
                ),
            )
        )
        with pytest.raises(WorkflowShapeDriftError):
            invoke(runtime, entry, workflow, idempotency_key="drift")
        assert node.calls == 1
        caplog.clear()
        result, _ = invoke(
            runtime,
            entry,
            workflow,
            idempotency_key="drift",
            force_resume_with_drift=True,
        )
        assert result == {"operation": {"value": 42}}
        assert node.calls == 1
        assert [r.getMessage() for r in caplog.records if r.levelno >= 30] == [
            "durable.resume.shape_drift_forced"
        ]
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize(
    "option,delay,error",
    [
        ("soft_time_limit", 0.04, SoftTimeLimitExceeded),
        ("time_limit", 1.06, HardTimeLimitExceeded),
    ],
)
def test_wrapper_deadline_really_fires(entry, option, delay, error):
    node = SleepingNode()
    node.delay = delay
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime()
    try:
        with pytest.raises(error):
            invoke(runtime, entry, workflow, **{option: 0.01})
        assert node.calls == 1
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize("option", ["soft_time_limit", "time_limit"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), -float("inf")])
def test_wrapper_rejects_invalid_deadline_before_execution(entry, option, value):
    node = CountingNode()
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime()
    try:
        with pytest.raises(ValueError, match=option):
            invoke(runtime, entry, workflow, **{option: value})
        assert node.calls == 0
    finally:
        close_runtime(runtime)


def test_wrapper_rejects_inverted_deadlines_before_execution(entry):
    node = CountingNode()
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime()
    try:
        with pytest.raises(ValueError, match="strictly less"):
            invoke(runtime, entry, workflow, soft_time_limit=1, time_limit=1)
        assert node.calls == 0
    finally:
        close_runtime(runtime)


@pytest.mark.parametrize(
    "control", ["task_manager", "cancellation_token", "search_attributes"]
)
@pytest.mark.parametrize("value", [False, {}])
def test_wrapper_rejects_unsupported_explicit_controls(entry, control, value):
    node = CountingNode()
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime()
    try:
        with pytest.raises(TypeError, match=control):
            invoke(runtime, entry, workflow, **{control: value})
        assert node.calls == 0
    finally:
        close_runtime(runtime)


def test_async_wrapper_rejects_external_execution_tracker():
    node = CountingNode()
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime()
    try:
        with pytest.raises(TypeError, match="execution_tracker"):
            invoke(runtime, "execute_async", workflow, execution_tracker={})
        assert node.calls == 0
    finally:
        close_runtime(runtime)


def test_wrapper_unknown_option_does_not_partially_execute(entry):
    node = CountingNode()
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime()
    try:
        with pytest.raises(TypeError, match="unsupported_execution_control"):
            invoke(runtime, entry, workflow, unsupported_execution_control=True)
        assert node.calls == 0
    finally:
        close_runtime(runtime)


def test_wrapper_none_controls_preserve_default_tuple(entry):
    node = CountingNode()
    workflow = workflow_for(node)
    runtime = AsyncLocalRuntime()
    options = {"execution_tracker": None} if entry == "execute_async" else {}
    try:
        result = invoke(
            runtime,
            entry,
            workflow,
            task_manager=None,
            cancellation_token=None,
            search_attributes=None,
            soft_time_limit=None,
            time_limit=None,
            **options,
        )
        assert isinstance(result, tuple) and len(result) == 2
        assert result[0] == {"operation": {"value": 42}}
        assert isinstance(result[1], str) and result[1]
        assert node.calls == 1
    finally:
        close_runtime(runtime)
