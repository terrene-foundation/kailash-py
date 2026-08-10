"""Regression: POST /monitoring/start must not report started on a dead handle.

Commit bb8a3f966 stopped POST /monitoring/stop from claiming ``stopped``
without establishing it. When the broadcast task refuses to stop, that fix
correctly RETAINS the task handle -- it is the only thing that can observe or
retry the task. The false success then moved one endpoint over::

    if not self._broadcast_task:
        self._broadcast_task = asyncio.create_task(self._broadcast_metrics())
    return {"status": "started", "run_id": request.run_id}

The truthiness test conflates two different things: "a handle object exists"
and "a task is broadcasting". Two ways that goes wrong, both reporting
``started``:

* after a stop that FAILED, the retained handle is truthy, so no task is
  created -- and the only task in existence is the one stop explicitly
  refused to certify as stopped; and
* after the broadcast task has ENDED (crashed, or exited its loop), the handle
  is still truthy and never cleared, so no task is ever created again and
  every subsequent start reports ``started`` with nothing broadcasting at all.

These assert the PROPERTY -- a live broadcast task exists, or the caller is
told it does not -- rather than the mechanism. Asserting on the handle's
truthiness is exactly what the endpoint already does wrong.
"""

import asyncio

import pytest

pytestmark = pytest.mark.regression

fastapi = pytest.importorskip(
    "fastapi", reason="DashboardAPIServer requires the optional fastapi extra"
)
from fastapi import HTTPException  # noqa: E402
from kailash.visualization.api import DashboardAPIServer, RunRequest  # noqa: E402


class _StubTaskManager:
    """Minimal collaborator: the SUT is the start handler, not storage."""

    def list_runs(self, *a, **kw):
        return []

    def get_run(self, *a, **kw):
        return None


def _server():
    server = DashboardAPIServer(task_manager=_StubTaskManager())
    # Pre-set so ``dashboard.start_monitoring`` short-circuits instead of
    # spawning its real background THREAD -- the thread is not under test and
    # would outlive the test's event loop.
    server.dashboard._monitoring = True
    return server


def _handler(server, path):
    """The REAL registered endpoint coroutine.

    Called directly rather than through TestClient so the broadcast task and
    the handler share one event loop; TestClient runs the app on its own loop,
    where a task created elsewhere can never be advanced.
    """
    route = next(r for r in server.app.routes if getattr(r, "path", None) == path)
    return route.endpoint


def _start(server):
    return _handler(server, "/api/v1/monitoring/start")


def _stop(server):
    return _handler(server, "/api/v1/monitoring/stop")


def _run(scenario):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(scenario())
    finally:
        loop.close()


async def _reap(task):
    task.cancel()
    await asyncio.wait({task}, timeout=2.0)


def test_start_refuses_while_a_failed_stop_left_the_broadcast_task_alive():
    """The case the endpoint reported ``started`` for.

    A stop that returned 500 leaves a task that ignored its cancellation still
    running. ``start`` then saw a truthy handle, created nothing, and reported
    ``started`` -- so the caller believes broadcasting was (re)established when
    the only task alive is the one stop refused to certify as stopped.
    """
    server = _server()

    async def scenario():
        released = asyncio.Event()

        async def stubborn():
            # Models a broadcast loop wedged somewhere that does not observe
            # cancellation, which is what makes stop refuse.
            while True:
                try:
                    await asyncio.sleep(0.01)
                except asyncio.CancelledError:
                    if released.is_set():
                        raise

        task = asyncio.create_task(stubborn())
        await asyncio.sleep(0)
        server._broadcast_task = task

        try:
            stop_outcome = await _stop(server)()
        except HTTPException as exc:
            stop_outcome = exc

        try:
            start_outcome = await _start(server)(RunRequest(run_id="r1"))
        except HTTPException as exc:
            start_outcome = exc

        observed = {
            "stop_outcome": stop_outcome,
            "start_outcome": start_outcome,
            "task_alive": not task.done(),
            "handle_is_same_task": server._broadcast_task is task,
            "monitoring": server.dashboard._monitoring,
        }

        released.set()
        await _reap(task)
        return observed

    observed = _run(scenario)

    # Premise: the stop really did fail and the task really is still alive.
    assert isinstance(
        observed["stop_outcome"], HTTPException
    ), f"premise check: stop should have refused; got {observed['stop_outcome']!r}"
    assert observed["task_alive"], "premise check: the stubborn task should survive"
    assert observed[
        "handle_is_same_task"
    ], "premise check: the failed stop must retain the handle (bb8a3f966)"

    # THE DEFECT: start reported success over a task nothing certified.
    assert isinstance(observed["start_outcome"], HTTPException), (
        "start reported success while the only broadcast task in existence is "
        "the one stop refused to certify as stopped: "
        f"{observed['start_outcome']!r}"
    )
    assert observed["start_outcome"].status_code == 409, observed[
        "start_outcome"
    ].status_code
    assert "did not complete" in observed["start_outcome"].detail

    # A refused start must not have half-applied: re-arming the dashboard's
    # ``_monitoring`` flag is what would let the wedged task resume pushing.
    assert observed["monitoring"] is False, (
        "start refused but still re-enabled monitoring, which is the wedged "
        "task's own loop condition -- the refusal left the system changed"
    )


