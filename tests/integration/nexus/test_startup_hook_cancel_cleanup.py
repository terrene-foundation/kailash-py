"""Tier 2 wiring test: startup_hook cancel-cleanup contract (sec M-N2).

Round-2 red-team sec M-N2: when ``asyncio.wait_for(startup_hook, timeout)``
times out, the cancellation propagates into the hook mid-execution. Any
resources the hook had acquired before the cancel point (DB connections,
spawned tasks, opened files) are NOT released by the framework — the
framework's only cleanup obligation is invoking ``shutdown_hook`` inside
the lifespan's ``finally:`` block.

This test proves the documented contract:

  "If a plugin's on_startup raises or is cancelled, its on_shutdown is
   still called. Plugins MUST write on_shutdown to be safe against
   partial-init state (every resource acquired in on_startup MUST be
   safe to release even if on_startup didn't finish)."

Real FastAPI, real asyncio.wait_for, real cancellation — no mocking.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from kailash.servers.workflow_server import WorkflowServer


@pytest.mark.integration
@pytest.mark.asyncio
async def test_startup_hook_timeout_invokes_shutdown_hook_for_partial_init_cleanup():
    """Plugin acquires a resource, then hangs; timeout cancels; shutdown_hook releases."""
    # Simulate a plugin that tracks acquired resources so on_shutdown can
    # release whatever on_startup managed to acquire.
    plugin_state: dict[str, bool] = {
        "resource_acquired": False,
        "resource_released": False,
        "cleanup_observed_partial_init": False,
    }

    async def partially_initializing_startup_hook() -> None:
        # Step 1: acquire a resource (observable side effect).
        plugin_state["resource_acquired"] = True
        # Step 2: wait for something that will never come before timeout fires.
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            # Contract clause 3: do NOT swallow; re-raise after any
            # cleanup that MUST happen synchronously under cancellation.
            raise

    async def defensive_shutdown_hook() -> None:
        # Contract clause 1: shutdown_hook is idempotent + safe against
        # partial-init state. It checks whether on_startup made it past
        # the acquisition step and only then releases.
        if plugin_state["resource_acquired"] and not plugin_state["resource_released"]:
            plugin_state["cleanup_observed_partial_init"] = True
            plugin_state["resource_released"] = True

    server = WorkflowServer(
        title="cancel-cleanup-test",
        startup_hook=partially_initializing_startup_hook,
        shutdown_hook=defensive_shutdown_hook,
        startup_hook_timeout=0.1,  # short bound → fast cancellation
    )
    app: FastAPI = server.app

    # Exercise the lifespan; expect timeout on startup.
    timed_out = False
    try:
        async with app.router.lifespan_context(app):
            pytest.fail("Lifespan should have timed out during startup_hook")
    except asyncio.TimeoutError:
        timed_out = True
    except Exception as exc:  # pragma: no cover — defensive against wrapped exc chains
        cause = exc
        while cause is not None:
            if isinstance(cause, asyncio.TimeoutError):
                timed_out = True
                break
            cause = cause.__cause__

    assert timed_out, "Expected asyncio.TimeoutError to surface from startup_hook"

    # Contract proofs:
    # 1. Resource was acquired before the timeout (partial-init reached step 1).
    assert plugin_state["resource_acquired"] is True, (
        "Test setup: startup_hook should have acquired the resource before "
        "timeout; if this fails, the timeout may be too short to exercise "
        "the contract."
    )
    # 2. shutdown_hook observed the partial-init state.
    assert plugin_state["cleanup_observed_partial_init"] is True, (
        "Cancel-cleanup contract VIOLATED: shutdown_hook should have been "
        "invoked by the lifespan's finally block after startup_hook "
        "timed out, and it should have observed the partial-init state."
    )
    # 3. Resource was released.
    assert plugin_state["resource_released"] is True, (
        "Cancel-cleanup contract VIOLATED: shutdown_hook should have "
        "released the resource that the timed-out startup_hook left behind."
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_startup_hook_spawned_tasks_survive_via_shutdown_hook_cleanup():
    """Tasks spawned by startup_hook before cancel are cleaned up via shutdown_hook registration.

    Contract clause 2: if the hook spawns tasks via asyncio.create_task that
    cannot be cancelled via the parent coroutine's cancellation, the hook
    MUST register them with shutdown_hook for teardown.
    """
    spawned_tasks: list[asyncio.Task] = []
    task_cancelled_in_shutdown: dict[str, bool] = {"ran": False}

    async def never_ending_background() -> None:
        await asyncio.Event().wait()

    async def startup_hook_with_background_task() -> None:
        # Spawn a long-running task BEFORE hitting the cancellation point.
        task = asyncio.create_task(never_ending_background())
        spawned_tasks.append(task)
        # Now hang so timeout fires.
        await asyncio.Event().wait()

    async def shutdown_hook_cancels_spawned() -> None:
        for task in spawned_tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    task_cancelled_in_shutdown["ran"] = True

    server = WorkflowServer(
        title="spawned-task-cleanup-test",
        startup_hook=startup_hook_with_background_task,
        shutdown_hook=shutdown_hook_cancels_spawned,
        startup_hook_timeout=0.1,
    )
    app: FastAPI = server.app

    try:
        async with app.router.lifespan_context(app):
            pytest.fail("Lifespan should have timed out")
    except asyncio.TimeoutError:
        pass
    except Exception as exc:
        cause = exc
        while cause is not None:
            if isinstance(cause, asyncio.TimeoutError):
                break
            cause = cause.__cause__
        else:
            raise

    assert len(spawned_tasks) == 1, "startup_hook should have spawned one task"
    assert task_cancelled_in_shutdown["ran"] is True, (
        "Spawned task was not cancelled by shutdown_hook — contract clause 2 "
        "(plugins MUST cancel spawned tasks via shutdown_hook) violated."
    )
    assert spawned_tasks[0].cancelled(), "Spawned task should be in cancelled state"
