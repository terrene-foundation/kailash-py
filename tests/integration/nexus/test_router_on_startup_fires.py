"""Tier 2 wiring test: `app.router.on_startup` hooks fire (regression for #500).

Before the fix, `WorkflowServer.__init__` passed a custom lifespan to FastAPI
that never invoked `app.router._startup()`, silently dropping every handler
users registered via the documented FastAPI pattern
`app.router.on_startup.append(fn)`.

This test boots a real `Nexus()` against a real uvicorn instance on an
ephemeral port, registers a router-level startup handler that mutates a
shared flag, hits a real endpoint via `httpx.AsyncClient`, and asserts the
flag is set. It exercises the ACTUAL FastAPI lifespan path, not a mock.

No mocking of uvicorn, FastAPI, Nexus, or asyncio — per testing.md Tier 2.
"""

from __future__ import annotations

import asyncio
import socket

import httpx
import pytest
import uvicorn

from nexus import Nexus


def _free_port() -> int:
    """Ask the kernel for an ephemeral TCP port we can bind to."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.mark.integration
@pytest.mark.asyncio
async def test_router_on_startup_fires_inside_uvicorn_lifespan():
    """Boot Nexus in-process, assert router.on_startup handler ran.

    Pattern:
      1. Construct Nexus (which builds the FastAPI app via the gateway).
      2. Register a router-level on_startup handler that sets a flag.
      3. Build uvicorn.Server with an ephemeral port, schedule it as a task.
      4. Wait for the server to report `started`, hit the root endpoint,
         assert the flag is set.
      5. Signal shutdown and await the server task.
    """
    startup_fired = {"router": False}

    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )

    fastapi_app = app.fastapi_app
    assert fastapi_app is not None, "Nexus gateway did not produce a FastAPI app"

    async def router_startup() -> None:
        startup_fired["router"] = True

    fastapi_app.router.on_startup.append(router_startup)

    port = _free_port()
    config = uvicorn.Config(
        fastapi_app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    server.config.lifespan = "on"  # force lifespan even if FastAPI disables it
    server_task = asyncio.create_task(server.serve())

    try:
        # Wait up to 5s for uvicorn to report started.
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        assert server.started, "uvicorn never reached started state"

        # Hit a real endpoint — uvicorn lifespan must have run by now.
        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        assert startup_fired["router"] is True, (
            "app.router.on_startup handler did not fire — "
            "Starlette's _DefaultLifespan was replaced by Nexus' custom "
            "lifespan and the replacement did not invoke app.router._startup()"
        )
    finally:
        server.should_exit = True
        # Give uvicorn up to 5s to shut down cleanly.
        try:
            await asyncio.wait_for(server_task, timeout=5.0)
        except asyncio.TimeoutError:
            server_task.cancel()
            try:
                await server_task
            except (asyncio.CancelledError, Exception):
                pass
        app.close()
