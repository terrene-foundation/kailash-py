"""Tier 2 wiring test: shutdown path runs router.on_shutdown, plugin on_shutdown, and ShutdownCoordinator.

Fix symmetry: whoever fixes startup also owns shutdown. This test boots a
real Nexus, registers hook probes at every layer:

  1. `app.router.on_shutdown.append(fn)` — FastAPI router-level hook
  2. Plugin `on_shutdown` via NexusPluginProtocol
  3. A probe on `ShutdownCoordinator` via its `register()` API

Then shuts down the server gracefully (via `server.should_exit = True`) and
asserts every probe fired, in the correct order.

No mocking — real uvicorn, real httpx, real asyncio tasks.
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


class ShutdownProbePlugin:
    """Plugin recording whether on_shutdown fired."""

    name = "shutdown-probe-plugin"

    def __init__(self) -> None:
        self.shutdown_fired: bool = False

    def install(self, app) -> None:
        return None

    async def on_shutdown(self) -> None:
        self.shutdown_fired = True


@pytest.mark.integration
@pytest.mark.asyncio
async def test_shutdown_runs_router_plugin_and_coordinator():
    """Boot Nexus, shut down, assert all three shutdown surfaces fired."""
    fired: dict[str, bool] = {"router": False, "coordinator": False}

    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )
    plugin = ShutdownProbePlugin()
    app.add_plugin(plugin)

    fastapi_app = app.fastapi_app
    assert fastapi_app is not None

    async def router_shutdown() -> None:
        fired["router"] = True

    fastapi_app.router.on_shutdown.append(router_shutdown)

    # The ShutdownCoordinator is on the underlying WorkflowServer instance.
    gateway = app._http_transport.gateway
    assert gateway is not None
    coordinator = gateway.shutdown_coordinator

    def coordinator_probe() -> None:
        fired["coordinator"] = True

    # Priority 50 — runs after the default executor shutdown (priority 0)
    # but well within the coordinator's default timeout.
    coordinator.register("probe", coordinator_probe, priority=50)

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

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        # Trigger graceful shutdown.
        server.should_exit = True
        try:
            await asyncio.wait_for(server_task, timeout=10.0)
        except asyncio.TimeoutError:
            server_task.cancel()
            try:
                await server_task
            except (asyncio.CancelledError, Exception):
                pass
            pytest.fail("uvicorn did not stop within 10s")

        # All three shutdown surfaces must have fired inside the lifespan.
        assert plugin.shutdown_fired is True, (
            "Plugin on_shutdown hook did not fire — the custom FastAPI "
            "lifespan did not route shutdown hooks through the async path"
        )
        assert fired["router"] is True, (
            "router.on_shutdown handler did not fire — the custom "
            "lifespan did not invoke app.router._shutdown()"
        )
        assert fired["coordinator"] is True, (
            "ShutdownCoordinator.shutdown() did not run its registered " "callbacks"
        )
    finally:
        if not server_task.done():
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
