# Copyright 2026 Terrene Foundation
# SPDX-License-Identifier: Apache-2.0

"""Regression: cancelling a background task before it starts MUST NOT leak its coroutine.

``Nexus.run_in_background(coro)`` wraps ``coro`` in a ``_safe_wrapper()``
coroutine and makes the WRAPPER the ``asyncio.Task``. When the task is
cancelled before the event loop has scheduled the wrapper for the first time,
the wrapper's ``await coro`` never executes -- so ``coro`` is never awaited and
CPython emits ``RuntimeWarning: coroutine '<name>' was never awaited`` when it
is eventually garbage-collected.

Surfaced as a stray RuntimeWarning from
``tests/unit/test_phase2_apis.py::TestRunInBackground::test_returns_cancellable_task``,
which does exactly this (create, then immediately cancel). Per
``rules/testing.md`` § Test Resource Cleanup a warning emitted from a finalizer
is a real defect: it fires at an arbitrary later GC and is attributed to
whatever code happened to trigger collection.

Instrument note: the assertion below probes the coroutine's STATE, not the
emitted warning. The warning is raised from a later event-loop callback
(``asyncio/events.py`` running ``self._context.run(...)``), so a
``warnings.catch_warnings`` block around the cancel does NOT capture it and
would pass identically whether or not the leak exists -- a non-discriminating
instrument. ``inspect.getcoroutinestate`` answers the question directly and
deterministically: a coroutine still in ``CORO_CREATED`` after its task
finished was never awaited.
"""

import asyncio
import inspect

import pytest

from nexus import Nexus


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancel_before_start_does_not_leak_unawaited_coroutine():
    """Cancelling immediately MUST leave ``coro`` closed, not un-started.

    Falsifying result: with the leak present the coroutine is still
    ``CORO_CREATED`` once the task has finished, and this assertion fails.
    """
    with Nexus(enable_durability=False) as app:

        async def long_work():
            await asyncio.sleep(100)

        coro = long_work()
        assert inspect.getcoroutinestate(coro) == inspect.CORO_CREATED

        task = app.run_in_background(coro)
        # Cancel before the loop ever schedules _safe_wrapper.
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        state = inspect.getcoroutinestate(coro)
        assert state == inspect.CORO_CLOSED, (
            f"coroutine left in {state} after its background task finished; "
            "it was never awaited and will emit "
            "'RuntimeWarning: coroutine ... was never awaited' at GC"
        )


@pytest.mark.regression
@pytest.mark.asyncio
async def test_cancel_after_start_still_propagates_cancellation():
    """The leak fix MUST NOT swallow cancellation for an already-running task.

    Guards the obvious wrong fix (absorbing CancelledError, or closing the
    coroutine unconditionally): a task cancelled while genuinely in-flight MUST
    still raise CancelledError to its awaiter.
    """
    started = asyncio.Event()

    with Nexus(enable_durability=False) as app:

        async def long_work():
            started.set()
            await asyncio.sleep(100)

        task = app.run_in_background(long_work())
        # Let the wrapper actually enter `await coro` before cancelling.
        await asyncio.wait_for(started.wait(), timeout=2.0)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.regression
@pytest.mark.asyncio
async def test_normal_completion_still_runs_the_coroutine():
    """The leak fix MUST NOT prevent an un-cancelled coroutine from running."""
    ran = asyncio.Event()

    with Nexus(enable_durability=False) as app:

        async def work():
            ran.set()

        task = app.run_in_background(work())
        await asyncio.wait_for(task, timeout=2.0)

        assert ran.is_set(), "background coroutine did not run to completion"
