"""Deadline owners and explicit drift permission survive every entry path."""

import asyncio

import pytest
import pytest_asyncio

from kailash.db.connection import ConnectionManager
from kailash.infrastructure.checkpoint_store import DBCheckpointStore
from kailash.nodes.base import Node
from kailash.runtime._time_limits import arm_time_limits_async
from kailash.runtime.async_local import AsyncLocalRuntime, ExecutionContext
from kailash.runtime.cancellation import CancellationToken
from kailash.runtime.durable import (
    DurableExecutionEngine,
    WorkflowShapeDriftError,
    check_shape_drift_or_raise,
    decode_checkpoint_payload,
    encode_checkpoint_payload,
)
from kailash.runtime.local import LocalRuntime
from kailash.runtime.parallel import ParallelRuntime
from kailash.sdk_exceptions import RuntimeExecutionError, SoftTimeLimitExceeded
from kailash.workflow.graph import Workflow

pytestmark = pytest.mark.regression


class ControlNode(Node):
    def get_parameters(self):
        return {}

    def run(self, **kwargs):
        self.calls += 1
        return {"value": 42}


class SpoofedBoolean:
    @property
    def __class__(self):
        return bool

    def __bool__(self):
        raise AssertionError("Drift validation must not coerce caller objects")


def make_workflow():
    node = ControlNode()
    node.calls = 0
    workflow = Workflow("runtime-controls", name="runtime-controls")
    workflow.add_node("operation", node)
    return workflow, node


def timer_tasks():
    return {
        task
        for task in asyncio.all_tasks()
        if "arm_time_limits_async.<locals>._fire_" in task.get_coro().__qualname__
    }


@pytest_asyncio.fixture
async def checkpoint_store(tmp_path):
    connection = ConnectionManager(f"sqlite:///{tmp_path / 'controls.db'}")
    store = DBCheckpointStore(connection)
    try:
        await connection.initialize()
        await store.initialize()
        yield store
    finally:
        await store.close()
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["drift", "invalid_blob", "context", "load_cancel"])
async def test_early_preparation_failure_finishes_owned_timers(
    case, checkpoint_store, monkeypatch
):
    workflow, node = make_workflow()
    runtime = AsyncLocalRuntime(
        checkpoint_store=checkpoint_store, checkpoint_after_each_node=True
    )
    before = timer_tasks()
    try:
        await runtime.execute_async(workflow, idempotency_key="early-failure")
        key = (await checkpoint_store.list_keys(""))[0]
        payload = decode_checkpoint_payload(await checkpoint_store.load(key))
        options = {}
        if case == "drift":
            await checkpoint_store.save(
                key,
                encode_checkpoint_payload(
                    workflow_fingerprint="other-shape",
                    tracker_state=payload["tracker"],
                ),
            )
            expected = WorkflowShapeDriftError
        elif case == "invalid_blob":
            await checkpoint_store.save(key, b"invalid checkpoint JSON")
            expected = ValueError
        elif case == "context":
            context = ExecutionContext()
            context.variables = None
            options["context"] = context
            expected = AttributeError
        else:
            original = checkpoint_store.load
            cancellation = asyncio.CancelledError("checkpoint read cancelled")

            async def cancelled_load(key):
                await original(key)  # Real SQLite load precedes injected cancellation.
                raise cancellation

            monkeypatch.setattr(checkpoint_store, "load", cancelled_load)
            expected = asyncio.CancelledError
        with pytest.raises(expected) as caught:
            await runtime.execute_async(
                workflow,
                idempotency_key="early-failure",
                soft_time_limit=60,
                time_limit=90,
                **options,
            )
        if case == "load_cancel":
            assert caught.value is cancellation
        assert node.calls == 1
        assert timer_tasks() == before  # No extra event-loop turn needed for disposal.
    finally:
        for task in timer_tasks() - before:
            task.cancel()
        await asyncio.gather(*(timer_tasks() - before), return_exceptions=True)
        await runtime.cleanup()
        runtime.close()


