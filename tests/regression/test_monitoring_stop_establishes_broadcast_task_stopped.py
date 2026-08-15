"""Regression: POST /monitoring/stop must not report stopped unless it is.

The endpoint did::

    if self._broadcast_task:
        self._broadcast_task.cancel()
        self._broadcast_task = None
    return {"status": "stopped"}

``cancel()`` only REQUESTS cancellation. The return was discarded, nothing
awaited or inspected the task, and ``{"status": "stopped"}`` went back to the
caller regardless -- a status field, which an orchestrator acts on, not merely
a log line.

Nulling the handle was the worse half. ``dashboard.stop_monitoring()`` runs
first and clears ``dashboard._monitoring``, which is the broadcast task's own
``while`` condition, so once the handle was dropped the task was unreachable
AND unobservable: a retry had nothing to act on, and ``start_monitoring``'s
``if not self._broadcast_task`` would spawn a SECOND broadcast task beside a
wedged first.

These assert the PROPERTY -- the task is no longer running -- rather than the
mechanism (whether the handle happens to be None). A handle-is-None assertion
would have passed against the original code, which is precisely how this
survived.
"""

import asyncio

import pytest

pytestmark = pytest.mark.regression

fastapi = pytest.importorskip(
    "fastapi", reason="DashboardAPIServer requires the optional fastapi extra"
)
from fastapi import HTTPException  # noqa: E402

from kailash.visualization.api import DashboardAPIServer  # noqa: E402


class _StubTaskManager:
    """Minimal collaborator: the SUT here is the stop handler, not storage."""

    def list_runs(self, *a, **kw):
        return []

    def get_run(self, *a, **kw):
        return None


def _server():
    # require_auth=False: this suite exercises the STOP handler's establishment
    # that the broadcast task actually stopped, not the authentication gate
    # #2112 added. The handler is invoked directly rather than over HTTP, so
    # the middleware is not on the path; the flag is what keeps construction
    # from demanding a credential source. The gate itself is covered by
    # tests/regression/test_issue_2112_dashboard_api_auth.py.
    server = DashboardAPIServer(task_manager=_StubTaskManager(), require_auth=False)
    server.dashboard._monitoring = True
    return server


def _stop_handler(server):
    """The REAL registered endpoint coroutine.

    Called directly rather than through TestClient so the broadcast task and
    the handler share one event loop. TestClient runs the app on its own loop;
    a task created on a different, non-running loop can never be advanced by
    the handler's ``asyncio.wait``, which times out and tests the harness
    rather than the code.
    """
    route = next(
        r
        for r in server.app.routes
        if getattr(r, "path", None) == "/api/v1/monitoring/stop"
    )
    return route.endpoint


def test_stop_reports_stopped_only_when_the_task_actually_stopped():
    """Cooperative task: endpoint reports stopped AND the task is not running."""
    server = _server()

    async def cooperative():
        while True:
            await asyncio.sleep(0.01)

    async def drive():
        task = asyncio.create_task(cooperative())
        await asyncio.sleep(0)
        server._broadcast_task = task
        result = await _stop_handler(server)()
        return task, result

    loop = asyncio.new_event_loop()
    try:
        task, result = loop.run_until_complete(drive())

        assert result == {"status": "stopped"}, result
        # THE PROPERTY: not "the handle is None" but "it is not running".
        assert task.done(), (
            "endpoint reported stopped while the broadcast task was still "
            "running -- the status claims more than the operation performed"
        )
    finally:
        loop.close()


def test_stop_refuses_to_report_stopped_when_the_task_survives_cancellation():
    """A task that outlives cancel(): the endpoint must NOT claim stopped.

    This is the case the original code reported success for. The stubborn task
    models a broadcast loop wedged somewhere that does not observe
    cancellation promptly.
    """
    server = _server()
    released = asyncio.Event()

    async def stubborn():
        while True:
            try:
                await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                if released.is_set():
                    raise
                # swallow: models a task that does not stop when asked

    holder = {}

    async def drive():
        task = asyncio.create_task(stubborn())
        await asyncio.sleep(0)
        server._broadcast_task = task
        holder["task"] = task
        try:
            return await _stop_handler(server)()
        except HTTPException as exc:
            return exc

    loop = asyncio.new_event_loop()
    try:
        outcome = loop.run_until_complete(drive())
        task = holder["task"]

        assert isinstance(outcome, HTTPException), (
            "endpoint returned success for a broadcast task that survived "
            f"cancellation: {outcome!r}"
        )
        assert outcome.status_code == 500, outcome.status_code
        assert "did not stop" in outcome.detail
        # THE PROPERTY the refusal is about: it really is still running.
        assert not task.done(), "premise check: the stubborn task should survive"
        # The handle MUST be retained: it is the only thing that can observe
        # or retry this task. Dropping it is what made the original defect
        # unrecoverable in-process.
        assert server._broadcast_task is task, (
            "handle was dropped for a task that never stopped; nothing can "
            "now observe or retry it"
        )
    finally:
        released.set()
        task = holder.get("task")
        if task is not None:
            loop.run_until_complete(_reap(task))
        loop.close()


async def _reap(task):
    task.cancel()
    await asyncio.wait({task}, timeout=2.0)
