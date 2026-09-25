"""Real task ownership at synchronous and asynchronous construction boundaries."""

import asyncio
import gc
import warnings

from kailash.middleware.gateway.event_store import EventStore, EventType


def test_sync_construction_defers_coroutine_and_append_starts_flush():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        store = EventStore(storage_backend="memory")
        gc.collect()
        assert store._flush_task is None

        async def append_and_close():
            try:
                event = await store.append(EventType.REQUEST_CREATED, "sync", {})
                task = store._flush_task
                assert task is not None and not task.done()
                assert task.get_loop() is asyncio.get_running_loop()
            finally:
                await store.close()
            assert task.done()
            assert await store.get_events("sync") == [event]
            assert store._buffer == []

        asyncio.run(append_and_close())
        gc.collect()
    assert not caught


def test_async_construction_starts_flush_and_close_drains():
    async def exercise():
        store = EventStore(storage_backend="memory", flush_interval_seconds=3600)
        task = store._flush_task
        try:
            assert task is not None and not task.done()
            assert task.get_loop() is asyncio.get_running_loop()
            event = await store.append(EventType.REQUEST_CREATED, "async", {})
            # Let the periodic task enter its sleep before cancelling it.
            await asyncio.sleep(0)
        finally:
            await store.close()
        assert task.done()
        assert await store.get_events("async") == [event]
        assert store._buffer == []

    asyncio.run(exercise())
