"""Awaited runtime close preserves ownership and the original cleanup failure."""

import asyncio
import threading

import pytest

from kailash.runtime import AsyncLocalRuntime


@pytest.mark.asyncio
@pytest.mark.parametrize("error_type", [RuntimeError, asyncio.CancelledError])
async def test_aclose_preserves_cleanup_error_and_releases_executor(error_type):
    error = error_type("original cleanup failure")

    class FailingCleanupRuntime(AsyncLocalRuntime):
        async def cleanup(self):
            self.cleanup_calls += 1
            raise error

    runtime = FailingCleanupRuntime(enable_monitoring=False)
    runtime.cleanup_calls = 0
    try:
        with pytest.raises(error_type) as observed:
            await runtime.aclose()
        assert observed.value is error
        assert runtime.cleanup_calls == 1
        assert runtime._ref_count == 0
        assert runtime.thread_pool is None
        assert runtime._close_task.done()
        assert not asyncio.get_running_loop().is_closed()
    finally:
        await AsyncLocalRuntime.cleanup(runtime)
        runtime.close()


@pytest.mark.parametrize("cancel_caller", [False, True])
def test_foreign_aclose_waits_for_existing_owner_task(cancel_caller):
    from tests.regression.test_async_runtime_cleanup_ownership import build

    owner = asyncio.new_event_loop()
    thread = threading.Thread(target=owner.run_forever)
    thread.start()
    state = {}

    async def prepare():
        registry, factory, workflow = build()
        runtime = AsyncLocalRuntime(resource_registry=registry, enable_monitoring=False)
        state["runtime"] = runtime
        await runtime.execute_workflow_async(workflow, inputs={})
        resource = factory.created[0]
        release = asyncio.Event()
        entered = asyncio.Event()
        original = resource.aclose

        async def delayed():
            entered.set()
            await release.wait()
            await original()

        resource.aclose = delayed
        state.update(runtime=runtime, resource=resource, release=release)
        runtime.close()
        await entered.wait()

    async def foreign():
        task = asyncio.create_task(state["runtime"].aclose())
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert not task.done()
        if cancel_caller:
            task.cancel("original foreign caller cancellation")
            await asyncio.sleep(0)
            task.cancel("second foreign caller cancellation")
            await asyncio.sleep(0)
            assert not task.done()
        owner.call_soon_threadsafe(state["release"].set)
        if cancel_caller:
            with pytest.raises(asyncio.CancelledError, match="original foreign caller"):
                await task
        else:
            await task
        assert state["resource"].completed.is_set()
        assert not state["resource"].server.sockets
        assert state["resource"].closes == [owner]
        assert owner.is_running()
        # A completed foreign task also remains safely awaitable.
        await state["runtime"].aclose()

    try:
        asyncio.run_coroutine_threadsafe(prepare(), owner).result(5)
        asyncio.run(foreign())
    finally:
        if "release" in state:
            owner.call_soon_threadsafe(state["release"].set)

            async def finish():
                await state["runtime"]._close_task

            asyncio.run_coroutine_threadsafe(finish(), owner).result(5)
        elif "runtime" in state:
            asyncio.run_coroutine_threadsafe(state["runtime"].aclose(), owner).result(5)
        owner.call_soon_threadsafe(owner.stop)
        thread.join(5)
        assert not thread.is_alive()
        owner.close()
