"""Independent real registry/socket ownership probes; no production mutations."""

import asyncio
import gc
import logging
import threading
import warnings

import pytest

from kailash.nodes.base import NodeParameter
from kailash.nodes.base_async import AsyncNode
from kailash.nodes.data.async_sql import AsyncSQLDatabaseNode
from kailash.resources.factory import ResourceFactory
from kailash.resources.registry import ResourceRegistry
from kailash.runtime.async_local import AsyncLocalRuntime
from kailash.workflow.graph import Workflow


class SocketResource:
    def __init__(self, server):
        self.server = server
        self.owner = asyncio.get_running_loop()
        self.closes = []
        self.completed = asyncio.Event()

    async def aclose(self):
        loop = asyncio.get_running_loop()
        self.closes.append(loop)
        self.server.close()
        await self.server.wait_closed()
        await asyncio.sleep(0)
        self.completed.set()


class SocketFactory(ResourceFactory):
    def __init__(self):
        self.created = []

    async def create(self):
        async def connected(reader, writer):
            writer.close()
            await writer.wait_closed()

        item = SocketResource(await asyncio.start_server(connected, "127.0.0.1", 0))
        self.created.append(item)
        return item

    def get_config(self):
        return {"kind": "real-local-tcp-server"}


def build():
    registry = ResourceRegistry()
    factory = SocketFactory()
    registry.register_factory("socket", factory)

    class UseResource(AsyncNode):
        def get_parameters(self):
            return {
                "resource_registry": NodeParameter(
                    name="resource_registry", type=ResourceRegistry, required=False
                )
            }

        async def async_run(self, **kwargs):
            assert kwargs["resource_registry"] is registry
            resource = await kwargs["resource_registry"].get_resource("socket")
            return {
                "loop": id(asyncio.get_running_loop()),
                "resource_owner": id(resource.owner),
                "open": bool(resource.server.sockets),
            }

    workflow = Workflow("lifecycle-probe", name="lifecycle-probe")
    workflow.add_node("resource", UseResource())
    return registry, factory, workflow


def emergency_release(factory):
    # Keep failed-baseline probes from leaking OS sockets; does not mark observed
    # aclose completion or alter assertions. This is fixture teardown only.
    for resource in factory.created:
        resource.server.close()


def test_native_sync_reuses_owned_loop_without_threads(monkeypatch):
    registry, factory, workflow = build()
    runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
    starts = []
    original = threading.Thread.start

    def observed(self, *args, **kwargs):
        starts.append(self.name)
        raise AssertionError("native synchronous execution must not start threads")

    monkeypatch.setattr(threading.Thread, "start", observed)
    try:
        first, _ = runtime.execute(workflow)
        second, _ = runtime.execute(workflow)
        runtime.close()
        data = {
            "first": first["resource"],
            "second": second["resource"],
            "threads": starts,
            "resource_count": len(factory.created),
            "closes": [len(r.closes) for r in factory.created],
            "closed": [r.completed.is_set() for r in factory.created],
            "ref_count": runtime._ref_count,
        }
        print("OWNERSHIP", data)
        assert starts == []
        assert (
            first["resource"]["loop"]
            == second["resource"]["loop"]
            == first["resource"]["resource_owner"]
        )
        assert len(factory.created) == 1
        resource = factory.created[0]
        assert resource.completed.is_set() and resource.closes == [resource.owner]
        assert resource.owner.is_closed() and runtime._ref_count == 0
        runtime.close()
        assert len(resource.closes) == 1
    finally:
        runtime.close()
        emergency_release(factory)


def test_async_context_finishes_registry_and_preserves_caller_loop():
    async def exercise():
        loop = asyncio.get_running_loop()
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        try:
            async with runtime:
                result, _ = await runtime.execute_async(workflow)
                assert result["resource"]["open"]
            resource = factory.created[0]
            print(
                "ASYNC_EXIT",
                {
                    "closed": resource.completed.is_set(),
                    "closes": len(resource.closes),
                    "ref_count": runtime._ref_count,
                    "caller_closed": loop.is_closed(),
                },
            )
            assert resource.completed.is_set() and resource.closes == [loop]
            assert runtime._ref_count == 0 and not loop.is_closed()
            await asyncio.sleep(0)
            assert asyncio.get_running_loop() is loop
            runtime.close()
            assert len(resource.closes) == 1
        finally:
            runtime.close()
            emergency_release(factory)

    asyncio.run(exercise())