@pytest.mark.asyncio
async def test_deadline_covers_checkpoint_preparation(checkpoint_store, monkeypatch):
    workflow, node = make_workflow()
    runtime = AsyncLocalRuntime(checkpoint_store=checkpoint_store)
    original = checkpoint_store.load
    reached = []

    async def delayed_load(key):
        result = await original(key)
        reached.append(key)
        await asyncio.sleep(0.04)
        return result

    monkeypatch.setattr(checkpoint_store, "load", delayed_load)
    before = timer_tasks()
    try:
        with pytest.raises(SoftTimeLimitExceeded):
            await runtime.execute_async(
                workflow, idempotency_key="slow-load", soft_time_limit=0.01
            )
        assert len(reached) == 1 and node.calls == 1
        assert timer_tasks() == before
    finally:
        await runtime.cleanup()
        runtime.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "entry",
    [
        "local_sync",
        "local_async",
        "local_private",
        "async_sync",
        "async_wrapper",
        "async_native",
        "durable",
    ],
)
@pytest.mark.parametrize(
    "value", ["false", "true", "", 0, 1, None, [], {}, SpoofedBoolean()]
)
async def test_drift_override_rejects_non_boolean_before_execution(entry, value):
    workflow, node = make_workflow()
    runtime = LocalRuntime() if entry.startswith("local") else AsyncLocalRuntime()
    try:
        with pytest.raises(TypeError, match="force_resume_with_drift must be a bool"):
            if entry == "local_sync":
                runtime.execute(workflow, force_resume_with_drift=value)
            elif entry == "local_async":
                await runtime.execute_async(workflow, force_resume_with_drift=value)
            elif entry == "local_private":
                await runtime._execute_async(workflow, force_resume_with_drift=value)
            elif entry == "async_sync":
                await asyncio.to_thread(
                    runtime.execute, workflow, force_resume_with_drift=value
                )
            elif entry == "async_wrapper":
                await runtime.execute_async(workflow, force_resume_with_drift=value)
            elif entry == "async_native":
                await runtime.execute_workflow_async(
                    workflow, inputs={}, force_resume_with_drift=value
                )
            else:
                engine = (
                    DurableExecutionEngine.builder()
                    .runtime(lambda **kwargs: runtime)
                    .build()
                )
                await engine.execute(workflow, force_resume_with_drift=value)
        assert node.calls == 0
    finally:
        if isinstance(runtime, AsyncLocalRuntime):
            await runtime.cleanup()
        runtime.close()


@pytest.mark.parametrize(
    "value", ["false", "true", "", 0, 1, None, [], {}, SpoofedBoolean()]
)
@pytest.mark.parametrize("stored", ["same", "different"])
def test_shared_drift_evaluator_rejects_non_boolean_even_without_drift(value, stored):
    with pytest.raises(TypeError, match="force_resume_with_drift must be a bool"):
        check_shape_drift_or_raise(
            idempotency_key="strict",
            stored_payload={"workflow_fingerprint": stored},
            current_fingerprint="same",
            force_resume_with_drift=value,
        )


@pytest.mark.parametrize("value", [False, True])
def test_shared_drift_evaluator_preserves_both_boolean_values(value, caplog):
    check_shape_drift_or_raise(
        idempotency_key="strict",
        stored_payload={"workflow_fingerprint": "same"},
        current_fingerprint="same",
        force_resume_with_drift=value,
    )
    if value:
        check_shape_drift_or_raise(
            idempotency_key="strict",
            stored_payload={"workflow_fingerprint": "different"},
            current_fingerprint="same",
            force_resume_with_drift=True,
        )
        assert [r.getMessage() for r in caplog.records] == [
            "durable.resume.shape_drift_forced"
        ]
    else:
        with pytest.raises(WorkflowShapeDriftError):
            check_shape_drift_or_raise(
                idempotency_key="strict",
                stored_payload={"workflow_fingerprint": "different"},
                current_fingerprint="same",
                force_resume_with_drift=False,
            )


@pytest.mark.asyncio
async def test_parallel_runtime_finishes_timers_on_execution_error():
    before = timer_tasks()
    workflow, _ = make_workflow()
    # A real graph with a missing node instance fails execution after arming.
    workflow.graph.add_edge("missing", "operation")
    try:
        with pytest.raises(RuntimeExecutionError):
            await ParallelRuntime().execute(workflow, soft_time_limit=60, time_limit=90)
        assert timer_tasks() == before
    finally:
        for task in timer_tasks() - before:
            task.cancel()
        await asyncio.gather(*(timer_tasks() - before), return_exceptions=True)


