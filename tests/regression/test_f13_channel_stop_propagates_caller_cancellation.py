"""Regression: ``Channel.stop()`` must not swallow the CALLER's cancellation.

``api_channel.py`` and ``cli_channel.py`` both did::

    if self._<task> and not self._<task>.done():
        self._<task>.cancel()
        try:
            await self._<task>
        except asyncio.CancelledError:
            pass
    await self._cleanup()
    self.status = ChannelStatus.STOPPED

Two different events arrive at that ``await`` as the SAME exception type:

1. the task we just cancelled ending in ``CancelledError`` -- expected, and the
   whole reason the handler is there; and
2. *this* coroutine being cancelled by somebody else while it waits -- an
   ``asyncio.wait_for(channel.stop(), timeout=...)`` giving up, a supervisor
   tearing down a task group, a shutdown deadline expiring.

``except asyncio.CancelledError: pass`` cannot distinguish them, so case 2 was
swallowed: the caller's cancellation vanished and ``stop()`` returned normally
having set ``ChannelStatus.STOPPED`` -- a clean-stop claim for a stop that
never finished. Commit bb8a3f966 rejected this exact form one module over, for
this exact reason.

These tests assert the PROPERTY the two cases differ on -- whether the
cancellation reaches the caller -- not the mechanism. Both channels are REAL
objects; only the long-running task each supervises is a stand-in, because a
real uvicorn server / interactive CLI loop is not what is under test here.
"""

import asyncio

import pytest

pytestmark = pytest.mark.regression

pytest.importorskip(
    "uvicorn", reason="APIChannel requires the optional server extra (uvicorn)"
)
pytest.importorskip(
    "starlette", reason="APIChannel requires the optional server extra (starlette)"
)

from kailash.channels.api_channel import APIChannel  # noqa: E402
from kailash.channels.base import (  # noqa: E402
    ChannelConfig,
    ChannelStatus,
    ChannelType,
)
from kailash.channels.cli_channel import CLIChannel  # noqa: E402


def _api_channel():
    return APIChannel(
        # enable_auth=False: this suite exercises STOP/cancellation
        # semantics, not the auth gate (#2072). An unstated None would
        # inherit the server's fail-closed default and refuse to build.
        ChannelConfig(
            name="f13_api",
            channel_type=ChannelType.API,
            port=18991,
            enable_auth=False,
        )
    )


def _cli_channel():
    return CLIChannel(ChannelConfig(name="f13_cli", channel_type=ChannelType.CLI))


# (factory, name of the attribute holding the supervised task)
CHANNELS = [
    pytest.param(_api_channel, "_server_task", id="api_channel"),
    pytest.param(_cli_channel, "_main_task", id="cli_channel"),
]