def test_foreign_thread_close_completes_on_live_owner_loop():
    async def exercise():
        loop = asyncio.get_running_loop()
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        try:
            await runtime.execute_async(workflow)
            resource = factory.created[0]
            await asyncio.wait_for(asyncio.to_thread(runtime.close), timeout=8)
            print(
                "FOREIGN_CLOSE",
                {
                    "closed": resource.completed.is_set(),
                    "close_loops": [id(x) for x in resource.closes],
                    "owner": id(loop),
                    "ref_count": runtime._ref_count,
                },
            )
            assert resource.completed.is_set() and resource.closes == [loop]
            assert not loop.is_closed() and runtime._ref_count == 0
            await asyncio.sleep(0)
            runtime.close()
            assert len(resource.closes) == 1
        finally:
            runtime.close()
            emergency_release(factory)

    asyncio.run(exercise())


def test_reference_count_delays_cleanup_until_last_consumer():
    async def exercise():
        loop = asyncio.get_running_loop()
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        try:
            assert runtime.acquire() is runtime
            async with runtime:
                await runtime.execute_async(workflow)
            resource = factory.created[0]
            assert (
                runtime._ref_count == 1
                and resource.closes == []
                and resource.server.sockets
            )
            async with runtime:
                pass
            print(
                "REFCOUNT_EXIT",
                {
                    "count": runtime._ref_count,
                    "closed": resource.completed.is_set(),
                    "closes": len(resource.closes),
                },
            )
            assert (
                runtime._ref_count == 0
                and resource.completed.is_set()
                and resource.closes == [loop]
            )
            runtime.close()
            assert len(resource.closes) == 1 and not loop.is_closed()
        finally:
            runtime.close()
            runtime.close()
            emergency_release(factory)

    asyncio.run(exercise())


def test_same_owner_sync_close_schedules_observable_completion():
    async def exercise():
        loop = asyncio.get_running_loop()
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        try:
            await runtime.execute_async(workflow)
            resource = factory.created[0]
            runtime.close()
            await asyncio.wait_for(resource.completed.wait(), timeout=2)
            assert (
                resource.closes == [loop]
                and not loop.is_closed()
                and runtime._ref_count == 0
            )
            runtime.close()
            assert len(resource.closes) == 1
        finally:
            runtime.close()
            emergency_release(factory)

    asyncio.run(exercise())


def test_foreign_owner_thread_loop_survives_main_thread_close():
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    factory = None
    runtime = None

    def own():
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=own, name="independent-runtime-owner")
    thread.start()
    assert ready.wait(2)

    async def initialize():
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        await runtime.execute_async(workflow)
        return runtime, factory

    try:
        runtime, factory = asyncio.run_coroutine_threadsafe(initialize(), loop).result(
            5
        )
        resource = factory.created[0]
        assert resource.owner is loop
        runtime.close()
        print(
            "BACKGROUND_OWNER_CLOSE",
            {
                "closed": resource.completed.is_set(),
                "closes": len(resource.closes),
                "owner_running": loop.is_running(),
                "ref_count": runtime._ref_count,
            },
        )
        assert (
            resource.completed.is_set()
            and resource.closes == [loop]
            and runtime._ref_count == 0
        )
        assert (
            asyncio.run_coroutine_threadsafe(asyncio.sleep(0, result=42), loop).result(
                2
            )
            == 42
        )
        assert loop.is_running()
        runtime.close()
        assert len(resource.closes) == 1
    finally:
        if runtime is not None:
            runtime.close()
        if factory is not None:
            loop.call_soon_threadsafe(emergency_release, factory)
        loop.call_soon_threadsafe(loop.stop)
        thread.join(3)
        assert not thread.is_alive()
        loop.close()


def test_cancelled_context_exit_finishes_real_resource():
    registry, factory, workflow = build()
    runtime = None

    async def exercise():
        nonlocal runtime
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        async with runtime:
            await runtime.execute_async(workflow)
            resource = factory.created[0]
            original = resource.aclose

            async def delayed_close():
                asyncio.get_running_loop().call_soon(
                    asyncio.current_task().get_loop().call_soon, host.cancel
                )
                await asyncio.sleep(0.02)
                await original()

            resource.aclose = delayed_close
            host = asyncio.current_task()

    try:
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(exercise())
        resource = factory.created[0]
        print(
            "CANCELLED_EXIT",
            {
                "completed": resource.completed.is_set(),
                "socket_open": bool(resource.server.sockets),
                "ref_count": runtime._ref_count,
            },
        )
        assert resource.completed.is_set() and not resource.server.sockets
    finally:
        emergency_release(factory)


