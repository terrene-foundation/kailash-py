"""Iteration-aware cyclic checkpoints preserve canonical node identity."""

import asyncio
import json
from contextlib import ExitStack

import pytest

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.durable import decode_checkpoint_payload
from kailash.runtime.execution_tracker import ExecutionTracker
from kailash.runtime.local import ContentAwareExecutionError, LocalRuntime
from kailash.sdk_exceptions import WorkflowCancelledError
from kailash.trust.auth.context import TenantContext, get_current_tenant_id
from tests.regression.test_cycle_runtime_contract import Tick, build, close


class DurableTick(Tick):
    fail_on = None

    def run(self, **inputs):
        result = super().run(**inputs)
        result["private"] = "cycle-checkpoint-person@example.invalid"
        result["tenant"] = get_current_tenant_id()
        if self.calls == self.fail_on:
            result.update(success=False, error="iteration declined")
        return result


class Classification:
    def get_classification(self, node_id, field_name):
        return "REDACT" if node_id == "tick" and field_name == "private" else None


async def setup_store(tmp_path):
    connection = ConnectionManager(f"sqlite:///{tmp_path / 'cycle-checkpoints.db'}")
    store = DBCheckpointStore(connection)
    await connection.initialize()
    await store.initialize()
    return connection, store


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime, "sync"])
async def test_sqlite_cycle_checkpoint_replays_each_iteration_without_dispatch(
    runtime_type, tmp_path, caplog
):
    connection, store = await setup_store(tmp_path)
    runtime = (LocalRuntime if runtime_type == "sync" else runtime_type)(
        checkpoint_store=store, checkpoint_after_each_node=True
    )
    runtime._classification_policy = Classification()
    workflow, tick, consumer = build(DurableTick)
    tenants = TenantContext()
    tenants.register("cycle-a")
    tenants.register("cycle-b")
    events = []
    runtime.on_node_complete(events.append)
    owner = ExitStack()
    if runtime_type == "sync":
        owner.enter_context(runtime)
    try:
        for tenant in ("cycle-a", "cycle-b", "cycle-a"):
            with tenants.switch(tenant):
                if runtime_type == "sync":
                    result, run_id = runtime.execute(
                        workflow, idempotency_key="same-cycle-key"
                    )
                else:
                    result, run_id = await runtime.execute_async(
                        workflow, idempotency_key="same-cycle-key"
                    )
            assert result["consume"] == {"result": {"n": 2}}
            assert result["tick"]["tenant"] == tenant
        assert tick.calls == 4 and consumer.calls == 2
        assert [e.node_id for e in events] == [
            "tick",
            "gate",
            "tick",
            "gate",
            "consume",
        ] * 2
        assert [e.tenant_id for e in events] == ["cycle-a"] * 5 + ["cycle-b"] * 5
        assert all(e.idempotency_key == "same-cycle-key" for e in events)
        assert all(
            e.outputs["private"] == "[REDACTED]" for e in events if e.node_id == "tick"
        )
        keys = await store.list_keys("")
        assert len(keys) == 2
        for key in keys:
            blob = await store.load(key)
            assert b"cycle-checkpoint-person@example.invalid" not in blob
            payload = decode_checkpoint_payload(blob)
            tracker = payload["tracker"]
            assert tracker["completed_nodes"] == ["consume"]
            iterations = tracker["cycle_iterations"]["loop"]
            assert set(iterations) == {"1", "2"}
            for number in (1, 2):
                assert iterations[str(number)]["completed_nodes"] == ["tick", "gate"]
                assert iterations[str(number)]["node_outputs"]["tick"]["result"] == {
                    "n": number
                }
                assert (
                    iterations[str(number)]["node_outputs"]["tick"]["private"]
                    == "[REDACTED]"
                )
        assert not [r for r in caplog.records if r.levelno >= 30]
    finally:
        owner.close()
        await close(runtime)
        await store.close()
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_partial_iteration_resume_skips_successful_nodes_only(
    runtime_type, tmp_path
):
    connection, store = await setup_store(tmp_path)
    runtime = runtime_type(checkpoint_store=store, checkpoint_after_each_node=True)
    runtime._classification_policy = Classification()
    workflow, tick, consumer = build(DurableTick)
    tick.fail_on = 2
    events = []
    runtime.on_node_complete(events.append)
    try:
        with pytest.raises(ContentAwareExecutionError) as caught:
            await runtime.execute_async(workflow, idempotency_key="partial-cycle")
        assert (
            caught.value.node_id == "tick" and tick.calls == 2 and consumer.calls == 0
        )
        assert [e.node_id for e in events] == ["tick", "gate"]
        keys = await store.list_keys("")
        assert len(keys) == 1
        payload = decode_checkpoint_payload(await store.load(keys[0]))
        assert payload["tracker"]["cycle_iterations"]["loop"]["1"][
            "completed_nodes"
        ] == ["tick", "gate"]
        assert "2" not in payload["tracker"]["cycle_iterations"]["loop"]
        tick.fail_on = None
        result, _ = await runtime.execute_async(
            workflow, idempotency_key="partial-cycle"
        )
        assert result["consume"] == {"result": {"n": 2}}
        assert tick.calls == 3 and consumer.calls == 1
        assert [e.node_id for e in events] == [
            "tick",
            "gate",
            "tick",
            "gate",
            "consume",
        ]
        before = await store.load(keys[0])
        replay, _ = await runtime.execute_async(
            workflow, idempotency_key="partial-cycle"
        )
        assert replay["consume"] == result["consume"]
        assert tick.calls == 3 and consumer.calls == 1 and len(events) == 5
        assert await store.load(keys[0]) == before
    finally:
        await close(runtime)
        await store.close()
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_restored_failed_iteration_is_rejected_before_success(
    runtime_type, tmp_path
):
    connection, store = await setup_store(tmp_path)
    runtime = runtime_type(checkpoint_store=store, checkpoint_after_each_node=True)
    workflow, tick, consumer = build()
    events = []
    runtime.on_node_complete(events.append)
    try:
        await runtime.execute_async(workflow, idempotency_key="restored-failure")
        keys = await store.list_keys("")
        payload = decode_checkpoint_payload(await store.load(keys[0]))
        failed_output = {"success": False, "error": "stored failure"}
        payload["tracker"]["cycle_iterations"]["loop"]["1"]["node_outputs"][
            "tick"
        ] = failed_output
        await store.save(keys[0], json.dumps(payload).encode())
        events.clear()
        with pytest.raises(ContentAwareExecutionError) as caught:
            await runtime.execute_async(workflow, idempotency_key="restored-failure")
        assert (
            caught.value.node_id == "tick"
            and caught.value.failure_data == failed_output
        )
        assert tick.calls == 2 and consumer.calls == 1 and events == []
    finally:
        await close(runtime)
        await store.close()
        await connection.close()