def _run(scenario):
    """Drive on a private loop so the supervised task and stop() share one.

    Every task the scenario creates must be reaped before the loop closes, so
    the scenario owns its own teardown and returns plain observations.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(scenario())
    finally:
        loop.close()


async def _reap(task):
    """Let a deliberately-stubborn task actually die."""
    task.cancel()
    await asyncio.wait({task}, timeout=2.0)


def _close(channel):
    """CLIChannel holds a runtime reference; release it or __del__ warns."""
    close = getattr(channel, "close", None)
    if callable(close):
        close()


async def _park_in_stopping(channel):
    """Drive stop() until it is parked waiting on the supervised task."""
    stopper = asyncio.create_task(channel.stop())
    for _ in range(50):
        await asyncio.sleep(0.01)
        if channel.status is ChannelStatus.STOPPING:
            break
    return stopper


@pytest.mark.parametrize("factory,task_attr", CHANNELS)
def test_stop_propagates_a_cancellation_aimed_at_the_caller(factory, task_attr):
    """Cancelling a caller that is awaiting stop() must NOT yield a clean STOPPED.

    This is the case the old form reported success for. The supervised task
    here swallows the FIRST cancellation -- the one ``stop()`` itself issues --
    and dies on the second. That is what makes the two events separable:

    * ``stop()`` cancels the task, the task ignores it, ``stop()`` parks;
    * the caller is then cancelled. With ``await self._<task>`` the caller's
      cancellation is delivered to the SUPERVISED TASK (it is the awaited
      future), the task dies, ``CancelledError`` surfaces at that same
      ``await``, ``except CancelledError: pass`` eats it, and ``stop()``
      returns normally having set ``STOPPED``.

    So the caller asked to be cancelled and instead received a clean stop.
    """
    channel = factory()

    async def scenario():
        async def dies_on_second_cancel():
            cancels = 0
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    cancels += 1
                    if cancels >= 2:
                        raise

        task = asyncio.create_task(dies_on_second_cancel())
        await asyncio.sleep(0)
        setattr(channel, task_attr, task)
        channel.status = ChannelStatus.RUNNING

        stopper = await _park_in_stopping(channel)
        entered_stopping = channel.status is ChannelStatus.STOPPING

        # Somebody else cancels the caller WHILE it awaits stop().
        stopper.cancel()
        outcome = (await asyncio.gather(stopper, return_exceptions=True))[0]

        observed = {
            "entered_stopping": entered_stopping,
            "stopper_cancelled": stopper.cancelled(),
            "stopper_outcome": outcome,
            "status": channel.status,
        }
        await _reap(task)
        return observed

    try:
        observed = _run(scenario)

        assert observed["entered_stopping"], (
            "premise check: stop() should have entered STOPPING and parked on "
            f"the supervised task; status was {observed['status']}"
        )
        assert observed["stopper_cancelled"], (
            "stop() swallowed a cancellation aimed at its own caller and "
            f"returned {observed['stopper_outcome']!r}; the caller cannot "
            "tell an interrupted stop from a completed one"
        )
        # THE PROPERTY the false STOPPED was about: it did not finish.
        assert observed["status"] is not ChannelStatus.STOPPED, (
            "channel reports STOPPED after a stop that was cancelled part-way "
            "through -- the supervised task was never established as stopped"
        )
    finally:
        _close(channel)


@pytest.mark.parametrize("factory,task_attr", CHANNELS)
def test_stop_does_not_strand_a_caller_behind_an_unstoppable_task(factory, task_attr):
    """A caller cancelling stop() must regain control even if the task will not die.

    Second manifestation of the same conflation, and the worse one. With
    ``await self._<task>`` the awaited future IS the supervised task, so
    cancelling the caller only re-requests cancellation of a task that already
    ignores it -- nothing is ever delivered to the ``stop()`` frame and the
    caller waits forever. Observing completion instead of awaiting the task
    gives the caller its own cancellation point back.

    Bounded here so the failure is a crisp verdict rather than a suite hang.
    """
    channel = factory()

    async def scenario():
        released = asyncio.Event()

        async def stubborn():
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if released.is_set():
                        raise

        task = asyncio.create_task(stubborn())
        await asyncio.sleep(0)
        setattr(channel, task_attr, task)
        channel.status = ChannelStatus.RUNNING

        stopper = await _park_in_stopping(channel)
        entered_stopping = channel.status is ChannelStatus.STOPPING

        stopper.cancel()
        # ``asyncio.wait`` REPORTS on the timeout; ``wait_for`` would cancel
        # the stopper again, and a stopper that cannot unwind never completes
        # that cancellation either -- the bound has to observe, not act.
        done, _pending = await asyncio.wait({stopper}, timeout=5.0)
        stranded = stopper not in done

        observed = {
            "entered_stopping": entered_stopping,
            "stranded": stranded,
            "task_alive": not task.done(),
            "status": channel.status,
        }

        released.set()
        await _reap(task)
        await asyncio.gather(stopper, return_exceptions=True)
        return observed

    try:
        observed = _run(scenario)

        assert observed["entered_stopping"], (
            "premise check: stop() should have entered STOPPING and parked on "
            f"the supervised task; status was {observed['status']}"
        )
        assert not observed["stranded"], (
            "the caller cancelled stop() and never regained control: its "
            "cancellation was absorbed by the supervised task, which ignores "
            "cancellation, so nothing was ever delivered to the stop() frame"
        )
        assert observed["task_alive"], (
            "premise check: the unstoppable task should still be alive, which "
            "is what a STOPPED claim would be false about"
        )
        assert observed["status"] is not ChannelStatus.STOPPED, observed["status"]
    finally:
        _close(channel)


@pytest.mark.parametrize("factory,task_attr", CHANNELS)
def test_stop_still_completes_when_the_supervised_task_ends_as_cancelled(
    factory, task_attr
):
    """Control: the supervised task's OWN CancelledError is still absorbed.

    This is the case the ``except asyncio.CancelledError: pass`` existed for,
    and it must keep working -- the fix narrows what is swallowed, it does not
    stop swallowing altogether.
    """
    channel = factory()

    async def scenario():
        async def cooperative():
            while True:
                await asyncio.sleep(0.01)

        task = asyncio.create_task(cooperative())
        await asyncio.sleep(0)
        setattr(channel, task_attr, task)
        channel.status = ChannelStatus.RUNNING

        await channel.stop()
        return {"task_done": task.done(), "status": channel.status}

    try:
        observed = _run(scenario)
        assert observed["status"] is ChannelStatus.STOPPED, observed["status"]
        assert observed[
            "task_done"
        ], "stop() reported STOPPED while the supervised task was still running"
    finally:
        _close(channel)


@pytest.mark.parametrize("factory,task_attr", CHANNELS)
def test_stop_surfaces_a_supervised_task_that_died_of_a_real_error(factory, task_attr):
    """Control: a genuine task failure must not become invisible.

    The old ``await task`` re-raised anything the task ended with. Observing
    completion instead of awaiting must not turn a real crash into a silent
    clean stop (zero-tolerance Rule 3).
    """
    channel = factory()

    async def scenario():
        async def crashes_on_shutdown():
            try:
                while True:
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                raise RuntimeError("server died during shutdown")

        task = asyncio.create_task(crashes_on_shutdown())
        await asyncio.sleep(0)
        setattr(channel, task_attr, task)
        channel.status = ChannelStatus.RUNNING

        raised = None
        try:
            await channel.stop()
        except RuntimeError as exc:
            raised = exc
        return {"raised": raised, "status": channel.status}

    try:
        observed = _run(scenario)
        assert observed["raised"] is not None, (
            "stop() reported a clean stop for a supervised task that died of "
            "a real error -- the failure became invisible"
        )
        assert "server died during shutdown" in str(observed["raised"])
        assert observed["status"] is ChannelStatus.ERROR, (
            "a supervised task that died of a real error must leave the "
            f"channel in ERROR, not {observed['status']}"
        )
    finally:
        _close(channel)
