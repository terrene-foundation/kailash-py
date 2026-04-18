"""Tier 2 wiring test: startup_hook_timeout bounds a hung plugin on_startup.

Round-1 red-team sec M2: a plugin on_startup that hangs (awaiting a DB that
never responds, an HTTP dependency that never answers) pins the FastAPI
lifespan coroutine forever. Uvicorn never begins accepting connections and
Kubernetes restarts the pod into CrashLoopBackOff.

The fix adds an optional ``startup_hook_timeout`` kwarg to
``WorkflowServer.__init__`` (and ``create_gateway``) that wraps the hook
invocation in ``asyncio.wait_for``. On timeout the lifespan's shutdown
branch still runs (via the widened try/finally from sec H1).

No mocking — real FastAPI, real asyncio.wait_for.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI

from kailash.servers.workflow_server import WorkflowServer


@pytest.mark.integration
@pytest.mark.asyncio
async def test_startup_hook_timeout_aborts_hung_hook_and_runs_teardown():
    """A startup_hook that never returns MUST be timed out, and teardown MUST run."""
    shutdown_fired: dict[str, bool] = {"ran": False}

    async def hung_startup_hook() -> None:
        # Never returns — simulates the DoS vector described in sec M2.
        await asyncio.Event().wait()

    async def shutdown_hook() -> None:
        shutdown_fired["ran"] = True

    server = WorkflowServer(
        title="timeout-test",
        startup_hook=hung_startup_hook,
        shutdown_hook=shutdown_hook,
        startup_hook_timeout=0.25,  # short bound for test speed
    )

    app: FastAPI = server.app

    timed_out = False
    try:
        async with app.router.lifespan_context(app):
            pytest.fail("Lifespan should have timed out during startup_hook")
    except asyncio.TimeoutError:
        timed_out = True
    except Exception as exc:
        # Accept wrapped cause chains too.
        cause = exc
        while cause is not None:
            if isinstance(cause, asyncio.TimeoutError):
                timed_out = True
                break
            cause = cause.__cause__ or cause.__context__
        if not timed_out:
            raise

    assert timed_out, "Expected asyncio.TimeoutError to surface via the lifespan."
    assert shutdown_fired["ran"] is True, (
        "shutdown_hook did not fire after startup_hook timeout — the "
        "widened try/finally is not actually wrapping the timeout branch."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_startup_hook_timeout_none_preserves_unbounded_wait():
    """When timeout is None (the default) the hook gets an unbounded await.

    Asserted behaviorally: with a fast-returning hook and timeout=None the
    lifespan completes normally and startup_hook fires.
    """
    fired: dict[str, bool] = {"startup": False, "shutdown": False}

    async def fast_startup_hook() -> None:
        fired["startup"] = True

    async def shutdown_hook() -> None:
        fired["shutdown"] = True

    server = WorkflowServer(
        title="no-timeout-test",
        startup_hook=fast_startup_hook,
        shutdown_hook=shutdown_hook,
        # startup_hook_timeout defaults to None — no wait_for wrap.
    )

    app: FastAPI = server.app
    async with app.router.lifespan_context(app):
        assert fired["startup"] is True, "startup_hook did not fire"

    assert fired["shutdown"] is True, "shutdown_hook did not fire"