@pytest.mark.asyncio
async def test_async_disarm_finishes_owners_under_repeated_caller_cancellation():
    loop = asyncio.get_running_loop()
    original_factory = loop.get_task_factory()
    started = asyncio.Event()
    release = asyncio.Event()
    owned = []

    def factory(loop, coroutine, **kwargs):
        if "arm_time_limits_async.<locals>._fire_" in coroutine.__qualname__:

            async def finish_owned_timer():
                try:
                    await coroutine
                finally:
                    started.set()
                    await release.wait()

            task = asyncio.Task(finish_owned_timer(), loop=loop, **kwargs)
            owned.append(task)
            return task
        if original_factory is not None:
            return original_factory(loop, coroutine, **kwargs)
        return asyncio.Task(coroutine, loop=loop, **kwargs)

    loop.set_task_factory(factory)
    caller = None
    try:
        handle = arm_time_limits_async(
            CancellationToken(), soft_time_limit=60, time_limit=90
        )
        await asyncio.sleep(0)  # Both real timer coroutines own their cleanup now.
        caller = asyncio.create_task(handle.disarm_async())
        await started.wait()
        for reason in ("first cancellation", "second cancellation"):
            caller.cancel(reason)
            await asyncio.sleep(0)
            assert not caller.done()
            assert not all(task.done() for task in owned)
        release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await caller
        assert caught.value.args == ("second cancellation",)
        assert len(owned) == 2 and all(task.done() for task in owned)
        await handle.disarm_async()  # Idempotent completed cleanup.
    finally:
        loop.set_task_factory(original_factory)
        release.set()
        if caller is not None and not caller.done():
            caller.cancel()
        await asyncio.gather(
            *(owned + ([caller] if caller else [])), return_exceptions=True
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_type", [LocalRuntime, AsyncLocalRuntime])
async def test_real_sqlite_drift_requires_explicit_true(
    runtime_type, checkpoint_store, caplog
):
    workflow, node = make_workflow()
    runtime = runtime_type(
        checkpoint_store=checkpoint_store, checkpoint_after_each_node=True
    )
    try:
        await runtime.execute_async(workflow, idempotency_key="explicit-drift")
        key = (await checkpoint_store.list_keys(""))[0]
        payload = decode_checkpoint_payload(await checkpoint_store.load(key))
        await checkpoint_store.save(
            key,
            encode_checkpoint_payload(
                workflow_fingerprint="other-shape", tracker_state=payload["tracker"]
            ),
        )
        for override in ("false", "true", 0, 1, None, [], {}):
            with pytest.raises(
                TypeError, match="force_resume_with_drift must be a bool"
            ):
                await runtime.execute_async(
                    workflow,
                    idempotency_key="explicit-drift",
                    force_resume_with_drift=override,
                )
            assert node.calls == 1
        with pytest.raises(WorkflowShapeDriftError):
            await runtime.execute_async(
                workflow,
                idempotency_key="explicit-drift",
                force_resume_with_drift=False,
            )
        caplog.clear()
        result, _ = await runtime.execute_async(
            workflow, idempotency_key="explicit-drift", force_resume_with_drift=True
        )
        assert result == {"operation": {"value": 42}} and node.calls == 1
        assert [r.getMessage() for r in caplog.records if r.levelno >= 30] == [
            "durable.resume.shape_drift_forced"
        ]
    finally:
        if isinstance(runtime, AsyncLocalRuntime):
            await runtime.cleanup()
        runtime.close()


@pytest.mark.asyncio
async def test_durable_dispatch_rejects_non_bool_before_real_queue_write(tmp_path):
    from kailash.infrastructure.task_queue import SQLTaskQueue, SQLTaskQueueDispatcher
    from kailash.workflow.builder import WorkflowBuilder

    connection = ConnectionManager(f"sqlite:///{tmp_path / 'queue.db'}")
    await connection.initialize()
    dispatcher = SQLTaskQueueDispatcher(connection)
    await dispatcher.initialize()
    queue = SQLTaskQueue(connection)
    engine = (
        DurableExecutionEngine.builder()
        .dispatch_via(dispatcher)
        .execution_mode("dispatch_only")
        .build()
    )
    builder = WorkflowBuilder()
    builder.add_node(
        "DataTransformer", "n", {"data": {"value": 42}, "transformations": []}
    )
    workflow = builder.build()
    try:
        for override in ("false", "true", "", 0, 1, None, [], {}):
            with pytest.raises(
                TypeError, match="force_resume_with_drift must be a bool"
            ):
                await engine.execute(workflow, force_resume_with_drift=override)
            assert await queue.dequeue() is None
        for override in (False, True):
            result, run_id = await engine.execute(
                workflow,
                idempotency_key=str(override),
                force_resume_with_drift=override,
            )
            assert result == {} and isinstance(run_id, str)
            assert await queue.dequeue() is not None
    finally:
        await engine.runtime.cleanup()
        engine.runtime.close()
        await connection.close()


@pytest.mark.asyncio
async def test_sqlite_queue_known_dialect_has_no_identifier_warning(tmp_path, caplog):
    from kailash.infrastructure.task_queue import SQLTaskQueue

    connection = ConnectionManager(f"sqlite:///{tmp_path / 'known-dialect.db'}")
    try:
        await connection.initialize()
        with caplog.at_level("WARNING"):
            queue = SQLTaskQueue(connection, table_name="q" * 70)
            await queue.initialize()
            task_id = await queue.enqueue({"value": 42})
            message = await queue.dequeue()
        assert message is not None and message.task_id == task_id
        assert message.payload == {"value": 42}
        assert not caplog.records
    finally:
        await connection.close()


@pytest.mark.parametrize(
    "url,too_long",
    [
        ("postgresql://localhost/identifier_probe", 64),
        ("mysql://localhost/identifier_probe", 65),
        ("sqlite:///:memory:", 129),
    ],
)
def test_queue_rejects_names_exceeding_known_dialect_before_connect(url, too_long):
    from kailash.db.dialect import IdentifierError
    from kailash.infrastructure.task_queue import SQLTaskQueue

    connection = ConnectionManager(url)
    with pytest.raises(IdentifierError, match="exceeds"):
        SQLTaskQueue(connection, table_name="q" * too_long)
    assert connection._pool is None


@pytest.mark.asyncio
async def test_long_queue_tables_keep_distinct_working_indexes(tmp_path):
    from kailash.infrastructure.task_queue import SQLTaskQueue

    connection = ConnectionManager(f"sqlite:///{tmp_path / 'long-indexes.db'}")
    try:
        await connection.initialize()
        tables = ["q" * 127 + ending for ending in ("a", "b")]
        for table, value in zip(tables, ("first", "second")):
            queue = SQLTaskQueue(connection, table_name=table)
            await queue.initialize()
            await queue.enqueue({"owner": value})
            # A separately constructed queue derives exactly the same names.
            restored = SQLTaskQueue(connection, table_name=table)
            await restored.initialize()
            message = await restored.dequeue()
            assert message is not None and message.payload == {"owner": value}
        rows = await connection.fetch(
            "SELECT name, tbl_name FROM sqlite_master WHERE type = ? AND name LIKE ?",
            "index",
            "idx_%",
        )
        assert len(rows) == 4
        assert len({row["name"] for row in rows}) == 4
        assert {row["tbl_name"] for row in rows} == set(tables)
        assert all(len(row["name"]) <= 128 for row in rows)
    finally:
        await connection.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_part", ["table", "dequeue", "stale"])
async def test_queue_validates_all_names_before_any_ddl(tmp_path, bad_part):
    from kailash.db.dialect import IdentifierError
    from kailash.infrastructure.task_queue import SQLTaskQueue

    connection = ConnectionManager(f"sqlite:///{tmp_path / 'no-partial-schema.db'}")
    try:
        await connection.initialize()
        if bad_part == "table":
            with pytest.raises(IdentifierError):
                SQLTaskQueue(connection, table_name="q" * 129)
        else:
            queue = SQLTaskQueue(connection, table_name="valid_queue")
            # Fault injection at the derived-name boundary must fail before DDL.
            setattr(queue, "_" + bad_part + "_index", "invalid index name")
            with pytest.raises(IdentifierError):
                await queue.initialize()
        assert (
            await connection.fetch(
                "SELECT name FROM sqlite_master WHERE type = ?", "table"
            )
            == []
        )
    finally:
        await connection.close()


@pytest.mark.parametrize(
    "url,limit",
    [
        ("postgresql://localhost/identifier_probe", 63),
        ("mysql://localhost/identifier_probe", 64),
    ],
)
def test_non_sqlite_derived_queue_names_fit_actual_dialect(url, limit):
    from kailash.infrastructure.task_queue import SQLTaskQueue

    connection = ConnectionManager(url)
    first = SQLTaskQueue(connection, table_name="q" * (limit - 1) + "a")
    second = SQLTaskQueue(connection, table_name="q" * (limit - 1) + "b")
    names = [
        first._dequeue_index,
        first._stale_index,
        second._dequeue_index,
        second._stale_index,
    ]
    assert len(set(names)) == 4
    for name in names:
        assert len(name) <= limit
        connection.dialect.quote_identifier(name)
    short = SQLTaskQueue(connection, table_name="short")
    assert short._dequeue_index == "idx_short_dequeue"
    assert short._stale_index == "idx_short_stale"
    assert connection._pool is None
