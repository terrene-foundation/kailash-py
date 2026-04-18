"""Tier 2 wiring test: plugin `on_startup` tasks survive (regression for #501).

Before the fix, Nexus.start() called `_call_startup_hooks()` BEFORE uvicorn
booted. For async hooks, that path reached `asyncio.run(hook())`, which:

  1. Created a fresh event loop.
  2. Ran the hook (which typically does
     `self._bg_task = asyncio.create_task(periodic_job())` to schedule a
     long-lived background task).
  3. Returned from the hook and CLOSED the loop, cancelling every task the
     hook had just created.

Then uvicorn booted its own loop and the plugin's background task was gone.

This test:
  1. Installs a plugin whose async `on_startup` schedules a
     `create_task(periodic_heartbeat())` that increments a counter every
     100ms.
  2. Boots Nexus against a real uvicorn.
  3. Waits 1.0s and asserts:
       - the task is NOT done (i.e. still running)
       - the counter is >= 5 (proving the task actually ran and the tick
         interval was respected).
  4. Cleans up.
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


class HeartbeatPlugin:
    """Plugin whose on_startup schedules a long-lived background task.

    Matches the NexusPluginProtocol: has `name`, `install()`, and
    `on_startup()`. The plugin tracks the task handle and the counter on
    itself so the test can inspect them after boot.
    """

    name = "heartbeat-test-plugin"

    def __init__(self) -> None:
        self.bg_task: asyncio.Task | None = None
        self.counter: int = 0
        self._stop = False

    def install(self, app) -> None:
        # No-op install — all the interesting work happens at startup.
        return None

    async def on_startup(self) -> None:
        self.bg_task = asyncio.create_task(self._heartbeat())

    async def on_shutdown(self) -> None:
        self._stop = True
        if self.bg_task is not None:
            self.bg_task.cancel()
            try:
                await self.bg_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat(self) -> None:
        while not self._stop:
            self.counter += 1
            await asyncio.sleep(0.1)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_plugin_on_startup_task_survives_1s_of_server_uptime():
    """Install plugin, boot Nexus, assert background task is alive after 1s."""
    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    plugin = HeartbeatPlugin()
    app.add_plugin(plugin)

    fastapi_app = app.fastapi_app
    assert fastapi_app is not None

    port = _free_port()
    config = uvicorn.Config(
        fastapi_app,
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
        assert server.started, "uvicorn never reached started state"

        # Prove the server is up by hitting a real endpoint.
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        # Give the heartbeat 1s of real wall time inside uvicorn's loop.
        await asyncio.sleep(1.0)

        # Core invariant (#501): the task survives the pre-uvicorn hook path.
        assert plugin.bg_task is not None, (
            "Plugin on_startup never ran — hook was not invoked inside "
            "the FastAPI lifespan"
        )
        assert not plugin.bg_task.done(), (
            "Plugin background task is DONE — it was cancelled before "
            "uvicorn's loop took over. The old asyncio.run() path closed "
            "the loop and destroyed every task the hook scheduled."
        )
        assert plugin.counter >= 5, (
            f"Heartbeat counter only reached {plugin.counter} after 1s of "
            f"uptime (expected >= 5). The task exists but is not running "
            f"on uvicorn's loop."
        )
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=5.0)
        except asyncio.TimeoutError:
            server_task.cancel()
            try:
                await server_task
            except (asyncio.CancelledError, Exception):
                pass
        # Ensure heartbeat task is cancelled even if shutdown didn't clean up.
        if plugin.bg_task is not None and not plugin.bg_task.done():
            plugin.bg_task.cancel()
            try:
                await plugin.bg_task
            except (asyncio.CancelledError, Exception):
                pass
        app.close()
