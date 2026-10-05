"""Optional cancellation observation cannot change cleanup custody or identity."""

import asyncio

import pytest

from kailash.sdk_exceptions import HardTimeLimitExceeded
from kailash.utils.resource_manager import _await_cleanup


@pytest.mark.asyncio
@pytest.mark.parametrize("native_task", [False, True])
@pytest.mark.parametrize("cleanup_failure", [False, True])
@pytest.mark.parametrize(
    "observer_mode", ["return", "ordinary", "control", "cancel_return", "cancel_raise"]
)
async def test_cancel_observer_runs_once_and_cannot_replace_caller(
    native_task, cleanup_failure, observer_mode
):
    started, release = asyncio.Event(), asyncio.Event()
    observations, events = [], []
    cleanup_error = ValueError("owned cleanup error")

    async def cleanup():
        started.set()
        await release.wait()
        events.append("drained")
        if cleanup_failure:
            raise cleanup_error
        return "completed"

    def observe(error):
        observations.append(error)
        if observer_mode.startswith("cancel"):
            asyncio.current_task().cancel("observer cancellation")
        if observer_mode in ("ordinary", "cancel_raise"):
            raise RuntimeError("observer ordinary failure")
        if observer_mode == "control":
            raise HardTimeLimitExceeded("observer control")

    owned = asyncio.create_task(cleanup()) if native_task else cleanup()
    waiter = asyncio.create_task(_await_cleanup(owned, on_cancel=observe))
    try:
        await asyncio.wait_for(started.wait(), 2)
        waiter.cancel("first caller")
        await asyncio.sleep(0)
        waiter.cancel("second caller")
        await asyncio.sleep(0)
        assert not waiter.done()
        release.set()
        with pytest.raises(asyncio.CancelledError) as caught:
            await waiter
        assert len(observations) == 1
        assert caught.value is observations[0]
        assert caught.value.args == ("first caller",)
        assert events == ["drained"]
        if native_task:
            assert owned.done() and not owned.cancelled()
            if cleanup_failure:
                assert owned.exception() is cleanup_error
            else:
                assert owned.result() == "completed"
    finally:
        release.set()
        await asyncio.gather(waiter, return_exceptions=True)
