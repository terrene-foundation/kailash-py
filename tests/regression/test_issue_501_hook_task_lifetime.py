"""Regression: #501 — Nexus._call_startup_hooks runs async hooks via asyncio.run, killing scheduled background tasks.

Minimal reproduction from the issue body:

    class MyPlugin:
        name = "my-plugin"
        def install(self, app): ...
        async def on_startup(self):
            self.task = asyncio.create_task(forever())

    async def forever():
        while True: await asyncio.sleep(0.1)

    app = Nexus()
    plugin = MyPlugin()
    app.add_plugin(plugin)
    # boot server, wait 1s
    # EXPECTED: plugin.task is not done()
    # ACTUAL (pre-fix): plugin.task is done() and was cancelled — the
    #   hook ran on a throwaway loop created by asyncio.run() which
    #   closed before uvicorn booted its own loop.

Root cause: `Nexus.start()` called `_call_startup_hooks()` BEFORE
`self._http_transport.run_blocking(...)` booted uvicorn. For async hooks,
the sync `_call_startup_hooks` entry point reached
`asyncio.run(hook())` (via `_run_async_hook`), which created a fresh event
loop, ran the hook, then CLOSED the loop — destroying every task the hook
scheduled.

Fix: plugin startup hooks now run via `_call_startup_hooks_async` inside
the FastAPI lifespan context manager, which executes inside uvicorn's own
event loop. Tasks scheduled by the hook therefore live for the server's
lifetime.

This regression test reproduces the minimal user-facing failure and MUST
NOT be deleted per orphan-detection rules.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
import uvicorn

from nexus import Nexus


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class BackgroundTaskPlugin:
    """Plugin whose on_startup schedules a long-lived task via create_task."""

    name = "bg-task-regression-plugin"

    def __init__(self) -> None:
        self.task: asyncio.Task | None = None

    def install(self, app) -> None:
        return None

    async def on_startup(self) -> None:
        self.task = asyncio.create_task(self._forever())

    async def _forever(self) -> None:
        while True:
            await asyncio.sleep(0.1)


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_501_plugin_on_startup_task_alive_after_1s():
    """Regression: #501 — a task scheduled by plugin on_startup MUST survive."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    plugin = BackgroundTaskPlugin()
    app.add_plugin(plugin)

    port = _free_port()
    config = uvicorn.Config(
        app.fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    server.config.lifespan = "on"
    server_task = asyncio.create_task(server.serve())

    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        assert server.started

        # Prove the server is actually serving, not just "started".
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        # Give the background task 1s to run on uvicorn's loop.
        await asyncio.sleep(1.0)

        assert plugin.task is not None, (
            "Plugin on_startup never ran — the lifespan did not invoke "
            "the async hook path"
        )
        assert not plugin.task.done(), (
            "Plugin background task is DONE — this is the #501 bug. "
            "The task was cancelled when asyncio.run()'s throwaway loop "
            "closed before uvicorn's loop started. Fix: hooks must run "
            "inside the FastAPI lifespan (uvicorn's loop)."
        )
    finally:
        if plugin.task is not None and not plugin.task.done():
            plugin.task.cancel()
            try:
                await plugin.task
            except (asyncio.CancelledError, Exception):
                pass
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=5.0)
        except asyncio.TimeoutError:
            server_task.cancel()
            try:
                await server_task
            except (asyncio.CancelledError, Exception):
                pass
        app.close()