def test_tracker_iteration_view_roundtrip_and_acyclic_shape():
    tracker = ExecutionTracker()
    tracker.record_completion("before", {"value": 1})
    assert tracker.to_dict() == {
        "completed_nodes": ["before"],
        "node_outputs": {"before": {"value": 1}},
    }
    first = tracker.for_cycle_iteration("loop", 1)
    first.record_completion("tick", {"value": 2})
    second = tracker.for_cycle_iteration("loop", 2)
    assert not second.is_completed("tick")
    restored = ExecutionTracker.from_dict(first.to_dict())
    assert restored.is_completed("before")
    assert restored.for_cycle_iteration("loop", 1).get_output("tick") == {"value": 2}
    assert not restored.for_cycle_iteration("loop", 2).is_completed("tick")
    assert restored.to_dict() == tracker.to_dict()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["token", "local_native", "async_native"])
async def test_successful_side_effect_is_saved_before_cancel_and_not_repeated(
    mode, tmp_path
):
    connection, store = await setup_store(tmp_path)
    runtime = (AsyncLocalRuntime if mode == "async_native" else LocalRuntime)(
        checkpoint_store=store, checkpoint_after_each_node=True
    )
    runtime._classification_policy = Classification()
    effects = tmp_path / "committed-effects.txt"

    class CommittedTick(DurableTick):
        def run(self, **inputs):
            result = super().run(**inputs)
            with effects.open("a") as stream:
                stream.write(str(result["result"]["n"]) + "\n")
            return result

    workflow, tick, consumer = build(CommittedTick)
    token = CancellationToken()
    if mode == "token":
        tick.cancel_token = token
    events = []
    attempt = None

    def completed(event):
        events.append(event)
        if mode != "token" and len(events) == 1:
            attempt.cancel()

    runtime.on_node_complete(completed)
    try:
        kwargs = {"cancellation_token": token} if mode == "token" else {}
        attempt = asyncio.create_task(
            runtime.execute_async(workflow, idempotency_key="cancelled-cycle", **kwargs)
        )
        with pytest.raises(
            WorkflowCancelledError if mode == "token" else asyncio.CancelledError
        ):
            await attempt
        assert effects.read_text().splitlines() == ["1"]
        assert tick.calls == 1 and consumer.calls == 0
        assert [event.node_id for event in events] == ["tick"]
        keys = await store.list_keys("")
        assert len(keys) == 1
        saved = decode_checkpoint_payload(await store.load(keys[0]))
        assert saved["tracker"]["cycle_iterations"]["loop"]["1"]["completed_nodes"] == [
            "tick"
        ]
        tick.cancel_token = None
        result, _ = await runtime.execute_async(
            workflow, idempotency_key="cancelled-cycle"
        )
        assert result["consume"] == {"result": {"n": 2}}
        assert effects.read_text().splitlines() == ["1", "2"]
        assert tick.calls == 2 and consumer.calls == 1
        assert [event.node_id for event in events] == [
            "tick",
            "gate",
            "tick",
            "gate",
            "consume",
        ]
        assert all(
            event.outputs["private"] == "[REDACTED]"
            for event in events
            if event.node_id == "tick"
        )
    finally:
        if attempt is not None and not attempt.done():
            attempt.cancel()
            await asyncio.gather(attempt, return_exceptions=True)
        await close(runtime)
        await store.close()
        await connection.close()


