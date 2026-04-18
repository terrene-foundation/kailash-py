"""Tier 2 wiring test: partial-startup crash still runs the shutdown branch.

Round-1 red-team sec H1 / rev H1: if ``router.startup()`` or the injected
``startup_hook`` raises BEFORE the ``yield`` in ``WorkflowServer``'s lifespan,
the previous code never entered ``finally:``. ShutdownCoordinator was not
invoked, plugins whose on_startup ran earlier in the chain leaked, and the
ThreadPoolExecutor registered at ``WorkflowServer.__init__`` never shut down.

The fix widens the ``try:`` to wrap the whole startup sequence, so even on
an aborted startup the shutdown branch runs. This test asserts that
externally-observable behavior against real FastAPI lifespan semantics.

No mocking — real FastAPI, real ShutdownCoordinator, real asyncio.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI

from kailash.servers.workflow_server import WorkflowServer


class _BoomStartupError(RuntimeError):
    """Marker exception so the test can assert the right exception surfaced."""


@pytest.mark.integration
@pytest.mark.asyncio
async def test_startup_hook_crash_still_runs_shutdown_branch():
    """When startup_hook raises, shutdown_hook + ShutdownCoordinator still fire.

    This is the partial-startup path that leaked resources before the fix.
    """
    shutdown_hook_fired: dict[str, bool] = {"ran": False}
    coordinator_probe_fired: dict[str, bool] = {"ran": False}

    async def startup_hook_that_raises() -> None:
        # Simulates a plugin on_startup hanging or failing — the exact
        # failure the red-team H1 scenario described.
        raise _BoomStartupError("startup_hook sentinel failure")

    async def shutdown_hook() -> None:
        shutdown_hook_fired["ran"] = True

    server = WorkflowServer(
        title="partial-startup-test",
        startup_hook=startup_hook_that_raises,
        shutdown_hook=shutdown_hook,
    )

    def coordinator_probe() -> None:
        coordinator_probe_fired["ran"] = True

    # Register a probe on the ShutdownCoordinator so we can verify the
    # coordinator ran its registered callbacks during the partial-startup
    # teardown. Priority 50 runs after the default executor shutdown
    # (priority 0) but is unrelated — the assertion is purely "did it run".
    server.shutdown_coordinator.register(
        "partial_startup_probe", coordinator_probe, priority=50
    )

    app: FastAPI = server.app

    # Drive the lifespan directly (mirrors what uvicorn does) and assert
    # the startup exception propagates AND the teardown branch ran.
    raised: Exception | None = None
    try:
        async with app.router.lifespan_context(app):
            pytest.fail(
                "Lifespan startup should have raised before yielding — got "
                "to the inside of `async with`"
            )
    except _BoomStartupError as exc:
        raised = exc
    except Exception as exc:
        # FastAPI may wrap the original exception; accept the wrapped form
        # as long as the cause chain includes our marker.
        cause = exc
        while cause is not None:
            if isinstance(cause, _BoomStartupError):
                raised = cause
                break
            cause = cause.__cause__ or cause.__context__
        if raised is None:
            raise

    assert (
        raised is not None
    ), "Expected _BoomStartupError to surface through the lifespan; got None."

    # The key invariants of the fix: even though startup_hook raised BEFORE
    # `yield`, the shutdown branch still fired.
    assert shutdown_hook_fired["ran"] is True, (
        "shutdown_hook did not fire after aborted startup — the try: is not "
        "widened to wrap router.startup() + startup_hook(). "
        "ShutdownCoordinator-registered resources leak on every partial "
        "startup crash."
    )
    assert coordinator_probe_fired["ran"] is True, (
        "ShutdownCoordinator.shutdown() did not run its registered "
        "callbacks on aborted startup — the ThreadPoolExecutor registered "
        "at WorkflowServer.__init__ leaks until process exit."
    )
