"""Real loop ownership, aggregate capacity, and lease cleanup regressions."""

import asyncio
import gc
import threading
import weakref
from concurrent.futures import ThreadPoolExecutor

import pytest

from kailash.utils.resource_manager import (
    AsyncResourcePool,
    ResourcePool,
    async_managed_resource,
)


class OwnedResource:
    def __init__(self):
        self.owner = asyncio.get_running_loop()
        self.closed = False

    async def close(self):
        assert asyncio.get_running_loop() is self.owner
        await asyncio.sleep(0)
        self.closed = True


def test_distinct_loops_never_borrow_each_others_idle_resource():
    pool = AsyncResourcePool(OwnedResource, max_size=2, cleanup=lambda r: r.close())
    loops = [asyncio.new_event_loop(), asyncio.new_event_loop()]
    resources = []

    async def borrow():
        async with pool.acquire() as resource:
            assert resource.owner is asyncio.get_running_loop()
            resources.append(resource)

    try:
        for loop in loops:
            loop.run_until_complete(borrow())
        assert resources[0] is not resources[1]
        loops[0].run_until_complete(borrow())
        assert resources[2] is resources[0]
    finally:
        for loop in loops:
            loop.run_until_complete(pool.cleanup_all())
            loop.close()
    assert all(resource.closed for resource in resources)


def test_max_size_remains_aggregate_across_owner_loops():
    pool = AsyncResourcePool(
        OwnedResource, max_size=1, timeout=0.02, cleanup=lambda r: r.close()
    )
    loops = [asyncio.new_event_loop(), asyncio.new_event_loop()]

    async def borrow():
        async with pool.acquire() as resource:
            return resource

    try:
        first = loops[0].run_until_complete(borrow())
        with pytest.raises(TimeoutError):
            loops[1].run_until_complete(borrow())
        loops[0].run_until_complete(pool.cleanup_all())
        assert first.closed
        second = loops[1].run_until_complete(borrow())
        assert second is not first
    finally:
        for loop in loops:
            loop.run_until_complete(pool.cleanup_all())
            loop.close()


@pytest.mark.asyncio
async def test_cleanup_retires_borrowed_resource_without_interrupting_lease():
    pool = AsyncResourcePool(OwnedResource, max_size=1, cleanup=lambda r: r.close())
    async with pool.acquire() as first:
        await pool.cleanup_all()
        assert not first.closed
    assert first.closed
    async with pool.acquire() as second:
        assert second is not first
        assert not second.closed
    await pool.cleanup_all()
    assert second.closed


@pytest.mark.asyncio
async def test_unhashable_resource_and_awaitable_factory_cleanup():
    closed = []

    async def create():
        return {"connected": True}

    async def close(resource):
        await asyncio.sleep(0)
        resource["connected"] = False
        closed.append(resource)

    pool = AsyncResourcePool(lambda: create(), cleanup=lambda r: close(r))
    async with pool.acquire() as resource:
        assert resource == {"connected": True}
    await pool.cleanup_all()
    assert closed == [{"connected": False}]


@pytest.mark.asyncio
async def test_async_managed_resource_awaits_returned_cleanup():
    resource = OwnedResource()
    async with async_managed_resource(
        "loop-owned-test", resource, cleanup=lambda r: r.close()
    ):
        assert not resource.closed
    assert resource.closed


@pytest.mark.asyncio
async def test_cleanup_waits_for_all_idle_closes_when_caller_is_cancelled():
    started = asyncio.Event()
    finish = asyncio.Event()
    resources = []

    async def close(resource):
        started.set()
        await finish.wait()
        await resource.close()

    pool = AsyncResourcePool(OwnedResource, max_size=2, cleanup=close)
    async with pool.acquire() as first:
        async with pool.acquire() as second:
            resources.extend([first, second])
    task = asyncio.create_task(pool.cleanup_all())
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(resource.closed for resource in resources)
    async with pool.acquire() as replacement:
        assert not replacement.closed
    await pool.cleanup_all()


@pytest.mark.asyncio
async def test_cancelled_factory_releases_aggregate_capacity():
    entered = asyncio.Event()
    release = asyncio.Event()

    async def factory():
        entered.set()
        await release.wait()
        return OwnedResource()

    pool = AsyncResourcePool(factory, max_size=1, cleanup=lambda r: r.close())

    async def borrow():
        async with pool.acquire() as resource:
            return resource

    task = asyncio.create_task(borrow())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    release.set()
    resource = await borrow()
    assert not resource.closed
    await pool.cleanup_all()
    assert resource.closed