def test_start_creates_a_new_task_when_the_previous_one_has_ended():
    """A handle for a task that already finished must not block a restart.

    ``_broadcast_metrics`` can end on its own -- its ``while`` condition goes
    false, or it raises. The handle is only ever cleared by a SUCCESSFUL stop,
    so a truthiness check keeps reporting ``started`` forever with nothing
    broadcasting.
    """
    server = _server()

    async def scenario():
        async def dies():
            raise RuntimeError("broadcast loop crashed")

        dead = asyncio.create_task(dies())
        await asyncio.sleep(0)
        assert dead.done(), "premise check: the task should have finished"
        server._broadcast_task = dead

        try:
            start_outcome = await _start(server)(RunRequest(run_id="r1"))
        except HTTPException as exc:
            start_outcome = exc

        replacement = server._broadcast_task
        observed = {
            "start_outcome": start_outcome,
            "replaced": replacement is not dead,
            "replacement_alive": replacement is not None and not replacement.done(),
        }

        if replacement is not None and replacement is not dead:
            await _reap(replacement)
        return observed

    observed = _run(scenario)

    assert observed["start_outcome"] == {"status": "started", "run_id": "r1"}, observed[
        "start_outcome"
    ]
    # THE PROPERTY: not "the handle is truthy" but "something is broadcasting".
    assert observed["replaced"], (
        "start reported started but kept the handle of a task that had already "
        "died -- nothing is broadcasting"
    )
    assert observed["replacement_alive"], "the replacement task is not running"


def test_start_creates_a_broadcast_task_on_a_clean_server():
    """Control: the ordinary path still starts broadcasting."""
    server = _server()

    async def scenario():
        assert server._broadcast_task is None, "premise check: clean server"
        start_outcome = await _start(server)(RunRequest(run_id="r1"))
        task = server._broadcast_task
        observed = {
            "start_outcome": start_outcome,
            "task_alive": task is not None and not task.done(),
        }
        if task is not None:
            await _reap(task)
        return observed

    observed = _run(scenario)
    assert observed["start_outcome"] == {"status": "started", "run_id": "r1"}
    assert observed["task_alive"], "no broadcast task was started"


def test_start_reuses_a_healthy_running_broadcast_task():
    """Control: start twice must not stack a second broadcaster.

    A live, never-cancelled task means broadcasting IS established, so
    ``started`` is truthful and no new task should be spawned.
    """
    server = _server()

    async def scenario():
        async def healthy():
            while True:
                await asyncio.sleep(0.01)

        task = asyncio.create_task(healthy())
        await asyncio.sleep(0)
        server._broadcast_task = task

        start_outcome = await _start(server)(RunRequest(run_id="r1"))
        observed = {
            "start_outcome": start_outcome,
            "same_task": server._broadcast_task is task,
        }
        await _reap(task)
        return observed

    observed = _run(scenario)
    assert observed["start_outcome"] == {"status": "started", "run_id": "r1"}
    assert observed[
        "same_task"
    ], "a second broadcast task was spawned beside a live one"