def test_concurrent_sync_admission_does_not_orphan_coroutine():
    entered = threading.Event()
    release = []
    errors = []

    class Waiting(AsyncNode):
        def get_parameters(self):
            return {}

        async def async_run(self, **kwargs):
            gate = asyncio.Event()
            release.append((asyncio.get_running_loop(), gate))
            entered.set()
            await gate.wait()
            return {"ok": True}

    workflow = Workflow("concurrent-sync", name="concurrent-sync")
    workflow.add_node("wait", Waiting())
    runtime = AsyncLocalRuntime(enable_monitoring=False)

    def first():
        try:
            runtime.execute(workflow)
        except BaseException as e:
            errors.append(e)

    thread = threading.Thread(target=first)
    thread.start()
    assert entered.wait(3)
    try:
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            with pytest.raises(RuntimeError):
                runtime.execute(workflow)
            gc.collect()
        orphaned = [
            str(w.message) for w in captured if "was never awaited" in str(w.message)
        ]
        print("CONCURRENT_SYNC", {"orphaned": orphaned})
        assert orphaned == []
    finally:
        if release:
            release[0][0].call_soon_threadsafe(release[0][1].set)
        thread.join(5)
        assert not thread.is_alive()
        runtime.close()
        assert not errors


def test_foreign_owner_close_does_not_block_active_caller_loop():
    owner = asyncio.new_event_loop()
    ready = threading.Event()
    entered = threading.Event()
    caller_progress = threading.Event()
    rescue = threading.Event()
    state = {}

    def run_owner():
        asyncio.set_event_loop(owner)
        ready.set()
        owner.run_forever()

    worker = threading.Thread(target=run_owner)
    worker.start()
    assert ready.wait(2)

    async def initialize():
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        await runtime.execute_async(workflow)
        resource = factory.created[0]
        gate = asyncio.Event()
        original = resource.aclose

        async def dependent_close():
            entered.set()
            await gate.wait()
            await original()

        resource.aclose = dependent_close
        state.update(runtime=runtime, factory=factory, resource=resource, gate=gate)

    asyncio.run_coroutine_threadsafe(initialize(), owner).result(5)

    def watchdog():
        assert entered.wait(3)
        if not caller_progress.wait(0.5):
            rescue.set()
            owner.call_soon_threadsafe(state["gate"].set)

    watch = threading.Thread(target=watchdog)
    watch.start()

    async def caller():
        state["runtime"].close()
        caller_progress.set()
        owner.call_soon_threadsafe(state["gate"].set)
        for _ in range(200):
            if state["resource"].completed.is_set():
                break
            await asyncio.sleep(0.005)
        print(
            "FOREIGN_ACTIVE_CALLER",
            {
                "watchdog_rescue": rescue.is_set(),
                "closed": state["resource"].completed.is_set(),
            },
        )
        assert not rescue.is_set()
        assert state["resource"].completed.is_set()

    try:
        asyncio.run(caller())
    finally:
        caller_progress.set()
        owner.call_soon_threadsafe(state["gate"].set)
        watch.join(2)
        owner.call_soon_threadsafe(emergency_release, state["factory"])
        owner.call_soon_threadsafe(owner.stop)
        worker.join(3)
        assert not worker.is_alive()
        owner.close()


@pytest.mark.asyncio
async def test_repeated_cancellation_waits_for_cleanup_before_propagating():
    registry, factory, workflow = build()
    runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
    host = asyncio.current_task()
    try:
        with pytest.raises(asyncio.CancelledError, match="first-cleanup-cancel"):
            async with runtime:
                await runtime.execute_async(workflow)
                resource = factory.created[0]
                original = resource.aclose

                async def cancel_repeatedly():
                    host.cancel("first-cleanup-cancel")
                    await asyncio.sleep(0)
                    host.cancel("second-cleanup-cancel")
                    await asyncio.sleep(0)
                    await original()

                resource.aclose = cancel_repeatedly
        assert resource.completed.is_set()
        assert resource.closes == [asyncio.get_running_loop()]
        assert runtime._close_task.done()
    finally:
        runtime.close()
        emergency_release(factory)