def test_cleaned_owner_loop_is_not_retained_by_global_pool():
    pool = AsyncResourcePool(OwnedResource, cleanup=lambda r: r.close())
    loop = asyncio.new_event_loop()
    reference = weakref.ref(loop)

    async def use_and_close():
        async with pool.acquire():
            await pool.cleanup_all()

    loop.run_until_complete(use_and_close())
    loop.close()
    del loop
    gc.collect()
    assert reference() is None


def test_sync_cleanup_retires_lease_and_supports_unhashable_resources():
    pool = ResourcePool(
        lambda: {"open": True},
        max_size=1,
        cleanup=lambda resource: resource.update(open=False),
    )
    with pool.acquire() as first:
        pool.cleanup_all()
        assert first["open"]
    assert not first["open"]
    with pool.acquire() as second:
        assert second is not first
        assert second["open"]
    pool.cleanup_all()
    assert not second["open"]


@pytest.mark.asyncio
async def test_http_context_reuses_session_then_closes_it(httpserver):
    from kailash.nodes.api.http import AsyncHTTPRequestNode, _async_http_session_pool

    httpserver.expect_request("/owned").respond_with_json({"ok": True})
    async with AsyncHTTPRequestNode() as node:
        first = await node.async_run(url=httpserver.url_for("/owned"))
        session = _async_http_session_pool._pool[0]
        second = await node.async_run(url=httpserver.url_for("/owned"))
        assert _async_http_session_pool._pool == [session]
        assert first["success"] and second["success"]
        assert not session.closed
    assert session.closed
    await node.cleanup()
    httpserver.check_assertions()


def test_http_two_live_owner_loops_keep_independent_sessions(httpserver):
    from kailash.nodes.api.http import AsyncHTTPRequestNode, _async_http_session_pool

    httpserver.expect_request("/parallel").respond_with_json({"ok": True})
    barrier = threading.Barrier(2)

    async def worker(index):
        node = AsyncHTTPRequestNode()
        try:
            result = await node.async_run(url=httpserver.url_for("/parallel"))
            assert result["success"]
            session = _async_http_session_pool._pool[0]
            assert session._loop is asyncio.get_running_loop()
            await asyncio.to_thread(barrier.wait, 10)
            if index == 0:
                await node.cleanup()
                assert session.closed
            await asyncio.to_thread(barrier.wait, 10)
            if index == 1:
                assert not session.closed
                second = await node.async_run(url=httpserver.url_for("/parallel"))
                assert second["success"]
                assert _async_http_session_pool._pool == [session]
            return session
        finally:
            await node.cleanup()

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(asyncio.run, worker(i)) for i in range(2)]
        first, second = [future.result(timeout=30) for future in futures]
    assert first is not second
    assert first.closed and second.closed
    httpserver.check_assertions()


@pytest.mark.asyncio
async def test_rest_cleanup_is_safe_before_transport_exists():
    from kailash.nodes.api.rest import RESTClientNode

    await RESTClientNode().cleanup()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_retired_lease_cleanup_survives_repeated_cancellation(
    cleanup_fails, caplog
):
    entered = asyncio.Event()
    finish = asyncio.Event()
    resources = []

    async def close(resource):
        entered.set()
        await finish.wait()
        await resource.close()
        if cleanup_fails:
            raise RuntimeError("controlled cleanup failure after close")

    pool = AsyncResourcePool(OwnedResource, max_size=1, cleanup=close)

    async def use():
        async with pool.acquire() as resource:
            resources.append(resource)
            await pool.cleanup_all()

    task = asyncio.create_task(use())
    await entered.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    await asyncio.sleep(0)
    assert pool._created_count == 1
    assert not resources[0].closed
    finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert resources[0].closed
    assert pool._created_count == 0
    if cleanup_fails:
        assert "controlled cleanup failure after close" in caplog.text


@pytest.mark.asyncio
async def test_async_rest_delegate_cleanup_closes_actual_session(httpserver):
    from kailash.nodes.api.http import _async_http_session_pool
    from kailash.nodes.api.rest import AsyncRESTClientNode

    httpserver.expect_request("/delegated").respond_with_json({"ok": True})
    node = AsyncRESTClientNode()
    try:
        result = await node.async_run(
            base_url=httpserver.url_for(""), resource="delegated"
        )
        assert result["success"]
        session = _async_http_session_pool._pool[0]
        assert not session.closed
    finally:
        await node.cleanup()
    assert session.closed
    httpserver.check_assertions()
