"""Regression: #500 — Nexus custom FastAPI lifespan silently ignores router.on_startup handlers.

Minimal reproduction from the issue body:

    app = Nexus()
    flag = []
    async def my_startup():
        flag.append(1)
    app.fastapi_app.router.on_startup.append(my_startup)
    # boot server, hit endpoint
    # EXPECTED: flag == [1]
    # ACTUAL (pre-fix): flag == []

Root cause: `WorkflowServer.__init__` passed a custom `lifespan` kwarg to
`FastAPI()`, which REPLACES (not wraps) Starlette's default
`_DefaultLifespan`. `_DefaultLifespan` was the only code that iterated
`router.on_startup` / `router.on_shutdown`. The custom lifespan did not
include `await app.router._startup()`, so every user-registered router hook
was silently dropped.

Fix: `WorkflowServer.__init__` now calls `await app.router._startup()` and
`await app.router._shutdown()` inside its lifespan, honoring the documented
FastAPI pattern.

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


@pytest.mark.regression
@pytest.mark.asyncio
async def test_issue_500_router_on_startup_handler_fires():
    """Regression: #500 — router.on_startup.append(fn) MUST run fn on boot."""
    flag: list[int] = []

    app = Nexus(
        api_port=_free_port(),
        auto_discovery=False,
        enable_durability=False,
        rate_limit=None,
    )

    async def my_startup() -> None:
        flag.append(1)

    app.fastapi_app.router.on_startup.append(my_startup)

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
    task = asyncio.create_task(server.serve())

    try:
        for _ in range(50):
            if server.started:
                break
            await asyncio.sleep(0.1)
        assert server.started

        async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}") as client:
            resp = await client.get("/", timeout=5.0)
            assert resp.status_code == 200

        assert flag == [1], (
            f"router.on_startup handler did not fire (flag={flag}). "
            f"This is the #500 bug: custom FastAPI lifespan replaced "
            f"Starlette's _DefaultLifespan and dropped router.on_startup."
        )
    finally:
        server.should_exit = True
        try:
            await asyncio.wait_for(task, timeout=5.0)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        app.close()
