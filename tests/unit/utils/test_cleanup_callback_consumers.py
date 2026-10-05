"""Source-exact canonical waiter support from 848ad6f; callback coverage remains open."""

import asyncio
import logging

import pytest

from kailash.utils.resource_manager import _await_cleanup


@pytest.mark.asyncio
async def test_cleanup_preserves_owned_task_and_future():
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    loop.call_soon(future.set_result, 19)
    assert await _await_cleanup(future) == 19

    async def work():
        await asyncio.sleep(0)
        return 29

    task = asyncio.create_task(work())
    assert await _await_cleanup(task) == 29
    assert task.result() == 29


@pytest.mark.asyncio
@pytest.mark.parametrize("sink_mode", ["raises", "cancels", "both"])
async def test_cancelled_cleanup_keeps_primary_over_diagnostic_sink(sink_mode):
    import kailash.utils.resource_manager as module

    started = asyncio.Event()
    release = asyncio.Event()
    drained = []
    observed = []

    class Sink(logging.Handler):
        def emit(self, record):
            if sink_mode in {"cancels", "both"}:
                asyncio.current_task().cancel("secondary-sink")
            if sink_mode in {"raises", "both"}:
                raise RuntimeError("secondary-sink")

    async def cleanup():
        started.set()
        await release.wait()
        drained.append(True)
        raise ValueError("secondary-cleanup")

    async def caller():
        try:
            await _await_cleanup(cleanup())
        except asyncio.CancelledError as error:
            observed.append(error)
        await asyncio.sleep(0)
        observed.append("continued")

    sink = Sink()
    module.logger.addHandler(sink)
    try:
        task = asyncio.create_task(caller())
        await started.wait()
        token = object()
        task.cancel(token)
        await asyncio.sleep(0)
        release.set()
        await task
        assert drained == [True]
        assert isinstance(observed[0], asyncio.CancelledError)
        assert observed[0].args[0] is token
        assert observed[1] == "continued"
    finally:
        module.logger.removeHandler(sink)
        release.set()