def test_distinct_open_execution_loop_is_rejected_before_resource_work():
    registry, factory, workflow = build()
    runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
    try:
        first, _ = runtime.execute(workflow)
        owner = factory.created[0].owner

        async def other_loop():
            with pytest.raises(RuntimeError, match="another event loop"):
                await runtime.execute_async(workflow)

        asyncio.run(other_loop())
        assert len(factory.created) == 1
        assert factory.created[0].closes == []
        assert not owner.is_closed()
        second, _ = runtime.execute(workflow)
        assert first["resource"]["loop"] == second["resource"]["loop"]
    finally:
        runtime.close()
        emergency_release(factory)


@pytest.mark.asyncio
async def test_same_loop_concurrent_workflows_keep_one_registry_owner():
    registry, factory, workflow = build()
    async with AsyncLocalRuntime(
        resource_registry=registry, enable_monitoring=False
    ) as runtime:
        outcomes = await asyncio.gather(
            runtime.execute_async(workflow), runtime.execute_async(workflow)
        )
        assert all(result["resource"]["open"] for result, _ in outcomes)
        assert len(factory.created) == 1
    assert factory.created[0].completed.is_set()
    assert factory.created[0].closes == [asyncio.get_running_loop()]


def test_mixed_loop_execution_fails_before_resource_use():
    owner = asyncio.new_event_loop()
    ready = threading.Event()
    state = {}

    def run():
        asyncio.set_event_loop(owner)
        ready.set()
        owner.run_forever()

    thread = threading.Thread(target=run)
    thread.start()
    assert ready.wait(2)

    async def initialize():
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        await runtime.execute_async(workflow)
        state.update(runtime=runtime, factory=factory, workflow=workflow)

    asyncio.run_coroutine_threadsafe(initialize(), owner).result(4)

    async def wrong_loop():
        with pytest.raises(RuntimeError, match="another event loop"):
            await state["runtime"].execute_async(state["workflow"])
        assert (
            len(state["factory"].created) == 1
            and state["factory"].created[0].closes == []
        )

    try:
        asyncio.run(wrong_loop())
        state["runtime"].close()
        assert state["factory"].created[0].completed.is_set()
    finally:
        state["runtime"].close()
        owner.call_soon_threadsafe(emergency_release, state["factory"])
        owner.call_soon_threadsafe(owner.stop)
        thread.join(3)
        owner.close()


def test_sql_pool_disposal_receives_actual_execution_loop(monkeypatch):
    original = AsyncSQLDatabaseNode.clear_shared_pools
    calls = []

    async def observed(cls, *args, **kwargs):
        calls.append((id(asyncio.get_running_loop()), kwargs.get("loop_id")))
        return await original(*args, **kwargs)

    monkeypatch.setattr(
        AsyncSQLDatabaseNode, "clear_shared_pools", classmethod(observed)
    )
    registry, factory, workflow = build()
    runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
    try:
        result, _ = runtime.execute(workflow)
        owner = result["resource"]["loop"]
        runtime.close()
        assert calls and all(
            actual == requested == owner for actual, requested in calls
        )
        assert factory.created[0].completed.is_set()
    finally:
        runtime.close()
        emergency_release(factory)


def test_resource_callback_failure_is_observed_without_exception_content(caplog):
    secret = "opaque-close-callback-canary-61084"

    async def exercise():
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        try:
            async with runtime:
                await runtime.execute_async(workflow)
                resource = factory.created[0]

                async def failing():
                    raise RuntimeError(secret)

                resource.aclose = failing
            errors = [
                r
                for r in caplog.records
                if "Error cleaning up resource" in r.getMessage()
            ]
            assert len(errors) == 1
            assert "RuntimeError@" in errors[0].getMessage()
            assert secret not in errors[0].getMessage()
        finally:
            runtime.close()
            emergency_release(factory)

    with caplog.at_level(logging.ERROR):
        asyncio.run(exercise())


def test_concurrent_final_releases_close_resource_exactly_once():
    async def exercise():
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        runtime.acquire()
        barrier = threading.Barrier(2)
        try:
            await runtime.execute_async(workflow)
            resource = factory.created[0]

            def release():
                barrier.wait(timeout=3)
                runtime.close()

            await asyncio.wait_for(
                asyncio.gather(asyncio.to_thread(release), asyncio.to_thread(release)),
                timeout=5,
            )
            assert (
                runtime._ref_count == 0
                and resource.completed.is_set()
                and resource.closes == [resource.owner]
            )
            runtime.close()
            assert len(resource.closes) == 1
        finally:
            runtime.close()
            runtime.close()
            emergency_release(factory)

    asyncio.run(exercise())