@pytest.mark.asyncio
async def test_successful_node_cancelling_owner_records_iteration_before_suspension():
    owner = None

    class CancelOwnerTick(Tick):
        def run(self, **inputs):
            result = super().run(**inputs)
            owner.cancel()
            return result

    tracker = ExecutionTracker()
    runtime = LocalRuntime()
    workflow, tick, consumer = build(CancelOwnerTick)
    events = []
    runtime.on_node_complete(events.append)
    try:
        owner = asyncio.create_task(
            runtime.execute_async(workflow, execution_tracker=tracker)
        )
        with pytest.raises(asyncio.CancelledError):
            await owner
        saved = tracker.to_dict()["cycle_iterations"]["loop"]["1"]
        assert saved["completed_nodes"] == ["tick"]
        assert saved["node_outputs"]["tick"] == {"result": {"n": 1}}
        assert tick.calls == 1 and consumer.calls == 0 and len(events) == 1
    finally:
        if owner is not None and not owner.done():
            owner.cancel()
            await asyncio.gather(owner, return_exceptions=True)
        await close(runtime)


@pytest.mark.asyncio
async def test_cancel_summary_includes_dag_and_prior_cycle_iteration(tmp_path):
    connection, store = await setup_store(tmp_path)
    runtime = LocalRuntime(checkpoint_store=store, checkpoint_after_each_node=True)

    class Prepare(Tick):
        def run(self, **inputs):
            self.calls += 1
            return {"result": {"n": 0}}

    workflow, tick, consumer = build()
    prepare = Prepare()
    workflow.add_node("prepare", prepare)
    workflow.connect("prepare", "tick", {"result": "input_data"})
    token = CancellationToken()
    events = []

    def completed(event):
        events.append(event)
        if event.node_id == "gate":
            token.cancel()

    runtime.on_node_complete(completed)
    try:
        with pytest.raises(WorkflowCancelledError) as caught:
            await runtime.execute_async(
                workflow, cancellation_token=token, idempotency_key="summary-cycle"
            )
        assert [event.node_id for event in events] == ["prepare", "tick", "gate"]
        assert caught.value.completed_nodes == ["prepare", "tick", "gate"]
        assert prepare.calls == tick.calls == 1 and consumer.calls == 0
        keys = await store.list_keys("")
        assert len(keys) == 1
        payload = decode_checkpoint_payload(await store.load(keys[0]))
        restored = ExecutionTracker.from_dict(payload["tracker"])
        assert restored.completed_node_ids == ["prepare"]
        assert restored.for_cycle_iteration("loop", 1).completed_node_ids == [
            "tick",
            "gate",
        ]
        assert restored.for_cycle_iteration("loop", 2).completed_node_ids == []
        assert restored.for_cycle_iteration("loop", 2).all_completed_node_ids == [
            "prepare",
            "tick",
            "gate",
        ]
    finally:
        await close(runtime)
        await store.close()
        await connection.close()
